from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.models import EvidenceItem


class SourcePlugin(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[EvidenceItem]:
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(UTC)
