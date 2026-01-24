import os
import pytest
from app.storage import init_db, get_connection
from app.config import settings

# Use a separate DB for tests
TEST_DB = "test_daily_agent.db"

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Override global DB path in storage (monkeypatch not easy for global var import, 
    # but we can patch app.storage.DB_PATH if we import it there or just swap file)
    import app.storage
    app.storage.DB_PATH = TEST_DB
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    init_db()
    yield
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.fixture
def clean_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drafts")
    conn.commit()
    conn.close()
