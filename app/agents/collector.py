import os
import subprocess
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.config import settings
from app.models import EvidenceItem, Materials, RunState
from app.sources.github_source import GitHubSource
from app.sources.notion_source import NotionSource
from app.sources.rss_source import RSSSource

class CollectorAgent(BaseAgent):
    def __init__(self):
        super().__init__("CollectorAgent")

    def run(self, run_state: RunState) -> Materials:
        errors: list[str] = []
        git_commits = self._collect_git_commits(settings.GIT_REPO_PATH)
        devlog = self._collect_devlog(settings.DEVLOG_PATH)

        notes: list[EvidenceItem] = []
        links: list[EvidenceItem] = []

        sources = self._enabled_sources()
        for src in sources:
            try:
                items = src.fetch()
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

    def _collect_git_commits(self, repo_path: str, hours: int = 24) -> list[EvidenceItem]:
        try:
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
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            items: list[EvidenceItem] = []
            for line in lines:
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                commit_hash, epoch_s, subject = parts
                try:
                    ts = datetime.fromtimestamp(int(epoch_s), tz=timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)
                items.append(
                    EvidenceItem(
                        source_name="git",
                        source_id=commit_hash,
                        timestamp=ts,
                        raw_snippet=subject,
                        title=subject,
                    )
                )
            return items
        except Exception:
            return []

    def _collect_devlog(self, file_path: str, char_limit: int = 2000) -> EvidenceItem | None:
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                start = max(0, size - char_limit)
                f.seek(start)
                content = f.read().strip()
            mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
            return EvidenceItem(
                source_name="devlog",
                source_id=os.path.abspath(file_path),
                timestamp=mtime,
                raw_snippet=content,
                title=os.path.basename(file_path),
            )
        except Exception:
            return None

    def _enabled_sources(self):
        enabled = []
        if str(getattr(settings, "ENABLE_SOURCE_NOTION", "false")).lower() == "true":
            enabled.append(NotionSource())
        if str(getattr(settings, "ENABLE_SOURCE_GITHUB", "false")).lower() == "true":
            enabled.append(GitHubSource())
        if str(getattr(settings, "ENABLE_SOURCE_RSS", "false")).lower() == "true":
            enabled.append(RSSSource())
        return enabled
