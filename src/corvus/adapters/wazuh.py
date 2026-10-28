"""Read-only Wazuh indexer adapter with bounded, snapshot-based pagination."""

import re
from datetime import datetime
from urllib.parse import quote

from ..errors import BackendError
from ..models import SearchResult
from ..timeutil import iso, utc

ALERTS = "wazuh-alerts-*"
ARCHIVES = "wazuh-archives-*"
MAX_EVENTS = 1000
PAGE_SIZE = 100


def _path(source, *keys):
    for key in keys:
        if not isinstance(source, dict):
            return None
        source = source.get(key)
    return source


def _field(mapping, name):
    if not isinstance(mapping, dict):
        return None
    value = next((v for k, v in mapping.items() if k.casefold() == name.casefold()), None)
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def normalize(source):
    """Map Wazuh/Windows fields without altering or discarding the original event."""
    eventdata = _path(source, "data", "win", "eventdata")
    return {
        "timestamp": source.get("timestamp"),
        "agent_id": _path(source, "agent", "id"),
        "agent_name": _path(source, "agent", "name"),
        "channel": _path(source, "data", "win", "system", "channel"),
        "event_id": _path(source, "data", "win", "system", "eventID"),
        "user": _field(eventdata, "user"),
        "process_guid": _field(eventdata, "processGuid"),
        "parent_process_guid": _field(eventdata, "parentProcessGuid"),
        "process_id": _field(eventdata, "processId"),
        "logon_guid": _field(eventdata, "logonGuid"),
    }


def document(hit: dict) -> dict:
    if (
        not isinstance(hit, dict)
        or not isinstance(hit.get("_source"), dict)
        or not isinstance(hit.get("_index"), str)
        or not isinstance(hit.get("_id"), str)
    ):
        raise BackendError("invalid_response", "Backend returned an invalid event document")
    return {
        "reference": {"backend": "wazuh", "index": hit["_index"], "id": hit["_id"]},
        "context": normalize(hit["_source"]),
        "source": hit["_source"],
    }


