from app.agents.publisher import PublisherAgent
from app.database import get_connection
from app.models import PublishRequest


def test_publisher_idempotent_thread_dry_run(clean_db):
    agent = PublisherAgent()
    req = PublishRequest(token="tok123", tweets=["t1", "t2", "t3"], dry_run=True)

    r1 = agent.run(req)
    r2 = agent.run(req)

    assert r1.tweet_ids == r2.tweet_ids

    conn = get_connection()
    rows = conn.execute(
        "SELECT position, tweet_id FROM thread_posts WHERE draft_token=? ORDER BY position",
        ("tok123",),
    ).fetchall()
    conn.close()
    assert len(rows) == 3

