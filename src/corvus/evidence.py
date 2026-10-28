"""Backend-independent evidence collection. No threat verdicts or response actions."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from . import __version__
from .errors import BackendError
from .models import EvidenceBackend
from .timeutil import iso, utc


def _collect_query(backend: EvidenceBackend, bundle: dict, name: str, **scope):
    """Preserve successful evidence and distinguish query failures from empty results."""
    try:
        result = backend.search_events(
            agent_id=bundle["entities"]["agent_id"],
            limit=bundle["scope"]["limit_per_query"],
            **scope,
        )
    except BackendError as exc:
        bundle["status"] = "partial"
        bundle["queries"].append(
            {
                "name": name,
                "status": "error",
                "error": exc.as_dict(),
                "scope": {
                    "agent_id": bundle["entities"]["agent_id"],
                    "limit": bundle["scope"]["limit_per_query"],
                    **{
                        key: iso(value) if isinstance(value, datetime) else value
                        for key, value in scope.items()
                    },
                },
            }
        )
        bundle["gaps"].append({"code": exc.code, "query": name, "message": str(exc)})
        return
    bundle["queries"].append({"name": name, **result.metadata()})
    if result.partial or result.truncated:
        bundle["status"] = "partial"
        bundle["gaps"].append(
            {
                "code": "incomplete_results",
                "query": name,
                "message": "Query was truncated or returned incomplete evidence",
            }
        )
    seen = {(e["reference"]["index"], e["reference"]["id"]) for e in bundle["events"]}
    for event in result.events:
        key = (event["reference"]["index"], event["reference"]["id"])
        if key not in seen:
            seen.add(key)
            bundle["events"].append(event)


def _collect_ancestry(backend: EvidenceBackend, bundle: dict, timestamp: datetime, end: datetime):
    context = bundle["entities"]
    values = [context.get("process_guid"), context.get("parent_process_guid")]
    if any(value is not None and not isinstance(value, str) for value in values):
        bundle["status"] = "partial"
        bundle["gaps"].append(
            {"code": "invalid_process_guid", "message": "Source GUIDs are not strings"}
        )
        return
    guids = list(dict.fromkeys(value for value in values if value))
    hours = bundle["scope"]["ancestry_lookback_hours"]
    if not guids or not hours:
        bundle["gaps"].append(
            {
                "code": "ancestry_not_queried",
                "message": "Alert lacks process GUIDs or ancestry lookback was disabled",
            }
        )
        return
    try:
        _collect_query(
            backend,
            bundle,
            "process_guid_pivot",
            start=timestamp - timedelta(hours=hours),
            end=end,
            process_guids=guids,
        )
    except ValueError:
        bundle["status"] = "partial"
        bundle["gaps"].append(
            {
                "code": "invalid_process_guid",
                "message": "Source GUIDs could not be used for a safe pivot",
            }
        )
    parent = context.get("parent_process_guid")
    if parent and not any(
        event["context"].get("process_guid") == parent
        and str(event["context"].get("event_id")) == "1"
        for event in bundle["events"]
    ):
        bundle["gaps"].append(
            {
                "code": "parent_creation_not_found",
                "message": "Parent creation was not retrieved within the configured scope",
            }
        )


def collect(
    backend: EvidenceBackend,
    *,
    index: str,
    alert_id: str,
    window_minutes: int = 15,
    ancestry_hours: int = 6,
    limit: int = 500,
) -> dict:
    """Retrieve one alert, its surrounding activity, and an optional process-GUID pivot."""
    if type(window_minutes) is not int or not 1 <= window_minutes <= 60:
        raise ValueError("Context window must be between 1 and 60 minutes on either side")
    if type(ancestry_hours) is not int or not 0 <= ancestry_hours <= 23:
        raise ValueError("Ancestry lookback must be between 0 and 23 hours")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Event limit must be between 1 and 1000 per query")
    started = datetime.now(timezone.utc)
    alert = backend.get_alert(index, alert_id)
    context = alert["context"]
    if not context.get("agent_id"):
        raise ValueError("Alert has no agent ID; refusing an unscoped evidence search")
    timestamp = utc(context.get("timestamp"))
    start = timestamp - timedelta(minutes=window_minutes)
    end = timestamp + timedelta(minutes=window_minutes)
    bundle = {
        "schema_version": "0.1",
        "collection_id": str(uuid4()),
        "started_at": iso(started),
        "completed_at": None,
        "status": "collected",
        "collector": {"name": "corvus", "version": __version__, "mode": "read_only"},
        "alert": alert,
        "entities": context,
        "scope": {
            "agent_id": context["agent_id"],
            "start": iso(start),
            "end": iso(end),
            "ancestry_lookback_hours": ancestry_hours,
            "limit_per_query": limit,
            "time_field": "timestamp",
            "as_of": iso(started),
        },
        "queries": [],
        "events": [],
        "gaps": [],
        "limitations": [
            "Collection is not a threat verdict or a completed investigation.",
            "Search uses indexed timestamps; source event times remain in the original events.",
            "Only collected, retained events are available; an empty search does not prove absence.",
            "Source exclusions, retention coverage, and unavailable log sources are not automatically measured.",
        ],
    }
    if end > started:
        bundle["status"] = "partial"
        bundle["gaps"].append(
            {
                "code": "context_window_not_elapsed",
                "message": "The requested post-alert window has not elapsed; this is a point-in-time collection",
            }
        )
    _collect_query(backend, bundle, "surrounding_activity", start=start, end=end)
    _collect_ancestry(backend, bundle, timestamp, end)

    def order(event):
        try:
            return utc(event["context"].get("timestamp"))
        except ValueError:
            bundle["gaps"].append(
                {"code": "invalid_event_timestamp", "reference": event["reference"]}
            )
            return datetime.max.replace(tzinfo=timezone.utc)

    bundle["events"].sort(key=order)
    bundle["completed_at"] = iso(datetime.now(timezone.utc))
    return bundle
