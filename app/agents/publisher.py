import time
from datetime import UTC, datetime

import tweepy

from app.agents.base import BaseAgent
from app.config import settings
from app.models import PublishRequest, PublishResult
from infrastructure.db.repositories import (
    get_draft,
    get_existing_thread_posts,
    insert_post_idempotent,
)
from infrastructure.db.session import get_sessionmaker


class PublisherAgent(BaseAgent):
    def __init__(self):
        super().__init__("PublisherAgent")

    def run(self, request: PublishRequest) -> PublishResult:
        draft_id = request.draft_id
        tweets = request.tweets
        with get_sessionmaker()() as session:
            draft = get_draft(session, draft_id)
            if draft is None:
                raise RuntimeError("Draft not found")

            existing = get_existing_thread_posts(session, draft)
            tweet_ids: list[str] = []

            reply_to: str | None = None
            for idx, text in enumerate(tweets, start=1):
                if idx in existing:
                    tweet_ids.append(existing[idx])
                    reply_to = existing[idx]
                    continue

                if request.dry_run or settings.DRY_RUN:
                    tweet_id = f"dry_{draft_id[:8]}_{idx}"
                else:
                    tweet_id = self._post_with_retry(
                        text, reply_to if request.reply_chain else None
                    )

                insert_post_idempotent(
                    session=session,
                    draft=draft,
                    position=idx,
                    tweet_id=tweet_id,
                    content=text,
                    publish_idempotency_key=f"{draft_id}:{idx}",
                    posted_at=datetime.now(UTC),
                )
                tweet_ids.append(tweet_id)
                reply_to = tweet_id

            session.commit()
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
