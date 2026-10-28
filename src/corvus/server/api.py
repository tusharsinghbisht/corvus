"""Authenticated API for the live alert queue. There are no model/action routes yet."""

from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..errors import BackendError, ConfigError
from . import alerts, auth, connections
from .database import audit, connect, initialize
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
        current=Depends(user),
    ):
        try:
            with connect(settings) as db:
                return alerts.listing(
                    db, hours=hours, minimum=minimum, search=q, connection=connection, before=before
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
