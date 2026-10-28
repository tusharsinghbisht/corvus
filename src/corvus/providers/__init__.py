"""Small provider-neutral completion contract; providers receive no backend tools."""

from dataclasses import dataclass
from typing import Protocol


class ModelError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelReply:
    content: str
    model: str
    usage: dict


class AnalystModel(Protocol):
    def complete(self, messages: list[dict]) -> ModelReply: ...
