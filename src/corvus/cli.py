"""Evidence collection and advisory analysis. No arbitrary queries or response execution."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import __version__
from .adapters.wazuh import WazuhAdapter
from .config import load_config
from .errors import BackendError, ConfigError
from .evidence import collect
from .providers import ModelError
from .reporting.cli import COMMANDS, add_commands, run_command
from .storage import save_private
from .timeutil import utc
from .transport import Transport


def parser():
    root = argparse.ArgumentParser(prog="corvus", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument(
        "--config", help="Private connection JSON (default: ~/.config/corvus/config.json)"
    )
    commands = root.add_subparsers(dest="command", required=True)
    alerts = commands.add_parser("alerts", help="List recent alerts for one agent")
    alerts.add_argument("--agent-id", required=True)
    alerts.add_argument("--since-minutes", type=int, default=30)
    alerts.add_argument("--limit", type=int, default=20)
    alerts.add_argument(
        "--marker", help="Optional literal lab marker in a command line or script block"
    )
    events = commands.add_parser("events", help="Search bounded archive telemetry for one agent")
    events.add_argument("--agent-id", required=True)
    events.add_argument("--start", required=True, help="ISO-8601 timestamp including timezone")
    events.add_argument("--end", required=True, help="ISO-8601 timestamp including timezone")
    events.add_argument("--limit", type=int, default=100)
    events.add_argument("--channel")
    events.add_argument("--out", help="Write private JSON instead of printing event contents")
    event = commands.add_parser(
        "event", help="Retrieve one alert or archive event by its full reference"
    )
    event.add_argument("--index", required=True)
    event.add_argument("--id", required=True)
    event.add_argument("--out")
    case = commands.add_parser(
        "collect", help="Collect an alert and surrounding evidence; no threat verdict"
    )
    case.add_argument("--index", required=True, help="Concrete alert index, not a wildcard")
    case.add_argument("--id", required=True, help="Source-native document ID")
    case.add_argument(
        "--window-minutes", type=int, default=15, help="Context on each side of alert time"
    )
    case.add_argument(
        "--ancestry-hours", type=int, default=6, help="GUID pivot lookback; 0 disables it"
    )
    case.add_argument("--limit", type=int, default=500, help="Maximum events per query, up to 1000")
    case.add_argument(
        "--out",
        required=True,
        help="New private evidence bundle; existing files are not overwritten",
    )
    add_commands(commands)
    return root


def _print(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in COMMANDS:
            return run_command(args)
        if args.command == "alerts" and not 1 <= args.since_minutes <= 1440:
            raise ValueError("Alert lookback must be between 1 and 1440 minutes")
        config = load_config(args.config)
        transport = Transport(config)
        adapter = WazuhAdapter(transport)
        if args.command == "alerts":
            end = datetime.now(timezone.utc)
            result = adapter.list_alerts(
                agent_id=args.agent_id,
                start=end - timedelta(minutes=args.since_minutes),
                end=end,
                limit=args.limit,
                marker=args.marker,
            )
            _print(
                {
                    "search": result.metadata(),
                    "alerts": [
                        {
                            "reference": event["reference"],
                            "timestamp": event["source"].get("timestamp"),
                            "agent": event["source"].get("agent"),
                            "rule": event["source"].get("rule"),
                        }
                        for event in result.events
                    ],
                }
            )
            return 2 if result.partial or result.truncated else 0
        if args.command == "events":
            result = adapter.search_events(
                agent_id=args.agent_id,
                start=utc(args.start),
                end=utc(args.end),
                limit=args.limit,
                channel=args.channel,
            )
            data = {"search": result.metadata(), "events": result.events}
            if args.out:
                _print(
                    {"output": str(save_private(args.out, data)), "returned": len(result.events)}
                )
            else:
                _print(data)
            return 2 if result.partial or result.truncated else 0
        if args.command == "event":
            data = adapter.get_event(args.index, args.id)
            if args.out:
                _print({"output": str(save_private(args.out, data))})
            else:
                _print(data)
            return 0
        bundle = collect(
            adapter,
            index=args.index,
            alert_id=args.id,
            window_minutes=args.window_minutes,
            ancestry_hours=args.ancestry_hours,
            limit=args.limit,
        )
        bundle["connection"] = {
            "indexer_url": config.indexer_url,
            "principal": config.username,
            "tls_server_name": config.tls_server_name,
            "legacy_ca_compatibility": config.allow_legacy_ca,
        }
        bundle["backend_requests"] = transport.audit
        output = save_private(args.out, bundle)
        _print(
            {
                "output": str(output),
                "collection_id": bundle["collection_id"],
                "status": bundle["status"],
                "events": len(bundle["events"]),
                "gaps": [gap["code"] for gap in bundle["gaps"]],
            }
        )
        return 2 if bundle["status"] == "partial" else 0
    except ModelError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    except BackendError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
