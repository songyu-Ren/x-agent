import os
import subprocess
from datetime import UTC, datetime

from app.agents.base import BaseAgent
from app.config import settings
from app.models import EvidenceItem, Materials, RunState
from app.sources.base import SourcePlugin
from app.sources.github_source import GitHubSource
from app.sources.notion_source import NotionSource
from app.sources.rss_source import RSSSource


class CollectorAgent(BaseAgent):
    def __init__(self):
        super().__init__("CollectorAgent")

    def run(self, run_state: RunState) -> Materials:
        errors: list[str] = []
        git_commits: list[EvidenceItem] = []
        devlog: EvidenceItem | None = None

        notes: list[EvidenceItem] = []
        links: list[EvidenceItem] = []

        sources = self._enabled_sources()
        for src in sources:
            try:
                items = src.fetch()
                if src.name == "git":
                    git_commits.extend(items)
                    continue
                if src.name == "devlog":
                    devlog = items[0] if items else None
                    continue
                for item in items:
                    if item.url:
                        links.append(item)
                    else:
                        notes.append(item)
            except Exception as e:
                errors.append(f"source:{src.name} failed: {str(e)[:200]}")

        return Materials(
            git_commits=git_commits,
            devlog=devlog,
            notes=notes,
            links=links,
            errors=errors,
        )

    def _enabled_sources(self) -> list[SourcePlugin]:
        enabled: list[SourcePlugin] = [GitCommitsSource(), DevlogSource()]
        if str(getattr(settings, "ENABLE_SOURCE_NOTION", "false")).lower() == "true":
            enabled.append(NotionSource())
        if str(getattr(settings, "ENABLE_SOURCE_GITHUB", "false")).lower() == "true":
            enabled.append(GitHubSource())
        if str(getattr(settings, "ENABLE_SOURCE_RSS", "false")).lower() == "true":
            enabled.append(RSSSource())
        return enabled


class GitCommitsSource(SourcePlugin):
    name = "git"

    def fetch(self) -> list[EvidenceItem]:
        repo_path = str(getattr(settings, "GIT_REPO_PATH", ".") or ".")
        hours = int(getattr(settings, "COLLECT_HOURS", 24) or 24)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return []
        cmd = [
            "git",
            "-C",
            repo_path,
            "log",
            f"--since={hours}hours",
            "--pretty=format:%H|%ct|%s",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        items: list[EvidenceItem] = []
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            commit_hash, epoch_s, subject = parts
            try:
                ts = datetime.fromtimestamp(int(epoch_s), tz=UTC)
            except Exception:
                ts = datetime.now(UTC)
            items.append(
                EvidenceItem(
                    source_name=self.name,
                    source_id=commit_hash,
                    timestamp=ts,
                    raw_snippet=subject,
                    title=subject,
                )
            )
        return items


class DevlogSource(SourcePlugin):
    name = "devlog"

    def fetch(self) -> list[EvidenceItem]:
        file_path = str(getattr(settings, "DEVLOG_PATH", "devlog.md") or "devlog.md")
        char_limit = int(getattr(settings, "DEVLOG_CHAR_LIMIT", 2000) or 2000)
        if not os.path.exists(file_path):
            return []
        with open(file_path, encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - char_limit)
            f.seek(start)
            content = f.read().strip()
        mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=UTC)
        return [
            EvidenceItem(
                source_name=self.name,
                source_id=os.path.abspath(file_path),
                timestamp=mtime,
                raw_snippet=content,
                title=os.path.basename(file_path),
            )
        ]