class WazuhAdapter:
    def __init__(self, transport):
        self.transport = transport

    def get_event(self, index: str, event_id: str) -> dict:
        if not isinstance(index, str) or not re.fullmatch(
            r"wazuh-(?:alerts|archives)-[A-Za-z0-9_.-]+", index
        ):
            raise ValueError("Event index must be a concrete Wazuh alert or archive index")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 512:
            raise ValueError("A non-empty event ID of at most 512 characters is required")
        result = self.transport.request(
            "GET", f"/{quote(index, safe='')}/_doc/{quote(event_id, safe='')}"
        )
        if result.get("found") is False:
            raise BackendError("not_found", "Requested event does not exist", 404)
        return document(result)

    def get_alert(self, index: str, alert_id: str) -> dict:
        if not isinstance(index, str) or not index.startswith("wazuh-alerts-"):
            raise ValueError("Alert index must be a concrete wazuh-alerts-* index")
        return self.get_event(index, alert_id)

    def search_events(
        self,
        *,
        agent_id: str,
        start: datetime,
        end: datetime,
        limit: int = 500,
        channel: str | None = None,
        process_guids: list[str] | None = None,
    ) -> SearchResult:
        filters = self._scope(agent_id, start, end, limit)
        if channel:
            filters.append({"term": {"data.win.system.channel": channel}})
        if process_guids:
            guid_pattern = r"\{?[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}\}?"
            if len(process_guids) > 4 or any(
                not isinstance(guid, str)
                or not re.fullmatch(guid_pattern, guid)
                or guid.startswith("{") != guid.endswith("}")
                for guid in process_guids
            ):
                raise ValueError("Expected at most four canonical process GUIDs")
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"terms": {"data.win.eventdata.processGuid": process_guids}},
                            {"terms": {"data.win.eventdata.parentProcessGuid": process_guids}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        return self._search(ARCHIVES, filters, limit)

    def list_alerts(
        self,
        *,
        agent_id: str,
        start: datetime,
        end: datetime,
        limit: int = 20,
        marker: str | None = None,
    ) -> SearchResult:
        filters = self._scope(agent_id, start, end, limit)
        if marker:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", marker):
                raise ValueError(
                    "Marker must contain 1-128 letters, digits, underscores, or hyphens"
                )
            filters.append(
                {
                    "bool": {
                        "should": [
                            {
                                "wildcard": {
                                    "data.win.eventdata.commandLine": {"value": "*" + marker + "*"}
                                }
                            },
                            {
                                "wildcard": {
                                    "data.win.eventdata.scriptBlockText": {
                                        "value": "*" + marker + "*"
                                    }
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        return self._search(ALERTS, filters, limit, descending=True)

    @staticmethod
    def _scope(agent_id, start, end, limit):
        if not isinstance(agent_id, str) or not re.fullmatch(r"\d{3,8}", agent_id):
            raise ValueError("A Wazuh agent ID such as 001 is required")
        start, end = utc(start), utc(end)
        if end <= start or (end - start).total_seconds() > 24 * 3600:
            raise ValueError("Search window must be positive and no longer than 24 hours")
        if type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
            raise ValueError(f"Event limit must be between 1 and {MAX_EVENTS}")
        return [
            {"term": {"agent.id": agent_id}},
            {"range": {"timestamp": {"gte": iso(start), "lte": iso(end)}}},
        ]

    def _search(self, pattern: str, filters: list, limit: int, descending=False) -> SearchResult:
        query = {
            "size": min(limit, PAGE_SIZE),
            "track_total_hits": True,
            "sort": [{"timestamp": "desc" if descending else "asc"}],
            "query": {"bool": {"filter": filters}},
        }
        audit = {"indices": pattern, "body": query, "limit": limit, "snapshot": "scroll"}
        response = self.transport.request(
            "POST",
            "/" + pattern + "/_search?scroll=1m&allow_no_indices=false&ignore_unavailable=false",
            query,
        )
        scroll_id = response.get("_scroll_id")
        result = SearchResult([], audit, 0, "eq")
        seen = set()
        try:
            total = response.get("hits", {}).get("total")
            if (
                not isinstance(total, dict)
                or type(total.get("value")) is not int
                or total["value"] < 0
            ):
                raise BackendError("invalid_response", "Backend omitted the total-hit count")
            result.total = total["value"]
            result.total_relation = total.get("relation", "gte")
            for _ in range(20):
                if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
                    result.partial = True
                    result.warnings.append(
                        "Backend timed out or reported failed shards; results are incomplete"
                    )
                hits = response.get("hits", {}).get("hits")
                if not isinstance(hits, list):
                    raise BackendError("invalid_response", "Backend omitted the event list")
                duplicate = False
                for hit in hits:
                    event = document(hit)
                    key = (event["reference"]["index"], event["reference"]["id"])
                    if key in seen:
                        duplicate = True
                        continue
                    seen.add(key)
                    result.events.append(event)
                    if len(result.events) >= limit:
                        break
                if duplicate:
                    result.partial = True
                    result.warnings.append("Duplicate documents encountered while paginating")
                    break
                if not hits or len(result.events) >= limit:
                    break
                if result.total_relation == "eq" and len(result.events) >= result.total:
                    break
                if not scroll_id:
                    result.partial = True
                    result.warnings.append("Backend omitted its pagination cursor")
                    break
                try:
                    response = self.transport.request(
                        "POST",
                        "/_search/scroll",
                        {
                            "scroll": "1m",
                            "scroll_id": scroll_id,
                        },
                    )
                    scroll_id = response.get("_scroll_id", scroll_id)
                except BackendError as exc:
                    result.partial = True
                    result.error = exc.as_dict()
                    break
            else:
                result.partial = True
                result.warnings.append("Pagination budget exhausted")
            result.truncated = result.total_relation != "eq" or len(result.events) < result.total
            return result
        finally:
            if scroll_id:
                try:
                    self.transport.request("DELETE", "/_search/scroll", {"scroll_id": [scroll_id]})
                except BackendError:
                    # A short TTL also bounds abandoned cursors. This does not
                    # change the completeness of already retrieved evidence.
                    result.warnings.append(
                        "Pagination cursor cleanup failed; it expires after one minute"
                    )
