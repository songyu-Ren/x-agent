import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import init_db
from infrastructure.db import models
from infrastructure.db.session import get_sessionmaker, reset_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    settings.DATABASE_URL = "sqlite+pysqlite:///:memory:"
    reset_engine()
    init_db()
    yield


@pytest.fixture
def clean_db():
    with get_sessionmaker()() as session:
        session.execute(delete(models.AuditLog))
        session.execute(delete(models.UserSession))
        session.execute(delete(models.User))
        session.execute(delete(models.AppConfig))
        session.execute(delete(models.Post))
        session.execute(delete(models.ActionToken))
        session.execute(delete(models.PublishAttempt))
        session.execute(delete(models.PolicyReport))
        session.execute(delete(models.AgentLog))
        session.execute(delete(models.Draft))
        session.execute(delete(models.Run))
        session.execute(delete(models.StyleProfile))
        session.execute(delete(models.WeeklyReport))
        session.commit()
