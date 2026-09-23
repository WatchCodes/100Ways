"""WATCH strategies: 10+ ways to monitor and alert.

Each strategy monitors repo state, gate decisions, or system health.
Strategies compose via WatchChain for comprehensive monitoring.
"""

from __future__ import annotations

import subprocess
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Callable
from datetime import datetime, timedelta


@dataclass
class WatchEvent:
    """A watch event triggered."""
    strategy: str
    event_type: str  # alert, warning, info
    title: str
    details: str
    severity: int  # 0-10
    timestamp: str = None
    metadata: dict = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}


class WatchStrategy(ABC):
    """Base class for watch strategies."""

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @abstractmethod
    def check(self) -> Optional[WatchEvent]:
        """Run check. Return event if triggered, else None."""
        pass


class RepoHeartbeat(WatchStrategy):
    """Heartbeat: verify the repo is accessible and healthy."""

    def name(self) -> str:
        return "watch.heartbeat"

    def __init__(self, repo_path: str, upstream: str):
        self.repo_path = repo_path
        self.upstream = upstream

    def check(self) -> Optional[WatchEvent]:
        """Check repo is accessible."""
        try:
            # Try to rev-parse HEAD
            subprocess.check_call(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return None  # Healthy
        except Exception as e:
            return WatchEvent(
                strategy=self.name(),
                event_type="alert",
                title="Repo heartbeat failed",
                details=f"Cannot access repo {self.repo_path}: {e}",
                severity=8
            )


class StaleBranchDetection(WatchStrategy):
    """Detect stale branches: branch hasn't been updated in N days."""

    def name(self) -> str:
        return "watch.stale-branch"

    def __init__(self, repo_path: str, branch: str = "main", days: int = 7):
        self.repo_path = repo_path
        self.branch = branch
        self.days = days

    def check(self) -> Optional[WatchEvent]:
        """Check if branch is stale."""
        try:
            # Get last commit timestamp
            timestamp = subprocess.check_output(
                ["git", "log", "-1", "--format=%at", self.branch],
                cwd=self.repo_path,
                text=True
            ).strip()

            last_commit = datetime.fromtimestamp(int(timestamp))
            age = datetime.now() - last_commit

            if age > timedelta(days=self.days):
                return WatchEvent(
                    strategy=self.name(),
                    event_type="warning",
                    title=f"Branch '{self.branch}' is stale",
                    details=f"Last commit {age.days} days ago",
                    severity=3,
                    metadata={"branch": self.branch, "age_days": age.days}
                )
            return None
        except Exception:
            return None


class UpstreamDrift(WatchStrategy):
    """Detect upstream drift: our branch has diverged significantly."""

    def name(self) -> str:
        return "watch.drift"

    def __init__(self, repo_path: str, upstream: str, threshold: int = 50):
        self.repo_path = repo_path
        self.upstream = upstream
        self.threshold = threshold

    def check(self) -> Optional[WatchEvent]:
        """Check for upstream drift."""
        try:
            # Count commits diverged
            count = int(subprocess.check_output(
                ["git", "rev-list", "--count", f"HEAD..{self.upstream}/HEAD"],
                cwd=self.repo_path,
                text=True
            ).strip())

            if count > self.threshold:
                return WatchEvent(
                    strategy=self.name(),
                    event_type="warning",
                    title="Upstream drift detected",
                    details=f"Our branch is {count} commits behind upstream",
                    severity=5,
                    metadata={"commits_behind": count, "threshold": self.threshold}
                )
            return None
        except Exception:
            return None


class ConflictDetection(WatchStrategy):
    """Detect unresolved conflicts or merge issues."""

    def name(self) -> str:
        return "watch.conflicts"

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def check(self) -> Optional[WatchEvent]:
        """Check for conflict markers or merge state."""
        try:
            # Check if repo is in merge state
            merge_head = Path(self.repo_path) / ".git" / "MERGE_HEAD"
            if merge_head.exists():
                return WatchEvent(
                    strategy=self.name(),
                    event_type="alert",
                    title="Repo in merge state",
                    details="MERGE_HEAD exists, merge may be incomplete",
                    severity=7
                )

            # Check for conflict markers in code
            result = subprocess.run(
                ["grep", "-r", "<<<<<<< HEAD", self.repo_path],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                files_with_conflicts = len(result.stdout.strip().split("\n"))
                return WatchEvent(
                    strategy=self.name(),
                    event_type="alert",
                    title="Conflict markers found",
                    details=f"Found conflict markers in {files_with_conflicts} locations",
                    severity=8
                )

            return None
        except Exception:
            return None


class FailedGateAlert(WatchStrategy):
    """Monitor gate failures."""

    def name(self) -> str:
        return "watch.gate-failures"

    def __init__(self, gate_log_file: str):
        self.gate_log_file = gate_log_file

    def check(self) -> Optional[WatchEvent]:
        """Check for recent gate failures."""
        try:
            log_path = Path(self.gate_log_file)
            if not log_path.exists():
                return None

            # Read last 10 lines
            lines = log_path.read_text().strip().split("\n")[-10:]

            failures = [l for l in lines if "FAIL" in l or "ERROR" in l]
            if failures:
                return WatchEvent(
                    strategy=self.name(),
                    event_type="alert",
                    title="Recent gate failures detected",
                    details=f"Found {len(failures)} failure(s) in gate logs",
                    severity=7,
                    metadata={"failures": failures[:3]}  # First 3
                )
            return None
        except Exception:
            return None


class DiskSpaceWatch(WatchStrategy):
    """Monitor disk space for the repo."""

    def name(self) -> str:
        return "watch.disk-space"

    def __init__(self, repo_path: str, threshold_percent: int = 90):
        self.repo_path = repo_path
        self.threshold_percent = threshold_percent

    def check(self) -> Optional[WatchEvent]:
        """Check disk space usage."""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.repo_path)
            used_percent = (used / total) * 100

            if used_percent > self.threshold_percent:
                return WatchEvent(
                    strategy=self.name(),
                    event_type="warning",
                    title="Disk space running low",
                    details=f"Disk is {used_percent:.1f}% full",
                    severity=6,
                    metadata={"used_percent": used_percent, "free_gb": free / (1024**3)}
                )
            return None
        except Exception:
            return None


class UnpushedCommits(WatchStrategy):
    """Detect unpushed local commits."""

    def name(self) -> str:
        return "watch.unpushed"

    def __init__(self, repo_path: str, remote: str = "origin"):
        self.repo_path = repo_path
        self.remote = remote

    def check(self) -> Optional[WatchEvent]:
        """Check for unpushed commits."""
        try:
            count = int(subprocess.check_output(
                ["git", "rev-list", "--count", f"HEAD..{self.remote}/HEAD"],
                cwd=self.repo_path,
                text=True,
                stderr=subprocess.DEVNULL
            ).strip())

            if count > 0:
                return WatchEvent(
                    strategy=self.name(),
                    event_type="info",
                    title="Unpushed commits found",
                    details=f"{count} commits not yet pushed to {self.remote}",
                    severity=2,
                    metadata={"unpushed_count": count}
                )
            return None
        except Exception:
            return None


class LargeFileDetection(WatchStrategy):
    """Detect accidentally committed large files."""

    def name(self) -> str:
        return "watch.large-files"

    def __init__(self, repo_path: str, size_mb: int = 100):
        self.repo_path = repo_path
        self.size_mb = size_mb

    def check(self) -> Optional[WatchEvent]:
        """Check for large files in repo."""
        try:
            # Get top 5 largest files
            output = subprocess.check_output(
                ["git", "rev-list", "--all", "--objects"],
                cwd=self.repo_path,
                text=True
            )

            large_files = []
            for line in output.strip().split("\n"):
                if not line:
                    continue
                sha, path = line.split(None, 1)
                try:
                    size = int(subprocess.check_output(
                        ["git", "cat-file", "-s", sha],
                        cwd=self.repo_path,
                        text=True
                    ).strip())
                    
                    if size > self.size_mb * 1024 * 1024:
                        large_files.append((path, size / (1024 * 1024)))
                except:
                    pass

            if large_files:
                large_files.sort(key=lambda x: x[1], reverse=True)
                return WatchEvent(
                    strategy=self.name(),
                    event_type="warning",
                    title="Large files detected in repo",
                    details=f"Found {len(large_files)} file(s) > {self.size_mb}MB",
                    severity=4,
                    metadata={"large_files": [f"{f[0]}: {f[1]:.1f}MB" for f in large_files[:3]]}
                )
            return None
        except Exception:
            return None


class WatchChain:
    """Compose multiple watch strategies."""

    def __init__(self, strategies: List[WatchStrategy] = None):
        self.strategies = strategies or []
        self.event_history = []

    def check_all(self) -> List[WatchEvent]:
        """Run all watches, collect events."""
        events = []
        for strategy in self.strategies:
            try:
                event = strategy.check()
                if event:
                    events.append(event)
                    self.event_history.append(event)
            except Exception:
                pass

        # Sort by severity descending
        events.sort(key=lambda e: e.severity, reverse=True)
        return events

    def add_watch(self, strategy: WatchStrategy):
        """Add a watch to the chain."""
        self.strategies.append(strategy)

    def get_recent_events(self, hours: int = 24) -> List[WatchEvent]:
        """Get events from the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [e for e in self.event_history if datetime.fromisoformat(e.timestamp) > cutoff]

    def alert_summary(self) -> dict:
        """Generate alert summary."""
        events = self.get_recent_events()
        return {
            "total_events": len(events),
            "alerts": sum(1 for e in events if e.event_type == "alert"),
            "warnings": sum(1 for e in events if e.event_type == "warning"),
            "avg_severity": sum(e.severity for e in events) / len(events) if events else 0,
            "strategies_active": len(self.strategies)
        }

    def to_dict(self) -> dict:
        """Serialize chain state."""
        return {
            "strategies": [s.name() for s in self.strategies],
            "count": len(self.strategies),
            "recent_events": len(self.get_recent_events(24)),
            "summary": self.alert_summary()
        }
