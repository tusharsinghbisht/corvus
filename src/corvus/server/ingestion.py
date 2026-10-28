"""Bounded polling with overlap, idempotent inserts, and atomic checkpoint advancement."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..errors import BackendError
from ..timeutil import utc
from . import connections
from .database import connect

WINDOW = timedelta(minutes=5)
OVERLAP = timedelta(minutes=2)
MAX_WINDOWS = 16
MAX_DOCUMENTS = 5000


def read_complete(factory, start, end):
    pending = [(start, end)]
    documents = {}
    queries = 0
    while pending:
        queries += 1
        if queries > MAX_WINDOWS:
            raise BackendError(
                "window_budget_exhausted", "Reduce the ingestion window; checkpoint unchanged"
            )
        left, right = pending.pop()
        result = factory().read_alert_window(start=left, end=right)
        if result.partial or result.error:
            raise BackendError(
                "incomplete_ingestion", "Backend query incomplete; checkpoint unchanged"
            )
        if result.truncated:
            middle = left + (right - left) / 2
            if right - left <= timedelta(milliseconds=1):
                raise BackendError(
                    "dense_timestamp", "Too many alerts share a timestamp; checkpoint unchanged"
                )
            pending.extend([(middle, right), (left, middle)])
            continue
        for document in result.events:
            reference = document["reference"]
            documents[(reference["index"], reference["id"])] = document
        if len(documents) > MAX_DOCUMENTS:
            raise BackendError(
                "ingestion_size_limit", "Ingestion batch exceeded its bound; checkpoint unchanged"
            )
    return list(documents.values())


def insert_alert(db, connection_id, document):
    source = document["source"]
    rule = source.get("rule") if isinstance(source.get("rule"), dict) else {}
    context = document["context"]
    reference = document["reference"]
    try:
        level = int(rule.get("level", 0))
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(level, 16))
    row = db.execute(
        """
        INSERT INTO alerts(id,connection_id,native_index,native_id,timestamp,
                           agent_id,agent_name,rule_id,rule_level,title,document)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(connection_id,native_index,native_id) DO NOTHING RETURNING id
    """,
        (
            uuid4(),
            connection_id,
            reference["index"],
            reference["id"],
            utc(context.get("timestamp")),
            context.get("agent_id"),
            context.get("agent_name"),
            str(rule.get("id", "")),
            level,
            str(rule.get("description", "Wazuh alert"))[:1000],
            Jsonb(document),
        ),
    ).fetchone()
    return row is not None


def poll(settings, connection, factory=None, now=None):
    now = now or datetime.now(timezone.utc)
    checkpoint = connection["checkpoint"]
    end = min(checkpoint + WINDOW, now - timedelta(seconds=2))
    if end <= checkpoint:
        return 0
    start = max(connection["backfill_start"], checkpoint - OVERLAP)
    documents = read_complete(
        factory or (lambda: connections.adapter(settings, connection)), start, end
    )
    with connect(settings) as db:
        current = db.execute(
            "SELECT checkpoint,enabled FROM connections WHERE id=%s FOR UPDATE", (connection["id"],)
        ).fetchone()
        if not current or not current["enabled"] or current["checkpoint"] != checkpoint:
            return 0
        count = sum(insert_alert(db, connection["id"], document) for document in documents)
        db.execute(
            "UPDATE connections SET checkpoint=%s,last_sync_at=now(),last_error=NULL WHERE id=%s",
            (end, connection["id"]),
        )
    return count
