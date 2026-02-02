import os

import pytest

from app.database import get_connection, init_db

TEST_DB = "test_daily_agent.db"

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Patch DB path
    import app.database
    app.database.DB_PATH = TEST_DB
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    init_db()
    yield
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.fixture
def clean_db():
    conn = get_connection()
    conn.execute("DELETE FROM drafts")
    conn.execute("DELETE FROM runs")
    conn.execute("DELETE FROM posts")
    conn.execute("DELETE FROM style_profiles")
    conn.execute("DELETE FROM weekly_reports")
    conn.execute("DELETE FROM thread_posts")
    conn.commit()
    conn.close()
