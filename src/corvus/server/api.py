"""Authenticated alert queue and manual investigations. No model credentials or calls here."""

from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..errors import BackendError, ConfigError
from . import alerts, auth, connections, operations
from .database import audit, connect, initialize
from .investigations import exporting, overview, policy, reviews, steps
from .investigations import service as triage
from .settings import Settings


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=2048)


class ConnectionInput(Credentials):
    name: str = Field(min_length=1, max_length=80)
    indexer_url: str = Field(min_length=1, max_length=256)
    backfill_hours: int = Field(default=24, ge=1, le=24)


class ConnectionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class InvestigationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: Literal["direct", "agentic"] = "agentic"


class SavedCollectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_historical: StrictBool
    profile: Literal["focused", "expanded"] = "focused"
    workflow: Literal["direct", "agentic"] = "direct"


class ContextChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: Literal["direct", "agentic"] | None = None
    profile: Literal["focused", "expanded"]
    expected_evidence_digest: str | None = Field(pattern=r"^[a-f0-9]{64}$")


class ProcessingApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_request_limit: int = Field(default=1, ge=1, le=3, strict=True)
    allow_external: StrictBool
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class AnalystPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    allow_external: StrictBool = False
    minimum_level: Literal[7, 12, 15]
    hourly_limit: int = Field(ge=1, le=20, strict=True)
    daily_limit: int = Field(ge=1, le=100, strict=True)
    version: int = Field(ge=0, strict=True)


class AnalystBudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_limit: int = Field(ge=1, le=200, strict=True)


class ReportReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accepted", "rejected", "follow_up"]
    note: str = Field(min_length=10, max_length=2000)
    evidence_checked: StrictBool
    analysis_id: UUID
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_sequence: int = Field(ge=0, le=2147483646, strict=True)


