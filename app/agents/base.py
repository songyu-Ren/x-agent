import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.models import AgentLog, Materials

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def run(self, input_data: Any) -> Any:
        pass

    def _summarize(self, data: Any) -> str:
        try:
            if data is None:
                return "None"
            if isinstance(data, Materials):
                return (
                    f"Materials(git_commits={len(data.git_commits)}, "
                    f"notes={len(data.notes)}, links={len(data.links)}, errors={len(data.errors)})"
                )
            if isinstance(data, BaseModel):
                return data.__class__.__name__
            if isinstance(data, list | tuple):
                return f"{type(data).__name__}(len={len(data)})"
            return f"{type(data).__name__}"
        except Exception:
            return "Unserializable"

    def execute(self, input_data: Any) -> tuple[Any, AgentLog]:
        start_ts = datetime.now(UTC)
        error_msg = None
        output_data = None
        warnings: list[str] = []

        try:
            logger.info("[%s] Starting", self.name)
            output_data = self.run(input_data)
        except Exception as e:
            logger.error("[%s] Failed", self.name, exc_info=True)
            error_msg = str(e)[:500]
            # Re-raise or return None? Orchestrator should handle execution flow.
            # We'll re-raise so orchestrator sees it immediately.
            raise e
        finally:
            end_ts = datetime.now(UTC)
            duration_ms = int((end_ts - start_ts).total_seconds() * 1000)
            input_summary = self._summarize(input_data)
            output_summary = self._summarize(output_data)

            if isinstance(output_data, Materials):
                if output_data.errors:
                    warnings.extend([w[:200] for w in output_data.errors])
            else:
                errors = getattr(output_data, "errors", None) if output_data is not None else None
                if isinstance(errors, list):
                    warnings.extend([str(w)[:200] for w in errors])

            log = AgentLog(
                agent_name=self.name,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_ms=duration_ms,
                input_summary=input_summary,
                output_summary=output_summary,
                errors=error_msg,
                warnings=warnings,
            )
            try:
                from app.observability.metrics import AGENT_LATENCY_SECONDS

                AGENT_LATENCY_SECONDS.labels(agent=self.name).observe(duration_ms / 1000.0)
            except Exception:
                pass
            logger.info("[%s] Finished in %sms", self.name, duration_ms)

        return output_data, log
