from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import UTC, datetime
from typing import Any


def _get_trace_context() -> tuple[str | None, str | None]:
    try:
        from opentelemetry.trace import get_current_span

        span = get_current_span()
        if not span:
            return None, None
        ctx = span.get_span_context()
        if not ctx or not ctx.is_valid:
            return None, None
        trace_id = f"{ctx.trace_id:032x}"
        span_id = f"{ctx.span_id:016x}"
        return trace_id, span_id
    except Exception:
        return None, None


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        trace_id, span_id = _get_trace_context()
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        for k, v in record.__dict__.items():
            if k in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
            }:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except Exception:
                payload[k] = repr(v)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    *,
    log_level: str,
    log_format: str,
    service_name: str,
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    if log_format.lower() == "json":
        formatter = JsonFormatter(service_name=service_name)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(level)

        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(name)
            logger.handlers = [handler]
            logger.setLevel(level)
            logger.propagate = False
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
