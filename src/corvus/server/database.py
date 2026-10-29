from pathlib import Path
from uuid import uuid4

import psycopg
from argon2 import PasswordHasher
from psycopg.rows import dict_row


def connect(settings):
    return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=10)


def initialize(settings):
    with connect(settings) as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtext('corvus.schema'))")
        db.execute("CREATE TABLE IF NOT EXISTS schema_versions(version integer PRIMARY KEY)")
        version = db.execute("SELECT max(version) AS version FROM schema_versions").fetchone()[
            "version"
        ]
        if version is None:
            db.execute(Path(__file__).with_name("schema.sql").read_text())
            version = 1
        if version == 1:
            db.execute(
                Path(__file__).with_name("migrations").joinpath("002_triage.sql").read_text()
            )
        elif version != 2:
            raise ValueError("Unsupported database schema version")
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            db.execute(
                "INSERT INTO users(id,username,password_hash) VALUES(%s,%s,%s)",
                (uuid4(), settings.admin_username, PasswordHasher().hash(settings.admin_password)),
            )


def audit(db, action, target=None, user_id=None):
    db.execute(
        "INSERT INTO audit_events(user_id,action,target) VALUES(%s,%s,%s)",
        (user_id, action, str(target) if target else None),
    )
