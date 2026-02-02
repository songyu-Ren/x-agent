import logging
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = "daily_agent.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    from app.migrations.runner import run_migrations

    run_migrations()
    logger.info("Database ensured via migrations")
