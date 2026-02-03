from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests

from app.config import settings
from app.models import EvidenceItem
from app.sources.base import SourcePlugin

logger = logging.getLogger(__name__)


class GitHubSource(SourcePlugin):
    name = "github"

    def fetch(self) -> list[EvidenceItem]:
        token = getattr(settings, "GITHUB_TOKEN", None)
        repo = getattr(settings, "GITHUB_REPO", None)
        if not token or not repo:
            raise RuntimeError("GITHUB_TOKEN or GITHUB_REPO not configured")

        since = datetime.now(UTC) - timedelta(hours=24)
        since_iso = since.isoformat()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        owner_repo = repo.strip()
        base = f"https://api.github.com/repos/{owner_repo}"

        items: list[EvidenceItem] = []

        pulls = requests.get(
            f"{base}/pulls",
            headers=headers,
            params={
                "state": "all",
                "per_page": "20",
                "sort": "updated",
                "direction": "desc",
            },
            timeout=15,
        )
        pulls.raise_for_status()
        for pr in pulls.json():
            updated_at = _parse_dt(pr.get("updated_at"))
            if updated_at and updated_at < since:
                continue
            pr_number = pr.get("number")
            title = pr.get("title") or ""
            body = (pr.get("body") or "")[:280]
            url = pr.get("html_url")
            snippet = f"PR #{pr_number}: {title}\n{body}".strip()
            items.append(
                EvidenceItem(
                    source_name=self.name,
                    source_id=f"pr:{pr_number}",
                    timestamp=updated_at or datetime.now(UTC),
                    raw_snippet=snippet,
                    title=title,
                    url=url,
                )
            )

        issues = requests.get(
            f"{base}/issues",
            headers=headers,
            params={"state": "all", "per_page": "20", "since": since_iso},
            timeout=15,
        )
        issues.raise_for_status()
        for issue in issues.json():
            if "pull_request" in issue:
                continue
            updated_at = _parse_dt(issue.get("updated_at"))
            if updated_at and updated_at < since:
                continue
            number = issue.get("number")
            title = issue.get("title") or ""
            body = (issue.get("body") or "")[:280]
            url = issue.get("html_url")
            snippet = f"Issue #{number}: {title}\n{body}".strip()
            items.append(
                EvidenceItem(
                    source_name=self.name,
                    source_id=f"issue:{number}",
                    timestamp=updated_at or datetime.now(UTC),
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
