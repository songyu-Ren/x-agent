from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List

from app.models import EvidenceItem


class SourcePlugin(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> List[EvidenceItem]:
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

