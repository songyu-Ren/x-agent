from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from app.config import settings
from infrastructure.db.session import get_engine


def run_migrations() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    url = getattr(settings, "DATABASE_URL", None) or f"sqlite+pysqlite:///{settings.DB_PATH}"
    cfg.set_main_option("sqlalchemy.url", url)
    engine = get_engine()
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
