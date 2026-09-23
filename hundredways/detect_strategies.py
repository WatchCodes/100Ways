"""DETECT strategies: 10+ ways to know upstream moved.

Each strategy is a detector that polls/watches/hooks the upstream repo
and signals when a new commit lands. Strategies compose via DetectChain.
"""

from __future__ import annotations

import json
import re
import time
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
import subprocess


@dataclass
class DetectEvent:
    """A detection event: upstream moved."""
    strategy: str
    old_head: str
    new_head: str
    commit_count: int
    timestamp: float
    metadata: dict


class DetectStrategy(ABC):
    """Base class for detect strategies."""

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @abstractmethod
    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Poll once. Return event if upstream moved, else None."""
        pass


class GitFetchPolling(DetectStrategy):
    """Git fetch polling: git fetch upstream && rev-parse HEAD every cycle."""

    def name(self) -> str:
        return "detect.poll"

    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Fetch and check if HEAD moved."""
        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            subprocess.check_call(
                ["git", "fetch", upstream],
                cwd=repo_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            new_head = subprocess.check_output(
                ["git", "rev-parse", f"{upstream}/HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            if old_head != new_head:
                count = int(subprocess.check_output(
                    ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                    cwd=repo_path,
                    text=True
                ).strip())

                return DetectEvent(
                    strategy=self.name(),
                    old_head=old_head,
                    new_head=new_head,
                    commit_count=count,
                    timestamp=time.time(),
                    metadata={"method": "git-fetch"}
                )
            return None
        except Exception as e:
            return None


class GitRevListPolling(DetectStrategy):
    """Alternative polling: rev-list only, no fetch side effects."""

    def name(self) -> str:
        return "detect.rev-list"

    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Check if upstream/HEAD exists and differs from local."""
        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            new_head = subprocess.check_output(
                ["git", "rev-parse", f"{upstream}/HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            if old_head != new_head:
                count = int(subprocess.check_output(
                    ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                    cwd=repo_path,
                    text=True
                ).strip())

                return DetectEvent(
                    strategy=self.name(),
                    old_head=old_head,
                    new_head=new_head,
                    commit_count=count,
                    timestamp=time.time(),
                    metadata={"method": "rev-list-only"}
                )
            return None
        except Exception:
            return None


class GitHashPolling(DetectStrategy):
    """Fast: hash the upstream ref, compare to cached hash."""

    def name(self) -> str:
        return "detect.hash-cache"

    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Hash upstream/HEAD, compare to last known hash."""
        cache_file = Path(repo_path) / ".detect_hash_cache"

        try:
            new_head = subprocess.check_output(
                ["git", "rev-parse", f"{upstream}/HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            new_hash = hashlib.sha256(new_head.encode()).hexdigest()
            old_hash = cache_file.read_text().strip() if cache_file.exists() else ""

            cache_file.write_text(new_hash)

            if old_hash and old_hash != new_hash:
                old_head = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_path,
                    text=True
                ).strip()

                count = int(subprocess.check_output(
                    ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                    cwd=repo_path,
                    text=True
                ).strip())

                return DetectEvent(
                    strategy=self.name(),
                    old_head=old_head,
                    new_head=new_head,
                    commit_count=count,
                    timestamp=time.time(),
                    metadata={"hash_change": True}
                )
            return None
        except Exception:
            return None


class ReflogPolling(DetectStrategy):
    """Check reflog for new entries: upstream/HEAD changes appear there first."""

    def name(self) -> str:
        return "detect.reflog"

    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Scan reflog for upstream/HEAD updates."""
        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            # Check reflog for upstream/HEAD updates
            reflog = subprocess.check_output(
                ["git", "reflog", f"{upstream}/HEAD", "--max-count=1"],
                cwd=repo_path,
                text=True
            ).strip()

            # Extract the ref from reflog output
            if reflog:
                new_head = reflog.split()[0]
                if new_head != old_head:
                    count = int(subprocess.check_output(
                        ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                        cwd=repo_path,
                        text=True
                    ).strip())

                    return DetectEvent(
                        strategy=self.name(),
                        old_head=old_head,
                        new_head=new_head,
                        commit_count=count,
                        timestamp=time.time(),
                        metadata={"method": "reflog"}
                    )
            return None
        except Exception:
            return None


class CommitMessageGrep(DetectStrategy):
    """Keyword detection: grep commit messages for trigger patterns."""

    def name(self) -> str:
        return "detect.message-grep"

    def detect(self, repo_path: str, upstream: str, trigger_keywords: list[str] = None) -> Optional[DetectEvent]:
        """Search recent commits for trigger keywords."""
        if trigger_keywords is None:
            trigger_keywords = ["[sync]", "[port]", "upstream", "cherry-pick"]

        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            # Get last 20 commits from upstream
            log = subprocess.check_output(
                ["git", "log", f"{upstream}/HEAD", "-20", "--format=%H %s"],
                cwd=repo_path,
                text=True
            ).strip()

            for line in log.split("\n"):
                if any(kw.lower() in line.lower() for kw in trigger_keywords):
                    new_head = line.split()[0]
                    if new_head != old_head:
                        count = int(subprocess.check_output(
                            ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                            cwd=repo_path,
                            text=True
                        ).strip())

                        return DetectEvent(
                            strategy=self.name(),
                            old_head=old_head,
                            new_head=new_head,
                            commit_count=count,
                            timestamp=time.time(),
                            metadata={"trigger": line.split(None, 1)[1]}
                        )
                    break

            return None
        except Exception:
            return None


class FileWatchPolling(DetectStrategy):
    """Watch specific file: check if file mtimes changed on upstream."""

    def name(self) -> str:
        return "detect.file-watch"

    def detect(self, repo_path: str, upstream: str, watch_files: list[str] = None) -> Optional[DetectEvent]:
        """Poll if any watched files changed in upstream."""
        if watch_files is None:
            watch_files = ["VERSION", "CHANGELOG.md", "package.json"]

        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            new_head = subprocess.check_output(
                ["git", "rev-parse", f"{upstream}/HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            if old_head == new_head:
                return None

            # Check if any watched file changed
            for file_path in watch_files:
                try:
                    diff = subprocess.check_output(
                        ["git", "diff", f"{old_head}..{new_head}", "--", file_path],
                        cwd=repo_path,
                        text=True
                    ).strip()

                    if diff:
                        count = int(subprocess.check_output(
                            ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                            cwd=repo_path,
                            text=True
                        ).strip())

                        return DetectEvent(
                            strategy=self.name(),
                            old_head=old_head,
                            new_head=new_head,
                            commit_count=count,
                            timestamp=time.time(),
                            metadata={"file_changed": file_path}
                        )
                except Exception:
                    pass

            return None
        except Exception:
            return None


class AuthorFilterPolling(DetectStrategy):
    """Author-based detection: only react to commits from specific authors."""

    def name(self) -> str:
        return "detect.author-filter"

    def detect(self, repo_path: str, upstream: str, allowed_authors: list[str] = None) -> Optional[DetectEvent]:
        """Detect changes only from whitelisted authors."""
        if allowed_authors is None:
            allowed_authors = ["maintainer@example.com"]

        try:
            old_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            new_head = subprocess.check_output(
                ["git", "rev-parse", f"{upstream}/HEAD"],
                cwd=repo_path,
                text=True
            ).strip()

            if old_head == new_head:
                return None

            # Check commits from allowed authors
            for author in allowed_authors:
                log = subprocess.check_output(
                    ["git", "log", f"{old_head}..{new_head}", f"--author={author}", "--format=%H"],
                    cwd=repo_path,
                    text=True
                ).strip()

                if log:
                    count = int(subprocess.check_output(
                        ["git", "rev-list", "--count", f"{old_head}..{new_head}"],
                        cwd=repo_path,
                        text=True
                    ).strip())

                    return DetectEvent(
                        strategy=self.name(),
                        old_head=old_head,
                        new_head=new_head,
                        commit_count=count,
                        timestamp=time.time(),
                        metadata={"author": author}
                    )

            return None
        except Exception:
            return None


class DetectChain:
    """Compose multiple detect strategies."""

    def __init__(self, strategies: list[DetectStrategy] = None):
        self.strategies = strategies or [GitFetchPolling()]

    def detect(self, repo_path: str, upstream: str) -> Optional[DetectEvent]:
        """Run strategies in order, return first non-None event."""
        for strategy in self.strategies:
            event = strategy.detect(repo_path, upstream)
            if event:
                return event
        return None

    def add_strategy(self, strategy: DetectStrategy):
        """Add a strategy to the chain."""
        self.strategies.append(strategy)

    def to_dict(self) -> dict:
        """Serialize chain state."""
        return {
            "strategies": [s.name() for s in self.strategies],
            "count": len(self.strategies)
        }
