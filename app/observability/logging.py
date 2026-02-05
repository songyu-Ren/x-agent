from __future__ import annotations

import json
import logging
import logging.config
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_draft_id: ContextVar[str | None] = ContextVar("draft_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def get_run_id() -> str | None:
    return _run_id.get()


def get_draft_id() -> str | None:
    return _draft_id.get()


def get_user_id() -> str | None:
    return _user_id.get()


def bind_correlation_ids(
    *,
    request_id: str | None = None,
    run_id: str | None = None,
    draft_id: str | None = None,
    user_id: str | None = None,
) -> dict[ContextVar[str | None], Any]:
    tokens: dict[ContextVar[str | None], Any] = {}
    if request_id is not None:
        tokens[_request_id] = _request_id.set(request_id)
    if run_id is not None:
        tokens[_run_id] = _run_id.set(run_id)
    if draft_id is not None:
        tokens[_draft_id] = _draft_id.set(draft_id)
    if user_id is not None:
        tokens[_user_id] = _user_id.set(user_id)
    return tokens


def reset_correlation_ids(tokens: dict[ContextVar[str | None], Any]) -> None:
    for var, token in tokens.items():
        try:
            var.reset(token)
        except Exception:
            continue


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
        request_id = get_request_id()
        run_id = get_run_id()
        draft_id = get_draft_id()
        user_id = get_user_id()
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        if request_id:
            payload["request_id"] = request_id
        if run_id:
            payload["run_id"] = run_id
        if draft_id:
            payload["draft_id"] = draft_id
        if user_id:
            payload["user_id"] = user_id

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
