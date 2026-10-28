from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from ..adapters.wazuh import WazuhAdapter
from ..config import Config
from ..errors import BackendError
from ..transport import Transport
from .database import audit

PUBLIC_FIELDS = "id,name,indexer_url,username,enabled,backfill_start,checkpoint,last_sync_at,last_error,created_at"


def backend_config(settings, url, username, password):
    parsed = urlsplit(url)
    if parsed.hostname not in settings.indexer_hosts or parsed.port not in (None, 443, 9200, 19200):
        raise ValueError("Indexer destination is not in the operator allowlist")
    return Config(
        indexer_url=url,
        username=username,
        password=password,
        ca_file=Path(settings.ca_file),
        allow_legacy_ca=settings.allow_legacy_ca,
        tls_server_name=settings.tls_server_name,
        timeout_seconds=15,
    )


def adapter(settings, connection):
    password = settings.cipher.decrypt(connection["encrypted_password"].encode()).decode()
    return WazuhAdapter(
        Transport(
            backend_config(settings, connection["indexer_url"], connection["username"], password)
        )
    )


def create(db, settings, name, url, username, password, backfill_hours, user_id):
    config = backend_config(settings, url, username, password)
    now = datetime.now(timezone.utc)
    result = WazuhAdapter(Transport(config)).read_alert_window(
        start=now - timedelta(minutes=15), end=now, limit=1
    )
    if result.partial or result.error:
        raise BackendError("incomplete_probe", "Indexer health query was incomplete")
    identifier = uuid4()
    start = now - timedelta(hours=backfill_hours)
    encrypted = settings.cipher.encrypt(password.encode()).decode()
    db.execute(
        """
        INSERT INTO connections(id,name,indexer_url,username,encrypted_password,backfill_start,checkpoint)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
    """,
        (identifier, name, url.rstrip("/"), username, encrypted, start, start),
    )
    audit(db, "connection.created", identifier, user_id)
    return identifier
