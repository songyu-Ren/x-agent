from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import feedparser

from app.config import settings
from app.models import EvidenceItem
from app.sources.base import SourcePlugin


class RSSSource(SourcePlugin):
    name = "rss"

    def fetch(self) -> List[EvidenceItem]:
        urls = getattr(settings, "RSS_FEED_URLS", "")
        feed_urls = [u.strip() for u in urls.split(",") if u.strip()]
        if not feed_urls:
            raise RuntimeError("RSS_FEED_URLS not configured")

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        items: List[EvidenceItem] = []

        for url in feed_urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                published = _entry_datetime(entry) or datetime.now(timezone.utc)
                if published < since:
                    continue
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", None)
                summary = getattr(entry, "summary", "")
                snippet = f"{title}\n{summary}".strip()[:500]
                source_id = getattr(entry, "id", link or title)[:120]
                items.append(
                    EvidenceItem(
                        source_name=self.name,
                        source_id=source_id,
                        timestamp=published,
                        raw_snippet=snippet,
                        title=title,
                        url=link,
                    )
                )
        return items


def _entry_datetime(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

