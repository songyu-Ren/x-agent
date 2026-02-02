import logging

from app.database import get_connection

logger = logging.getLogger(__name__)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _ensure_column(conn, table: str, column: str, ddl_type: str) -> None:
    if _column_exists(conn, table, column):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def apply_v2_schema() -> None:
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        if not _table_exists(conn, "runs"):
            conn.execute(
                """
                CREATE TABLE runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    duration_ms INTEGER,
                    status TEXT NOT NULL,
                    agent_logs_json TEXT,
                    last_error TEXT
                )
                """
            )
        else:
            _ensure_column(conn, "runs", "finished_at", "TIMESTAMP")
            _ensure_column(conn, "runs", "duration_ms", "INTEGER")

        if not _table_exists(conn, "drafts"):
            conn.execute(
                """
                CREATE TABLE drafts (
                    token TEXT PRIMARY KEY,
                    run_id TEXT,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    token_consumed INTEGER DEFAULT 0,
                    consumed_at TIMESTAMP,
                    thread_enabled INTEGER DEFAULT 0,
                    thread_plan_json TEXT,
                    tweets_json TEXT,
                    published_tweet_ids_json TEXT,
                    materials_json TEXT,
                    topic_plan_json TEXT,
                    style_profile_json TEXT,
                    candidates_json TEXT,
                    edited_draft_json TEXT,
                    policy_report_json TEXT,
                    final_text TEXT,
                    tweet_id TEXT,
                    last_error TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                )
                """
            )
        else:
            _ensure_column(conn, "drafts", "token_consumed", "INTEGER DEFAULT 0")
            _ensure_column(conn, "drafts", "consumed_at", "TIMESTAMP")
            _ensure_column(conn, "drafts", "thread_enabled", "INTEGER DEFAULT 0")
            _ensure_column(conn, "drafts", "thread_plan_json", "TEXT")
            _ensure_column(conn, "drafts", "tweets_json", "TEXT")
            _ensure_column(conn, "drafts", "published_tweet_ids_json", "TEXT")
            _ensure_column(conn, "drafts", "style_profile_json", "TEXT")

        if not _table_exists(conn, "posts"):
            conn.execute(
                """
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT UNIQUE,
                    content TEXT,
                    posted_at TIMESTAMP NOT NULL
                )
                """
            )

        if not _table_exists(conn, "style_profiles"):
            conn.execute(
                """
                CREATE TABLE style_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP NOT NULL,
                    profile_json TEXT NOT NULL
                )
                """
            )

        if not _table_exists(conn, "weekly_reports"):
            conn.execute(
                """
                CREATE TABLE weekly_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_start TIMESTAMP NOT NULL,
                    week_end TIMESTAMP NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )

        if not _table_exists(conn, "thread_posts"):
            conn.execute(
                """
                CREATE TABLE thread_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_token TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    tweet_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    posted_at TIMESTAMP NOT NULL,
                    UNIQUE(draft_token, position)
                )
                """
            )

        conn.commit()
    finally:
        conn.close()

    logger.info("v2 schema ensured")

