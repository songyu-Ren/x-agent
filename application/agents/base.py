from __future__ import annotations

from abc import ABC, abstractmethod

from application.agents.types import RunStateDelta
from domain.models import RunState


class BaseAgent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def run(self, state: RunState) -> RunStateDelta: ...
