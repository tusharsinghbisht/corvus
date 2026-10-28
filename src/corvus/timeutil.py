"""Timezone-aware timestamps shared by adapters and collection workflows."""

from datetime import datetime, timezone


def utc(value: str | datetime) -> datetime:
    try:
        result = (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str)
            else value
        )
        if not isinstance(result, datetime) or result.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected an ISO-8601 timestamp with a timezone") from exc


def iso(value: datetime) -> str:
    return utc(value).isoformat().replace("+00:00", "Z")
