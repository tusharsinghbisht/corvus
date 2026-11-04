"""Run INSIDE the API container: bounded, read-only index export to stdout.

Redirect stdout to a private file ON THE WAZUH HOST, never to chat or a local checkout.
No model configuration or completion is loaded. Missing/truncated data fails closed.
"""

import argparse
import json
from datetime import timedelta

from corvus.server.connections import adapter
from corvus.server.database import connect
from corvus.server.settings import Settings
from corvus.timeutil import utc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--kind", choices=["archives", "alerts"], required=True)
    args = parser.parse_args()
    start, end = utc(args.start), utc(args.end)
    if not 0 < (end - start).total_seconds() <= 3 * 86400:
        raise ValueError("Export window must be within 72 hours")
    settings = Settings.load()
    with connect(settings) as db:
        connection = db.execute("SELECT * FROM connections ORDER BY created_at LIMIT 1").fetchone()
        backend = adapter(settings, connection)
    queries = []
    seen = set()
    written = 0

    def emit(value):
        nonlocal written
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        written += len(data.encode()) + 1
        if written > 1024 * 1024 * 1024:
            raise ValueError("Private export exceeds 1 GiB bound")
        print(data, flush=True)

    def capture(lower, upper):
        if len(queries) >= 2000:
            raise ValueError("Export query budget exceeded")
        result = (
            backend.search_events(agent_id="001", start=lower, end=upper, limit=1000)
            if args.kind == "archives"
            else backend.list_alerts(agent_id="001", start=lower, end=upper, limit=1000)
        )
        queries.append(
            {
                "start": lower.isoformat(),
                "end": upper.isoformat(),
                "returned": len(result.events),
                "total": result.total,
                "partial": result.partial,
                "truncated": result.truncated,
            }
        )
        # Read-only partial searches can be retried with smaller bounded windows.
        # Never publish a partial leaf, even if it happened to return its reported total.
        if result.truncated or result.partial or result.error:
            if (upper - lower).total_seconds() <= 1:
                raise ValueError("Dense window exceeds safe export bound")
            middle = lower + (upper - lower) / 2
            capture(lower, middle)
            capture(middle, upper)
            return
        for event in result.events:
            key = tuple(event["reference"][field] for field in ("backend", "index", "id"))
            if key in seen:
                continue
            if len(seen) >= 200000:
                raise ValueError("Event export bound exceeded")
            seen.add(key)
            emit({"type": "event", "document": event})

    position = start
    while position < end:
        upper = min(position + timedelta(hours=12), end)
        capture(position, upper)
        position = upper
    emit(
        {
            "type": "manifest",
            "agent_id": "001",
            "kind": args.kind,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "events": len(seen),
            "complete_within_queries": True,
            "queries": queries,
            "limitations": [
                "Only currently retained indexed data, not proof of full native coverage.",
                "Raw telemetry may contain personal data or secrets; no model call was made.",
            ],
        }
    )


if __name__ == "__main__":
    main()
