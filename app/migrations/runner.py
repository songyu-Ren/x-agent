import logging
from typing import Callable

from app.database import get_connection

logger = logging.getLogger(__name__)


def _ensure_migrations_table() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _is_applied(migration_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE id = ? LIMIT 1", (migration_id,)
    ).fetchone()
    conn.close()
    return row is not None


def _mark_applied(migration_id: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (?, datetime('now'))",
        (migration_id,),
    )
    conn.commit()
    conn.close()


def run_migrations() -> None:
    _ensure_migrations_table()

    from app.migrations.v2_schema import apply_v2_schema

    migrations: list[tuple[str, Callable[[], None]]] = [
        ("v2_schema", apply_v2_schema),
    ]

    for migration_id, fn in migrations:
        if _is_applied(migration_id):
            logger.info("Migration already applied: %s", migration_id)
            continue
        logger.info("Applying migration: %s", migration_id)
        fn()
        _mark_applied(migration_id)
        logger.info("Migration applied: %s", migration_id)

