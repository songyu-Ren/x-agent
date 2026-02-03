import logging
from collections.abc import Generator

from sqlalchemy.orm import Session

from infrastructure.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


def get_session() -> Generator[Session, None, None]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from infrastructure.db.migrations import run_migrations

    run_migrations()
    logger.info("Database ensured via migrations")
