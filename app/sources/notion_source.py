from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests

from app.config import settings
from app.models import EvidenceItem
from app.sources.base import SourcePlugin


class NotionSource(SourcePlugin):
    name = "notion"

    def fetch(self) -> list[EvidenceItem]:
        api_key = getattr(settings, "NOTION_API_KEY", None)
        db_id = getattr(settings, "NOTION_DB_ID", None)
        if not api_key or not db_id:
            raise RuntimeError("NOTION_API_KEY or NOTION_DB_ID not configured")

        since = datetime.now(UTC) - timedelta(hours=24)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        payload = {
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 20,
        }

        resp = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        items: list[EvidenceItem] = []
        for page in results:
            last_edited = _parse_dt(page.get("last_edited_time"))
            if last_edited and last_edited < since:
                continue
            page_id = page.get("id")
            title = _extract_title(page)
            url = page.get("url")
            snippet = title
            items.append(
                EvidenceItem(
                    source_name=self.name,
                    source_id=str(page_id),
                    timestamp=last_edited or datetime.now(UTC),
                    raw_snippet=snippet,
                    title=title,
                    url=url,
                )
            )
        return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for _, prop in props.items():
        if prop.get("type") == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                return "".join([t.get("plain_text", "") for t in title_arr]).strip()
    return "(untitled)"