def create_app(settings):
    @asynccontextmanager
    async def lifespan(app):
        initialize(settings)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[urlsplit(settings.origin).hostname, "api", "localhost", "127.0.0.1"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Pydantic's default response can echo password input; never return request values.
        return JSONResponse({"detail": "Invalid request fields"}, status_code=422)

    @app.middleware("http")
    async def boundary(request, call_next):
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and request.headers.get("origin") != settings.origin
        ):
            response = JSONResponse({"detail": "Cross-origin mutation refused"}, status_code=403)
        elif request.headers.get("sec-fetch-site") == "cross-site":
            response = JSONResponse({"detail": "Cross-site API access refused"}, status_code=403)
        elif request.headers.get("content-length") and (
            not request.headers["content-length"].isdigit()
            or int(request.headers["content-length"]) > 16384
        ):
            response = JSONResponse({"detail": "Request body too large"}, status_code=413)
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    def user(request: Request):
        with connect(settings) as db:
            return auth.authenticate(db, request.cookies.get(auth.cookie_name(settings)))

    @app.get("/api/health")
    def health():
        try:
            with connect(settings) as db:
                db.execute("SELECT 1")
            return {"status": "ok"}
        except Exception:
            raise HTTPException(503, "Database unavailable") from None

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response):
        with connect(settings) as db:
            token, error = auth.sign_in(db, body.username, body.password.get_secret_value())
        if error:
            raise HTTPException(
                429 if error == "throttled" else 401,
                "Sign-in temporarily limited"
                if error == "throttled"
                else "Invalid username or password",
            )
        response.set_cookie(
            auth.cookie_name(settings),
            token,
            max_age=43200,
            httponly=True,
            secure=settings.secure,
            samesite="strict",
            path="/",
        )
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(current=Depends(user)):
        return current

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, current=Depends(user)):
        with connect(settings) as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=%s",
                (auth.digest(request.cookies[auth.cookie_name(settings)]),),
            )
            audit(db, "session.deleted", user_id=current["id"])
        response.delete_cookie(
            auth.cookie_name(settings),
            path="/",
            secure=settings.secure,
            httponly=True,
            samesite="strict",
        )
        return {"ok": True}

    @app.get("/api/connections")
    def list_connections(current=Depends(user)):
        with connect(settings) as db:
            rows = db.execute(
                f"SELECT {connections.PUBLIC_FIELDS} FROM connections ORDER BY created_at"
            ).fetchall()
        return {"connections": rows, "indexer_hosts": settings.indexer_hosts}

    @app.post("/api/connections", status_code=201)
    def add_connection(body: ConnectionInput, current=Depends(user)):
        try:
            with connect(settings) as db:
                identifier = connections.create(
                    db,
                    settings,
                    body.name.strip(),
                    body.indexer_url.strip(),
                    body.username.strip(),
                    body.password.get_secret_value(),
                    body.backfill_hours,
                    current["id"],
                )
            return {"id": identifier}
        except UniqueViolation:
            raise HTTPException(409, "This name or indexer is already connected") from None
        except (ConfigError, ValueError):
            raise HTTPException(
                400, "Invalid connection settings or disallowed indexer destination"
            ) from None
        except BackendError as exc:
            raise HTTPException(502, f"Indexer check failed: {exc.code}") from None

    @app.patch("/api/connections/{identifier}")
    def update_connection(identifier: UUID, body: ConnectionState, current=Depends(user)):
        with connect(settings) as db:
            row = db.execute(
                "UPDATE connections SET enabled=%s WHERE id=%s RETURNING id",
                (body.enabled, identifier),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Connection not found")
            audit(
                db,
                "connection.resumed" if body.enabled else "connection.paused",
                identifier,
                current["id"],
            )
        return {"ok": True}

    @app.get("/api/alerts")
    def list_alerts(
        hours: int = Query(default=24, ge=1, le=720),
        minimum: int = Query(default=0, ge=0, le=16),
        q: str = Query(default="", max_length=100),
        connection: UUID | None = None,
        before: str | None = Query(default=None, max_length=500),
        view: Literal[
            "all", "uninvestigated", "active", "needs_review", "follow_up", "reviewed", "attention"
        ] = "all",
        current=Depends(user),
    ):
        try:
            with connect(settings) as db:
                return alerts.listing(
                    db,
                    hours=hours,
                    minimum=minimum,
                    search=q,
                    connection=connection,
                    before=before,
                    view=view,
                )
        except ValueError:
            raise HTTPException(400, "Invalid alert cursor") from None

    @app.get("/api/alerts/{identifier}")
    def detail(identifier: UUID, current=Depends(user)):
        with connect(settings) as db:
            row = db.execute("SELECT * FROM alerts WHERE id=%s", (identifier,)).fetchone()
        if not row:
            raise HTTPException(404, "Alert not found")
        return row

    @app.get("/api/alerts/{identifier}/investigations")
    def investigations(identifier: UUID, current=Depends(user)):
        with connect(settings) as db:
            return {"attempts": triage.history(db, identifier)}

    @app.post("/api/alerts/{identifier}/investigations", status_code=201)
    def investigate(
        identifier: UUID, body: InvestigationInput | None = None, current=Depends(user)
    ):
        with connect(settings) as db:
            return {
                "id": triage.request_collection(
                    db, identifier, current["id"], workflow=body.workflow if body else "direct"
                )
            }

    @app.get("/api/alerts/{identifier}/investigations/{attempt_id}")
    def investigation(identifier: UUID, attempt_id: UUID, current=Depends(user)):
        with connect(settings) as db:
            return triage.detail(db, identifier, attempt_id)

    @app.post("/api/alerts/{identifier}/investigations/{attempt_id}/reuse", status_code=201)
    def reuse_investigation_collection(
        identifier: UUID, attempt_id: UUID, body: SavedCollectionInput, current=Depends(user)
    ):
        with connect(settings) as db:
            return {"id": triage.reuse_collection(db, identifier, attempt_id, body, current["id"])}

    @app.post("/api/alerts/{identifier}/investigations/{attempt_id}/context")
    def select_investigation_context(
        identifier: UUID, attempt_id: UUID, body: ContextChoice, current=Depends(user)
    ):
        with connect(settings) as db:
            return triage.choose_context(
                db,
                identifier,
                attempt_id,
                body.profile,
                body.expected_evidence_digest,
                current["id"],
                workflow=body.workflow,
            )

    @app.get("/api/agents/local/{kind}")
    def local_agent_overview(kind: Literal["correlation", "intel"], current=Depends(user)):
        with connect(settings) as db:
            return steps.tasks(db, kind)

    @app.post("/api/alerts/{identifier}/investigations/{attempt_id}/approve")
    def approve_investigation(
        identifier: UUID, attempt_id: UUID, body: ProcessingApproval, current=Depends(user)
    ):
        if not body.allow_external:
            raise HTTPException(400, "Explicit external-processing approval is required")
        with connect(settings) as db:
            triage.approve(
                db,
                identifier,
                attempt_id,
                body.evidence_digest,
                current["id"],
                model_request_limit=body.model_request_limit,
            )
        return {"ok": True}

    @app.post("/api/alerts/{identifier}/investigations/{attempt_id}/cancel")
    def cancel_investigation(identifier: UUID, attempt_id: UUID, current=Depends(user)):
        with connect(settings) as db:
            triage.cancel(db, identifier, attempt_id, current["id"])
        return {"ok": True}

    @app.get("/api/alerts/{identifier}/investigations/{attempt_id}/reviews")
    def report_reviews(
        identifier: UUID,
        attempt_id: UUID,
        before: int | None = Query(default=None, ge=1, le=2147483647),
        current=Depends(user),
    ):
        with connect(settings) as db:
            return reviews.page(db, reviews.load_attempt(db, identifier, attempt_id), before=before)

    @app.post("/api/alerts/{identifier}/investigations/{attempt_id}/reviews", status_code=201)
    def review_report(
        identifier: UUID, attempt_id: UUID, body: ReportReviewInput, current=Depends(user)
    ):
        with connect(settings) as db:
            return reviews.create(db, identifier, attempt_id, body, current["id"])

    @app.get("/api/alerts/{identifier}/investigations/{attempt_id}/export")
    def export_investigation(
        identifier: UUID,
        attempt_id: UUID,
        format: Literal["zip", "markdown"] = "zip",
        current=Depends(user),
    ):
        with connect(settings) as db:
            content, media_type, filename = exporting.build(
                db, identifier, attempt_id, current["id"], format=format
            )
        return Response(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/operations")
    def operations_status(current=Depends(user)):
        with connect(settings) as db:
            return operations.readiness(db)

    @app.get("/api/settings/analyst")
    def analyst_settings(current=Depends(user)):
        with connect(settings) as db:
            return policy.listing(db)

    @app.put("/api/settings/analyst/connections/{identifier}")
    def analyst_policy(identifier: UUID, body: AnalystPolicyInput, current=Depends(user)):
        with connect(settings) as db:
            policy.update(db, identifier, body, current["id"])
            return policy.listing(db)

    @app.put("/api/settings/analyst/budget")
    def analyst_budget(body: AnalystBudgetInput, current=Depends(user)):
        with connect(settings) as db:
            policy.lock(db)
            db.execute(
                "UPDATE analyst_settings SET daily_limit=%s WHERE singleton", (body.daily_limit,)
            )
            audit(db, "analyst.global_budget_changed", user_id=current["id"])
            return policy.listing(db)

    @app.get("/api/agents/analyst")
    def analyst_overview(
        review: Literal["all", "pending", "accepted", "rejected", "follow_up"] = "all",
        current=Depends(user),
    ):
        with connect(settings) as db:
            return {**overview.analyst(db, review), **policy.listing(db)}

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        create_app(Settings.load()),
        host="0.0.0.0",
        port=8000,
        proxy_headers=False,
        access_log=False,
    )
