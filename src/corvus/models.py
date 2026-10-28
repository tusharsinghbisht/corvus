"""Small shared contracts. Documents preserve both source data and normalized context."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class SearchResult:
    events: list[dict]
    query: dict
    total: int
    total_relation: str
    truncated: bool = False
    partial: bool = False
    warnings: list[str] = field(default_factory=list)
    error: dict | None = None

    def metadata(self):
        return {
            "status": "partial" if self.partial or self.truncated else "ok",
            "query": self.query,
            "returned": len(self.events),
            "total": self.total,
            "total_relation": self.total_relation,
            "truncated": self.truncated,
            "partial": self.partial,
            "warnings": self.warnings,
            "error": self.error,
            "event_references": [event["reference"] for event in self.events],
        }


class EvidenceBackend(Protocol):
    def get_alert(self, index: str, alert_id: str) -> dict: ...

    def search_events(
        self,
        *,
        agent_id: str,
        start: datetime,
        end: datetime,
        limit: int = 500,
        channel: str | None = None,
        process_guids: list[str] | None = None,
    ) -> SearchResult: ...
