import time

import tweepy

from app.agents.base import BaseAgent
from app.config import settings
from app.database import get_connection
from app.models import PublishRequest, PublishResult

class PublisherAgent(BaseAgent):
    def __init__(self):
        super().__init__("PublisherAgent")

    def run(self, request: PublishRequest) -> PublishResult:
        token = request.token
        tweets = request.tweets

        existing = self._load_existing_thread_posts(token)
        tweet_ids: list[str] = []

        reply_to: str | None = None
        for idx, text in enumerate(tweets, start=1):
            if idx in existing:
                tweet_ids.append(existing[idx])
                reply_to = existing[idx]
                continue

            if request.dry_run or settings.DRY_RUN:
                fake_id = f"dry_{token[:8]}_{idx}"
                self._save_thread_post(token, idx, fake_id, text)
                tweet_ids.append(fake_id)
                reply_to = fake_id
                continue

            tweet_id = self._post_with_retry(text, reply_to if request.reply_chain else None)
            self._save_thread_post(token, idx, tweet_id, text)
            tweet_ids.append(tweet_id)
            reply_to = tweet_id

        return PublishResult(tweet_ids=tweet_ids)

    def _client(self) -> tweepy.Client:
        return tweepy.Client(
            consumer_key=settings.TWITTER_API_KEY,
            consumer_secret=settings.TWITTER_API_SECRET,
            access_token=settings.TWITTER_ACCESS_TOKEN,
            access_token_secret=settings.TWITTER_ACCESS_TOKEN_SECRET,
        )

    def _post_with_retry(self, text: str, reply_to: str | None) -> str:
        delay = 0.5
        last_err: Exception | None = None
        for _ in range(3):
            try:
                client = self._client()
                resp = (
                    client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
                    if reply_to
                    else client.create_tweet(text=text)
                )
                if resp.data and resp.data.get("id"):
                    return str(resp.data["id"])
                raise RuntimeError("No data in X response")
            except Exception as e:
                last_err = e
                time.sleep(delay)
                delay *= 2
        raise last_err or RuntimeError("X post failed")

    def _load_existing_thread_posts(self, token: str) -> dict[int, str]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT position, tweet_id FROM thread_posts WHERE draft_token = ? ORDER BY position ASC",
            (token,),
        ).fetchall()
        conn.close()
        return {int(r[0]): str(r[1]) for r in rows}

    def _save_thread_post(self, token: str, position: int, tweet_id: str, content: str) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR IGNORE INTO thread_posts (draft_token, position, tweet_id, content, posted_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (token, position, tweet_id, content),
        )
        conn.commit()
        conn.close()
