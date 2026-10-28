import unittest
from datetime import datetime, timedelta, timezone

from corvus.adapters.wazuh import WazuhAdapter, normalize
from corvus.errors import BackendError

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def hit(identifier):
    return {
        "_index": "wazuh-archives-4.x-2026.10.28",
        "_id": str(identifier),
        "_source": {"timestamp": NOW.isoformat(), "agent": {"id": "001", "name": "test-host"}},
    }


def page(ids, total, cursor="cursor"):
    return {
        "_scroll_id": cursor,
        "_shards": {"failed": 0},
        "hits": {"total": {"value": total, "relation": "eq"}, "hits": [hit(i) for i in ids]},
    }


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class WazuhTests(unittest.TestCase):
    def search(self, client, **kwargs):
        return WazuhAdapter(client).search_events(
            agent_id="001",
            start=NOW - timedelta(minutes=15),
            end=NOW,
            **kwargs,
        )

    def test_scroll_pagination_and_cleanup(self):
        client = FakeTransport(page([1, 2], 3), page([3], 3), {"succeeded": True})
        result = self.search(client)
        self.assertEqual(len(result.events), 3)
        self.assertFalse(result.partial or result.truncated)
        self.assertEqual(client.calls[-1][0:2], ("DELETE", "/_search/scroll"))
        self.assertEqual(result.events[0]["context"]["agent_id"], "001")

    def test_cap_is_explicit(self):
        result = self.search(FakeTransport(page([1, 2], 8), {}), limit=2)
        self.assertTrue(result.truncated)
        self.assertEqual(result.metadata()["status"], "partial")
        self.assertEqual(result.total, 8)

    def test_empty_success_differs_from_permission_failure(self):
        result = self.search(FakeTransport(page([], 0), {}))
        self.assertEqual(result.total, 0)
        self.assertFalse(result.partial or result.truncated)
        with self.assertRaises(BackendError):
            self.search(FakeTransport(BackendError("permission_denied", "Denied", 403)))

    def test_scroll_failure_preserves_prior_evidence(self):
        result = self.search(FakeTransport(page([1], 3), BackendError("timeout", "Timed out"), {}))
        self.assertEqual(len(result.events), 1)
        self.assertTrue(result.partial and result.truncated)
        self.assertEqual(result.error["code"], "timeout")

    def test_failed_shards_are_partial(self):
        first = page([1], 1)
        first["_shards"]["failed"] = 1
        result = self.search(FakeTransport(first, {}))
        self.assertTrue(result.partial)

    def test_cleanup_failure_is_visible(self):
        result = self.search(FakeTransport(page([1], 1), BackendError("timeout", "Timed out")))
        self.assertTrue(result.warnings)
        self.assertFalse(result.partial)

    def test_missing_cursor_and_duplicate_pages_are_visible(self):
        result = self.search(FakeTransport(page([1], 2, cursor=None)))
        self.assertTrue(result.partial)
        result = self.search(FakeTransport(page([1], 3), page([1], 3), {}))
        self.assertTrue(result.partial)
        self.assertEqual(len(result.events), 1)

    def test_scope_and_index_validation(self):
        adapter = WazuhAdapter(FakeTransport())
        for agent in ["*", "", "001 OR 002"]:
            with self.subTest(agent=agent), self.assertRaises(ValueError):
                adapter.search_events(agent_id=agent, start=NOW, end=NOW + timedelta(minutes=1))
        with self.assertRaises(ValueError):
            adapter.search_events(agent_id="001", start=NOW, end=NOW + timedelta(hours=25))
        for index in [".opendistro_security", "wazuh-alerts-*", "wazuh-alerts-x/_search"]:
            with self.subTest(index=index), self.assertRaises(ValueError):
                adapter.get_event(index, "id")

    def test_guid_filters_are_bounded_and_validated(self):
        adapter = WazuhAdapter(FakeTransport())
        for guid in ["-" * 36, "{11111111-1111-1111-1111-111111111111", "arbitrary text"]:
            with self.subTest(guid=guid), self.assertRaises(ValueError):
                adapter.search_events(
                    agent_id="001", start=NOW - timedelta(minutes=1), end=NOW, process_guids=[guid]
                )

    def test_event_ids_are_encoded(self):
        client = FakeTransport(hit("a/b"))
        WazuhAdapter(client).get_event("wazuh-archives-4.x-2026.10.28", "a/b")
        self.assertTrue(client.calls[0][1].endswith("/a%2Fb"))

    def test_normalization_preserves_case_variations_and_missing_sources(self):
        source = {"data": {"win": {"eventdata": {"ProcessGuid": "{test}", "User": "example"}}}}
        self.assertEqual(normalize(source)["process_guid"], "{test}")
        self.assertIsNone(normalize({"data": None})["process_guid"])
        self.assertEqual(source["data"]["win"]["eventdata"]["User"], "example")
