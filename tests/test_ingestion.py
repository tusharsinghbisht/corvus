import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

from corvus.adapters.wazuh import WazuhAdapter
from corvus.errors import BackendError
from corvus.server.alerts import cursor, decode_cursor
from corvus.server.connections import backend_config
from corvus.server.ingestion import read_complete
from corvus.server.settings import Settings


def settings(**changes):
    values = dict(
        database_url="postgresql://unused",
        origin="http://127.0.0.1:8000",
        encryption_key=Fernet.generate_key().decode(),
        admin_username="test-admin",
        admin_password="test-only-password-not-a-secret",
        ca_file=__file__,
        indexer_hosts=["wazuh.indexer"],
    )
    return Settings(**(values | changes))


def document(identifier="test-event", timestamp=None, agent="001", level=5):
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "reference": {"backend": "wazuh", "index": "wazuh-alerts-test", "id": identifier},
        "context": {"timestamp": timestamp, "agent_id": agent, "agent_name": "test-host"},
        "source": {
            "timestamp": timestamp,
            "rule": {"id": "test-rule", "level": level, "description": "Test event"},
        },
    }


def result(events=(), truncated=False, partial=False, error=None):
    return SimpleNamespace(events=list(events), truncated=truncated, partial=partial, error=error)


class IngestionTests(unittest.TestCase):
    def test_global_adapter_query_has_no_agent_or_severity_filter(self):
        now = datetime.now(timezone.utc)
        adapter = WazuhAdapter(None)
        with patch.object(adapter, "_search", return_value=result()) as search:
            adapter.read_alert_window(start=now - timedelta(minutes=5), end=now)
        filters = search.call_args.args[1]
        self.assertEqual(len(filters), 1)
        self.assertIn("range", filters[0])
        with self.assertRaises(ValueError):
            adapter.read_alert_window(start=now, end=now)

    def test_truncated_windows_split_and_deduplicate_shared_boundaries(self):
        now = datetime.now(timezone.utc)
        calls = []

        class Backend:
            def read_alert_window(self, *, start, end):
                calls.append((start, end))
                if end - start > timedelta(minutes=1):
                    return result(truncated=True)
                return result([document("shared"), document(start.isoformat())])

        records = read_complete(Backend, now - timedelta(minutes=2), now)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(records), 3)

    def test_partial_and_dense_windows_fail_instead_of_claiming_completeness(self):
        now = datetime.now(timezone.utc)
        for response in [
            result(partial=True),
            result(error={"code": "denied"}),
            result(truncated=True),
        ]:

            class Backend:
                def read_alert_window(self, **kwargs):
                    return response

            with self.subTest(response=response), self.assertRaises(BackendError):
                read_complete(Backend, now - timedelta(microseconds=500), now)

    def test_query_budget_is_bounded(self):
        now = datetime.now(timezone.utc)

        class Backend:
            def read_alert_window(self, **kwargs):
                return result(truncated=True)

        with (
            patch("corvus.server.ingestion.MAX_WINDOWS", 2),
            self.assertRaises(BackendError) as caught,
        ):
            read_complete(Backend, now - timedelta(minutes=5), now)
        self.assertEqual(caught.exception.code, "window_budget_exhausted")

    def test_cursor_round_trip_and_malformed_shapes(self):
        row = {"id": uuid4(), "timestamp": datetime.now(timezone.utc)}
        self.assertEqual(decode_cursor(cursor(row)), (row["timestamp"], row["id"]))
        for value in [None, [1, 2], {}, ["date", 123], ["date", "bad-id"]]:
            encoded = base64.urlsafe_b64encode(json.dumps(value).encode()).decode()
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_cursor(encoded)
        with self.assertRaises(ValueError):
            decode_cursor("not-base64")

    def test_server_origin_and_indexer_allowlists(self):
        for origin in [
            "http://public.example",
            "ftp://localhost",
            "https://user:pass@example.com",
            "https://example.com/path",
        ]:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                settings(origin=origin)
        for url in [
            "https://169.254.169.254",
            "https://attacker.invalid",
            "http://wazuh.indexer:9200",
            "https://wazuh.indexer:55000",
            "https://user:pass@wazuh.indexer:9200",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                backend_config(settings(), url, "reader", "secret")
