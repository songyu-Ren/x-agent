import subprocess
import logging
import os
from typing import Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

def collect_git_commits(repo_path: str, hours: int = 24) -> str:
    """Collect git commit messages from the last N hours."""
    try:
        # Check if it's a git repo
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            logger.warning(f"{repo_path} is not a git repository.")
            return ""

        cmd = [
            "git",
            "-C", repo_path,
            "log",
            f"--since={hours}hours",
            "--pretty=format:%s"  # Only subject
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Git log failed: {e}")
        return ""
    except Exception as e:
        logger.error(f"Error collecting git logs: {e}")
        return ""

def collect_devlog(file_path: str, char_limit: int = 2000) -> str:
    """Read the last N characters of the devlog file."""
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Devlog file not found: {file_path}")
            return ""
            
        with open(file_path, "r", encoding="utf-8") as f:
            # Efficient tail for large files? For MVP, reading all is fine if not huge.
            # Or seek to end.
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - char_limit)
            f.seek(start)
            content = f.read()
            return content.strip()
    except Exception as e:
        logger.error(f"Error reading devlog: {e}")
        return ""

def collect_materials() -> Dict[str, Any]:
    """Aggregate all materials."""
    git_logs = collect_git_commits(settings.GIT_REPO_PATH)
    devlog = collect_devlog(settings.DEVLOG_PATH)
    
    return {
        "git_logs": git_logs,
        "devlog": devlog,
        "links": [], # Future extension
        "notes": []  # Future extension
    }
