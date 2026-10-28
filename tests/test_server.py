"""Real PostgreSQL integration tests. Set CORVUS_TEST_DATABASE_URL to a disposable DB."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_ingestion import document, result, settings

from corvus.errors import BackendError
from corvus.server import alerts
from corvus.server.api import create_app
from corvus.server.database import connect, initialize
from corvus.server.ingestion import insert_alert, poll


@unittest.skipUnless(
    os.environ.get("CORVUS_TEST_DATABASE_URL"), "Disposable PostgreSQL URL not configured"
)
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.environ["CORVUS_TEST_DATABASE_URL"]
        cls.schema = "corvus_test_" + uuid4().hex
        with psycopg.connect(cls.base) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        cls.settings = settings(
            database_url=make_conninfo(cls.base, options="-csearch_path=" + cls.schema)
        )
        initialize(cls.settings)

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.base) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def setUp(self):
        with connect(self.settings) as db:
            db.execute("TRUNCATE sessions,login_failures,audit_events,alerts,connections CASCADE")
        self.client = TestClient(create_app(self.settings), base_url=self.settings.origin)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.headers = {"Origin": self.settings.origin}

    def login(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": self.settings.admin_username,
                "password": self.settings.admin_password,
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        return response

    def connection(self):
        identifier = uuid4()
        start = datetime.now(timezone.utc) - timedelta(minutes=10)
        with connect(self.settings) as db:
            db.execute(
                "INSERT INTO connections(id,name,indexer_url,username,encrypted_password,backfill_start,checkpoint) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    identifier,
                    "Test Wazuh",
                    "https://wazuh.indexer:9200",
                    "reader",
                    self.settings.cipher.encrypt(b"private-reader-password").decode(),
                    start,
                    start,
                ),
            )
            return db.execute("SELECT * FROM connections WHERE id=%s", (identifier,)).fetchone()

    def test_data_requires_authentication_and_mutations_require_origin(self):
        for path in [
            "/api/alerts",
            "/api/connections",
            "/api/alerts/" + str(uuid4()),
            "/api/auth/me",
        ]:
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.post("/api/auth/login", json={}).status_code, 403)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.login()
        self.assertEqual(
            self.client.get("/api/alerts", headers={"Sec-Fetch-Site": "cross-site"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/alerts", headers={"Host": "attacker.invalid"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/logout", headers={"Origin": "https://attacker.invalid"}
            ).status_code,
            403,
        )

    def test_sessions_are_hashed_expire_and_logout_revokes(self):
        response = self.login()
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        token = self.client.cookies.get("corvus_session")
        with connect(self.settings) as db:
            row = db.execute("SELECT token_hash FROM sessions").fetchone()
        self.assertNotEqual(token, row["token_hash"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(
            self.client.post("/api/auth/logout", headers=self.headers).status_code, 200
        )
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.login()
        with connect(self.settings) as db:
            db.execute("UPDATE sessions SET expires_at=now()-interval '1 second'")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_validation_errors_do_not_echo_passwords(self):
        sentinel = "sensitive-input-never-echo"
        response = self.client.post(
            "/api/auth/login", json={"username": "", "password": sentinel}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(sentinel, response.text)

    def test_failed_login_throttle_is_persisted(self):
        for _ in range(10):
            response = self.client.post(
                "/api/auth/login",
                json={"username": "wrong", "password": "wrong"},
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": self.settings.admin_username,
                "password": self.settings.admin_password,
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 429)

    def test_credentials_are_encrypted_and_not_in_public_connection_response(self):
        connection = self.connection()
        self.login()
        response = self.client.get("/api/connections")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("encrypted_password", response.text)
        self.assertNotIn("private-reader-password", response.text)
        self.assertNotIn("private-reader-password", connection["encrypted_password"])
        identifier = connection["id"]
        response = self.client.patch(
            f"/api/connections/{identifier}", json={"enabled": False}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        with connect(self.settings) as db:
            self.assertFalse(
                db.execute("SELECT enabled FROM connections WHERE id=%s", (identifier,)).fetchone()[
                    "enabled"
                ]
            )

    def test_onboarding_verifies_indexer_before_saving_and_refuses_duplicate_sources(self):
        self.login()
        body = {
            "name": "New Wazuh",
            "indexer_url": "https://wazuh.indexer:9200",
            "username": "reader",
            "password": "test-reader-secret",
            "backfill_hours": 6,
        }
        with (
            patch("corvus.server.connections.Transport"),
            patch("corvus.server.connections.WazuhAdapter") as backend,
        ):
            backend.return_value.read_alert_window.return_value = result()
            response = self.client.post("/api/connections", json=body, headers=self.headers)
            self.assertEqual(response.status_code, 201)
            self.assertNotIn(body["password"], response.text)
            self.assertEqual(
                self.client.post("/api/connections", json=body, headers=self.headers).status_code,
                409,
            )
        with connect(self.settings) as db:
            row = db.execute("SELECT * FROM connections").fetchone()
            self.assertNotEqual(row["encrypted_password"], body["password"])
            self.assertEqual(
                self.settings.cipher.decrypt(row["encrypted_password"].encode()).decode(),
                body["password"],
            )
        body["indexer_url"] = "https://169.254.169.254"
        self.assertEqual(
            self.client.post("/api/connections", json=body, headers=self.headers).status_code, 400
        )

    def test_poll_is_atomic_idempotent_and_advances_only_after_complete_data(self):
        connection = self.connection()

        class Backend:
            def read_alert_window(self, **kwargs):
                return result([document("a"), document("b", agent="002")])

        self.assertEqual(poll(self.settings, connection, Backend), 2)
        self.assertEqual(poll(self.settings, connection, Backend), 0)
        with connect(self.settings) as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM alerts").fetchone()["n"], 2)
            self.assertGreater(
                db.execute("SELECT checkpoint FROM connections").fetchone()["checkpoint"],
                connection["checkpoint"],
            )

    def test_partial_results_and_transaction_failures_leave_checkpoint_unchanged(self):
        connection = self.connection()

        class Partial:
            def read_alert_window(self, **kwargs):
                return result([document("a")], partial=True)

        with self.assertRaises(BackendError):
            poll(self.settings, connection, Partial)

        class Invalid:
            def read_alert_window(self, **kwargs):
                return result([document("a"), document("bad", timestamp="bad-time")])

        with self.assertRaises(ValueError):
            poll(self.settings, connection, Invalid)
        with connect(self.settings) as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM alerts").fetchone()["n"], 0)
            self.assertEqual(
                db.execute("SELECT checkpoint FROM connections").fetchone()["checkpoint"],
                connection["checkpoint"],
            )

    def test_equal_timestamp_pagination_and_filters_preserve_all_alerts(self):
        connection = self.connection()
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.settings) as db:
            for number in range(61):
                insert_alert(
                    db,
                    connection["id"],
                    document(str(number), timestamp=now, level=12 if number < 3 else 5),
                )
            first = alerts.listing(db)
            second = alerts.listing(db, before=first["next_cursor"])
            self.assertEqual(len(first["alerts"]), 50)
            self.assertEqual(len(second["alerts"]), 11)
            self.assertEqual(len({row["id"] for row in first["alerts"] + second["alerts"]}), 61)
            self.assertEqual(first["stats"], {"total": 61, "high": 3, "agents": 1})
            self.assertEqual(alerts.listing(db, minimum=12)["stats"]["total"], 3)
        self.login()
        self.assertEqual(self.client.get("/api/alerts?before=malformed").status_code, 400)
        self.assertEqual(self.client.get("/api/alerts").json()["stats"]["total"], 61)
        identifier = first["alerts"][0]["id"]
        self.assertIn("document", self.client.get(f"/api/alerts/{identifier}").json())
