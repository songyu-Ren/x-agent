from __future__ import annotations

from datetime import UTC, datetime

from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker


def get_config(key: str) -> dict | None:
    with get_sessionmaker()() as session:
        return db.get_app_config(session, key)


def set_config(key: str, value: dict) -> None:
    with get_sessionmaker()() as session:
        db.set_app_config(session, key, value)
        session.commit()


def get_bool(key: str, default: bool) -> bool:
    raw = get_config(key)
    if not raw:
        return default
    value = raw.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    if isinstance(value, int):
        return value != 0
    return default


def get_int(key: str, default: int) -> int:
    raw = get_config(key)
    if not raw:
        return default
    value = raw.get("value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except Exception:
            return default
    return default


def get_str(key: str, default: str) -> str:
    raw = get_config(key)
    if not raw:
        return default
    value = raw.get("value")
    if isinstance(value, str):
        return value
    return default


def set_simple(key: str, value: bool | int | str) -> None:
    payload = {"value": value, "updated_at": datetime.now(UTC).isoformat()}
    set_config(key, payload)
