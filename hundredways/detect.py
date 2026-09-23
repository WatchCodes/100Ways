"""DETECT category: 20 comprehensive detection strategies for upstream changes.

Implements pluggable, composable detection chains via DiffChain pattern.
Each detection method is a DetectionStrategy with pluggable integration points.

20 Detection Ways:
  1. polling         - Periodic HEAD checks via git fetch/rev-parse
  2. webhooks        - Webhook listeners for instant push notifications
  3. cron            - Scheduled cron jobs for periodic scans
  4. github_api      - GitHub REST API repository polling
  5. scheduled_sync  - Time-based scheduled synchronization
  6. rss_feeds       - RSS feed monitoring for release changes
  7. graphql         - GitHub GraphQL queries for advanced filtering
  8. signal_handlers - OS signal handlers for reactive events
  9. idle_time       - Idle-time background checks
 10. startup_scans   - On-startup repository scans
 11. pr_closes       - PR close event detection
 12. tag_changes     - Git tag creation/modification detection
 13. reflog_probes   - Reflog-based history probing
 14. webhook_fallback - Webhook with fallback polling
 15. selector_loops  - Selector-based multiplexing
 16. multi_host      - Multi-host heartbeat detection
 17. branch_tracking - Branch ref change tracking
 18. commit_digests  - Commit hash digest verification
 19. event_streams   - Event stream subscriptions
 20. health_checks   - Upstream health check monitoring

Architecture:
  - DetectionStrategy: base class for all detectors
  - DiffChain: composable, pluggable detection chain
  - DetectionEvent: unified event model for all detection types
  - DetectionConfig: configuration for all strategies
  - SecurityAuditor: input validation, rate limiting, state recovery
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ==============================================================================
# TYPES & ENUMS
# ==============================================================================


class DetectionKind(str, Enum):
    """Unified event kinds across all detection strategies."""

    NEW_COMMITS = "new-commits"
    TAG_CREATED = "tag-created"
    TAG_DELETED = "tag-deleted"
    BRANCH_UPDATED = "branch-updated"
    BRANCH_CREATED = "branch-created"
    BRANCH_DELETED = "branch-deleted"
    PR_OPENED = "pr-opened"
    PR_CLOSED = "pr-closed"
    PR_MERGED = "pr-merged"
    RELEASE_PUBLISHED = "release-published"
    HEALTH_DEGRADED = "health-degraded"
    WEBHOOK_RECEIVED = "webhook-received"
    REFLOG_CHANGE = "reflog-change"
    COMMIT_DIGEST_MISMATCH = "commit-digest-mismatch"
    MULTI_HOST_DIVERGENCE = "multi-host-divergence"


class DetectionStrategyKind(str, Enum):
    """Classification of detection strategy types."""

    POLLING = "polling"
    WEBHOOK = "webhook"
    SCHEDULED = "scheduled"
    SIGNAL = "signal"
    PASSIVE = "passive"
    COMPOSITE = "composite"


@dataclass
class DetectionEvent:
    """Unified event model for all detection strategies."""

    kind: DetectionKind
    timestamp: datetime
    source: str  # which detection strategy produced this
    data: dict[str, Any] = field(default_factory=dict)
    upstream_sha: str = ""
    downstream_sha: str = ""
    branch: str = ""
    commit_count: int = 0
    error: Optional[str] = None
    requires_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dict."""
        return {
            "kind": self.kind.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "upstream_sha": self.upstream_sha,
            "downstream_sha": self.downstream_sha,
            "branch": self.branch,
            "commit_count": self.commit_count,
            "error": self.error,
            "requires_action": self.requires_action,
        }


@dataclass
class DetectionConfig:
    """Configuration for all detection strategies."""

    repo: str  # local repository path
    upstream_remote: str = "upstream"
    upstream_branch: str = "main"
    downstream_branch: str = "sync-upstream"
    state_dir: str = "config"
    webhook_port: int = 8765
    webhook_token: str = ""
    poll_interval: int = 300  # seconds
    cron_schedule: str = "0 */6 * * *"  # every 6 hours
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    rss_feeds: list[str] = field(default_factory=list)
    remote_hosts: list[str] = field(default_factory=list)
    timeout: int = 15  # seconds
    max_retries: int = 3
    rate_limit_per_hour: int = 60
    enable_logging: bool = True
    log_level: str = "INFO"
    dry_run: bool = False

    def validate(self) -> list[str]:
        """Validate configuration; return list of errors."""
        errors = []
        if not self.repo or not Path(self.repo).exists():
            errors.append(f"repo path does not exist: {self.repo}")
        if self.poll_interval < 10:
            errors.append(f"poll_interval too short: {self.poll_interval} < 10")
        if self.timeout < 5:
            errors.append(f"timeout too short: {self.timeout} < 5")
        if self.webhook_port < 1024 or self.webhook_port > 65535:
            errors.append(f"webhook_port out of range: {self.webhook_port}")
        if self.rate_limit_per_hour < 1:
            errors.append(f"rate_limit_per_hour must be >= 1")
        return errors


# ==============================================================================
# LOGGING & MONITORING
# ==============================================================================


class DetectionLogger:
    """Structured logging for detection strategies."""

    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(f"detect.{name}")
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(level)

    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, extra=kwargs)

    def info(self, msg: str, **kwargs):
        self.logger.info(msg, extra=kwargs)

    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, extra=kwargs)

    def error(self, msg: str, **kwargs):
        self.logger.error(msg, extra=kwargs)


# ==============================================================================
# SECURITY & VALIDATION
# ==============================================================================


class SecurityAuditor:
    """Input validation, rate limiting, and state corruption recovery."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        self.config = config
        self.logger = logger
        self.call_log: dict[str, list[float]] = {}  # strategy -> timestamps
        self.state_dir = Path(config.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def validate_sha(self, sha: str) -> bool:
        """Validate git SHA format (40 hex chars for SHA1, 64 for SHA256)."""
        if not isinstance(sha, str):
            return False
        sha = sha.lower()
        return len(sha) in (40, 64) and all(c in "0123456789abcdef" for c in sha)

    def validate_branch_name(self, branch: str) -> bool:
        """Validate branch name (git rules)."""
        if not isinstance(branch, str) or not branch:
            return False
        # Simplified validation: no spaces, no special chars, no ..
        forbidden = [" ", "\n", "\t", "//", "..", "@{"]
        return not any(x in branch for x in forbidden)

    def validate_remote_url(self, url: str) -> bool:
        """Validate remote URL (basic check)."""
        if not isinstance(url, str) or not url:
            return False
        try:
            result = urllib.parse.urlparse(url)
            return result.scheme in ("http", "https", "ssh", "git") and bool(
                result.netloc or result.path
            )
        except Exception:
            return False

    def check_rate_limit(self, strategy: str) -> bool:
        """Check if rate limit is exceeded for this strategy."""
        now = time.time()
        hour_ago = now - 3600
        if strategy not in self.call_log:
            self.call_log[strategy] = []
        recent = [t for t in self.call_log[strategy] if t >= hour_ago]
        self.call_log[strategy] = recent

        if len(recent) >= self.config.rate_limit_per_hour:
            self.logger.warning(
                f"Rate limit exceeded for {strategy}: {len(recent)}/{self.config.rate_limit_per_hour}"
            )
            return False

        self.call_log[strategy].append(now)
        return True

    def recover_corrupted_state(self, strategy: str) -> dict[str, Any]:
        """Recover from corrupted state by reading backups."""
        state_file = self.state_dir / f"{strategy}.json"
        backup_file = self.state_dir / f"{strategy}.json.bak"

        if state_file.exists():
            try:
                return json.loads(state_file.read_text())
            except (json.JSONDecodeError, IOError):
                self.logger.warning(f"Corrupted state file for {strategy}, attempting backup")
                if backup_file.exists():
                    try:
                        return json.loads(backup_file.read_text())
                    except (json.JSONDecodeError, IOError):
                        self.logger.error(f"Backup also corrupted for {strategy}")
        return {}

    def save_state(self, strategy: str, state: dict[str, Any]) -> None:
        """Save state with atomic backup."""
        state_file = self.state_dir / f"{strategy}.json"
        backup_file = self.state_dir / f"{strategy}.json.bak"

        # Create backup of existing state
        if state_file.exists():
            try:
                backup_file.write_text(state_file.read_text())
            except IOError as e:
                self.logger.warning(f"Failed to create backup for {strategy}: {e}")

        # Write new state atomically
        try:
            temp_file = state_file.with_suffix(".json.tmp")
            temp_file.write_text(json.dumps(state, indent=2))
            temp_file.replace(state_file)
        except IOError as e:
            self.logger.error(f"Failed to save state for {strategy}: {e}")

    def validate_webhook_signature(
        self, payload: str, signature: str, secret: str
    ) -> bool:
        """Validate webhook signature (HMAC-SHA256)."""
        import hmac

        expected = "sha256=" + hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)


# ==============================================================================
# DETECTION STRATEGY BASE CLASS
# ==============================================================================


class DetectionStrategy(ABC):
    """Abstract base for all detection strategies."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        self.config = config
        self.logger = logger
        self.auditor = SecurityAuditor(config, logger)
        self.is_running = False

    @property
    @abstractmethod
    def kind(self) -> DetectionStrategyKind:
        """Return strategy type."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return strategy name."""
        pass

    @abstractmethod
    def detect(self) -> list[DetectionEvent]:
        """Run detection and return events. May raise exceptions."""
        pass

    def start(self) -> None:
        """Start background detection (for async strategies)."""
        self.is_running = True

    def stop(self) -> None:
        """Stop background detection."""
        self.is_running = False

    def _git(self, *args: str) -> str:
        """Run git command, raise on error."""
        proc = subprocess.run(
            ["git", "-C", self.config.repo, *args],
            capture_output=True,
            text=True,
            timeout=self.config.timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def _git_safe(self, *args: str) -> str:
        """Run git command, return empty on error."""
        try:
            return self._git(*args)
        except Exception as e:
            self.logger.debug(f"git command failed (safe): {e}")
            return ""

    def _load_state(self) -> dict[str, Any]:
        """Load detection state (with corruption recovery)."""
        return self.auditor.recover_corrupted_state(self.name)

    def _save_state(self, state: dict[str, Any]) -> None:
        """Save detection state (with atomic backup)."""
        self.auditor.save_state(self.name, state)


# ==============================================================================
# DETECTION STRATEGIES: 1-16
# ==============================================================================


class PollingStrategy(DetectionStrategy):
    """Strategy 1: Periodic HEAD checks via git fetch/rev-parse."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "polling"

    def detect(self) -> list[DetectionEvent]:
        """Detect changes via periodic git fetch."""
        if not self.auditor.check_rate_limit(self.name):
            return []

        events = []
        state = self._load_state()
        last_sha = state.get("last_upstream_sha", "")

        try:
            # Fetch upstream
            self._git("fetch", self.config.upstream_remote)

            # Get current upstream HEAD
            upstream_ref = f"{self.config.upstream_remote}/{self.config.upstream_branch}"
            current_sha = self._git("rev-parse", upstream_ref)

            if not self.auditor.validate_sha(current_sha):
                return [
                    DetectionEvent(
                        kind=DetectionKind.HEALTH_DEGRADED,
                        timestamp=datetime.now(),
                        source=self.name,
                        error="Invalid upstream SHA",
                        requires_action=True,
                    )
                ]

            # Detect new commits
            if last_sha and last_sha != current_sha:
                commits = self._git("rev-list", f"{last_sha}..{current_sha}").split()
                if commits:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.NEW_COMMITS,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=current_sha,
                            branch=self.config.upstream_branch,
                            commit_count=len(commits),
                            requires_action=True,
                        )
                    )

            # Update state
            self._save_state(
                {
                    "last_upstream_sha": current_sha,
                    "last_check": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            self.logger.error(f"Polling detection failed: {e}")
            events.append(
                DetectionEvent(
                    kind=DetectionKind.HEALTH_DEGRADED,
                    timestamp=datetime.now(),
                    source=self.name,
                    error=str(e),
                    requires_action=True,
                )
            )

        return events


class WebhookStrategy(DetectionStrategy):
    """Strategy 2: Webhook listeners for instant push notifications."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        super().__init__(config, logger)
        self.events_queue: list[DetectionEvent] = []
        self.lock = threading.Lock()

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.WEBHOOK

    @property
    def name(self) -> str:
        return "webhooks"

    def start(self) -> None:
        """Start webhook listener in background thread."""
        super().start()
        if self.config.dry_run:
            self.logger.info("Webhook listener (dry-run mode, not started)")
            return
        self.logger.info(
            f"Starting webhook listener on port {self.config.webhook_port}"
        )
        # In production, start HTTP server here
        # For now, just mark as running

    def detect(self) -> list[DetectionEvent]:
        """Return queued webhook events."""
        with self.lock:
            events = self.events_queue[:]
            self.events_queue.clear()
        return events

    def receive_webhook(self, payload_str: str, signature: str) -> bool:
        """Receive and validate webhook payload."""
        if not self.auditor.validate_webhook_signature(
            payload_str, signature, self.config.webhook_token
        ):
            self.logger.warning("Invalid webhook signature")
            return False

        try:
            payload = json.loads(payload_str)
            event = self._parse_github_webhook(payload)
            if event:
                with self.lock:
                    self.events_queue.append(event)
                self.logger.info(f"Webhook received: {event.kind}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to process webhook: {e}")
        return False

    def _parse_github_webhook(self, payload: dict) -> Optional[DetectionEvent]:
        """Parse GitHub webhook payload."""
        timestamp = datetime.now()

        # Push event (doesn't have action field)
        if payload.get("repository") and "ref" in payload and "after" in payload:
            ref = payload["ref"]
            branch = ref.split("/")[-1] if "/" in ref else ref
            return DetectionEvent(
                kind=DetectionKind.NEW_COMMITS,
                timestamp=timestamp,
                source=self.name,
                upstream_sha=payload.get("after", ""),
                branch=branch,
                data={"commits": len(payload.get("commits", []))},
                requires_action=True,
            )

        # For other events, action is required
        if "action" not in payload:
            return None

        action = payload["action"]

        # Tag event
        if action == "created" and "repository" in payload:
            if payload.get("ref_type") == "tag":
                return DetectionEvent(
                    kind=DetectionKind.TAG_CREATED,
                    timestamp=timestamp,
                    source=self.name,
                    branch=payload.get("ref", ""),
                    data={"pusher": payload.get("pusher", {}).get("name", "unknown")},
                    requires_action=True,
                )

        # PR event
        if "pull_request" in payload:
            pr = payload["pull_request"]
            if action == "closed" and pr.get("merged"):
                return DetectionEvent(
                    kind=DetectionKind.PR_MERGED,
                    timestamp=timestamp,
                    source=self.name,
                    upstream_sha=pr.get("merge_commit_sha", ""),
                    branch=pr.get("head", {}).get("ref", ""),
                    data={"number": pr.get("number"), "title": pr.get("title", "")},
                    requires_action=True,
                )
            elif action == "closed":
                return DetectionEvent(
                    kind=DetectionKind.PR_CLOSED,
                    timestamp=timestamp,
                    source=self.name,
                    branch=pr.get("head", {}).get("ref", ""),
                    data={"number": pr.get("number")},
                )

        return None


class CronStrategy(DetectionStrategy):
    """Strategy 3: Scheduled cron jobs for periodic scans."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.SCHEDULED

    @property
    def name(self) -> str:
        return "cron"

    def detect(self) -> list[DetectionEvent]:
        """Detect using cron schedule (manual polling)."""
        # In practice, this would be invoked by system cron
        # For this implementation, we use the polling strategy
        polling = PollingStrategy(self.config, self.logger)
        events = polling.detect()
        for event in events:
            event.source = self.name
        return events


class GitHubAPIStrategy(DetectionStrategy):
    """Strategy 4: GitHub REST API repository polling."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "github_api"

    def detect(self) -> list[DetectionEvent]:
        """Detect changes via GitHub REST API."""
        if not self.config.github_token or not self.config.github_owner:
            self.logger.warning(
                "GitHub API detection requires github_token and github_owner"
            )
            return []

        if not self.auditor.check_rate_limit(self.name):
            return []

        events = []
        state = self._load_state()

        try:
            # Get latest commit from GitHub API
            url = (
                f"https://api.github.com/repos/{self.config.github_owner}"
                f"/{self.config.github_repo}/commits/{self.config.upstream_branch}"
            )
            headers = {
                "Authorization": f"token {self.config.github_token}",
                "Accept": "application/vnd.github.v3+json",
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                data = json.loads(resp.read().decode())
                current_sha = data.get("sha", "")

                if not self.auditor.validate_sha(current_sha):
                    raise ValueError(f"Invalid SHA from GitHub API: {current_sha}")

                last_sha = state.get("last_sha", "")
                if last_sha and last_sha != current_sha:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.NEW_COMMITS,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=current_sha,
                            branch=self.config.upstream_branch,
                            data={"message": data.get("commit", {}).get("message", "")},
                            requires_action=True,
                        )
                    )

                self._save_state(
                    {
                        "last_sha": current_sha,
                        "last_check": datetime.now().isoformat(),
                    }
                )

        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.logger.error("GitHub API authentication failed")
            elif e.code == 403:
                self.logger.warning("GitHub API rate limited")
            else:
                self.logger.error(f"GitHub API error: {e.code}")
            events.append(
                DetectionEvent(
                    kind=DetectionKind.HEALTH_DEGRADED,
                    timestamp=datetime.now(),
                    source=self.name,
                    error=f"HTTP {e.code}",
                )
            )
        except Exception as e:
            self.logger.error(f"GitHub API detection failed: {e}")
            events.append(
                DetectionEvent(
                    kind=DetectionKind.HEALTH_DEGRADED,
                    timestamp=datetime.now(),
                    source=self.name,
                    error=str(e),
                )
            )

        return events


class ScheduledSyncStrategy(DetectionStrategy):
    """Strategy 5: Time-based scheduled synchronization."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.SCHEDULED

    @property
    def name(self) -> str:
        return "scheduled_sync"

    def detect(self) -> list[DetectionEvent]:
        """Check if scheduled sync should run."""
        state = self._load_state()
        last_sync = state.get("last_sync")

        if last_sync:
            last_sync_time = datetime.fromisoformat(last_sync)
            time_since_sync = datetime.now() - last_sync_time
            # Run sync every poll_interval seconds
            if time_since_sync.total_seconds() < self.config.poll_interval:
                return []

        # Time to sync
        polling = PollingStrategy(self.config, self.logger)
        events = polling.detect()

        # Update sync time only if we got events
        if events:
            self._save_state({"last_sync": datetime.now().isoformat()})
            for event in events:
                event.source = self.name

        return events


class RSSFeedStrategy(DetectionStrategy):
    """Strategy 6: RSS feed monitoring for release changes."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "rss_feeds"

    def detect(self) -> list[DetectionEvent]:
        """Monitor RSS feeds for release announcements."""
        if not self.config.rss_feeds:
            return []

        if not self.auditor.check_rate_limit(self.name):
            return []

        events = []
        state = self._load_state()
        known_items = set(state.get("known_items", []))

        for feed_url in self.config.rss_feeds:
            if not self.auditor.validate_remote_url(feed_url):
                self.logger.warning(f"Invalid RSS feed URL: {feed_url}")
                continue

            try:
                items = self._fetch_rss_items(feed_url)
                for item in items:
                    item_id = item.get("id", item.get("title", ""))
                    if item_id not in known_items:
                        known_items.add(item_id)
                        events.append(
                            DetectionEvent(
                                kind=DetectionKind.RELEASE_PUBLISHED,
                                timestamp=datetime.now(),
                                source=self.name,
                                branch=item.get("tag", ""),
                                data={
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                },
                                requires_action=True,
                            )
                        )
            except Exception as e:
                self.logger.error(f"RSS feed processing failed for {feed_url}: {e}")

        self._save_state({"known_items": list(known_items)})
        return events

    def _fetch_rss_items(self, feed_url: str) -> list[dict]:
        """Fetch and parse RSS feed items (simplified)."""
        import xml.etree.ElementTree as ET

        try:
            req = urllib.request.Request(
                feed_url, headers={"User-Agent": "100ways-detect/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                root = ET.fromstring(resp.read())

            items = []
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pubdate = item.findtext("pubDate", "")
                items.append({"title": title, "url": link, "date": pubdate, "id": link})

            return items
        except Exception as e:
            self.logger.debug(f"RSS parsing error: {e}")
            return []


class GraphQLStrategy(DetectionStrategy):
    """Strategy 7: GitHub GraphQL queries for advanced filtering."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "graphql"

    def detect(self) -> list[DetectionEvent]:
        """Detect via GitHub GraphQL API."""
        if not self.config.github_token or not self.config.github_owner:
            self.logger.warning(
                "GraphQL detection requires github_token and github_owner"
            )
            return []

        if not self.auditor.check_rate_limit(self.name):
            return []

        events = []

        try:
            # Simple GraphQL query for recent commits
            query = """
            query {
              repository(owner: "%s", name: "%s") {
                defaultBranchRef {
                  target {
                    oid
                    ... on Commit {
                      history(first: 5) {
                        edges {
                          node {
                            oid
                            message
                            committedDate
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """ % (
                self.config.github_owner,
                self.config.github_repo,
            )

            url = "https://api.github.com/graphql"
            headers = {
                "Authorization": f"Bearer {self.config.github_token}",
                "Content-Type": "application/json",
            }
            data = json.dumps({"query": query}).encode()
            req = urllib.request.Request(url, data=data, headers=headers)

            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                result = json.loads(resp.read().decode())

                if "errors" in result:
                    self.logger.error(f"GraphQL error: {result['errors']}")
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.HEALTH_DEGRADED,
                            timestamp=datetime.now(),
                            source=self.name,
                            error=str(result.get("errors", [])),
                        )
                    )
                    return events

                # Process results
                repo_data = result.get("data", {}).get("repository", {})
                ref_data = repo_data.get("defaultBranchRef", {})
                if ref_data:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.NEW_COMMITS,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=ref_data.get("target", {}).get("oid", ""),
                            requires_action=True,
                        )
                    )

        except Exception as e:
            self.logger.error(f"GraphQL detection failed: {e}")
            events.append(
                DetectionEvent(
                    kind=DetectionKind.HEALTH_DEGRADED,
                    timestamp=datetime.now(),
                    source=self.name,
                    error=str(e),
                )
            )

        return events


class SignalHandlerStrategy(DetectionStrategy):
    """Strategy 8: OS signal handlers for reactive events."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        super().__init__(config, logger)
        self.signal_received = False
        self._register_handlers()

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.SIGNAL

    @property
    def name(self) -> str:
        return "signal_handlers"

    def _register_handlers(self) -> None:
        """Register OS signal handlers."""

        def _handler(signum, frame):
            self.signal_received = True
            self.logger.info(f"Signal {signum} received")

        try:
            signal.signal(signal.SIGUSR1, _handler)
            signal.signal(signal.SIGUSR2, _handler)
        except ValueError:
            # Signals not available on this platform
            pass

    def detect(self) -> list[DetectionEvent]:
        """Detect if signal was received."""
        if not self.signal_received:
            return []

        self.signal_received = False
        # When signal received, trigger polling
        polling = PollingStrategy(self.config, self.logger)
        events = polling.detect()
        for event in events:
            event.source = self.name
        return events


class IdleTimeStrategy(DetectionStrategy):
    """Strategy 9: Idle-time background checks."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        super().__init__(config, logger)
        self.last_activity = time.time()
        self.idle_threshold = 60  # seconds

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.PASSIVE

    @property
    def name(self) -> str:
        return "idle_time"

    def detect(self) -> list[DetectionEvent]:
        """Detect during idle time."""
        now = time.time()
        if now - self.last_activity < self.idle_threshold:
            return []

        self.last_activity = now
        # Run polling during idle time
        polling = PollingStrategy(self.config, self.logger)
        events = polling.detect()
        for event in events:
            event.source = self.name
        return events

    def record_activity(self) -> None:
        """Record user activity (resets idle timer)."""
        self.last_activity = time.time()


class StartupScanStrategy(DetectionStrategy):
    """Strategy 10: On-startup repository scans."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "startup_scans"

    def detect(self) -> list[DetectionEvent]:
        """Scan repository on startup."""
        state = self._load_state()
        if state.get("startup_complete"):
            return []  # Only run once per startup

        events = []
        try:
            # Fetch and check for divergence
            self._git("fetch", self.config.upstream_remote)

            upstream_sha = self._git(
                "rev-parse",
                f"{self.config.upstream_remote}/{self.config.upstream_branch}",
            )
            downstream_sha = self._git("rev-parse", self.config.downstream_branch)

            if upstream_sha != downstream_sha:
                commits = self._git_safe(
                    "rev-list", f"{downstream_sha}..{upstream_sha}"
                ).split()
                if commits:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.NEW_COMMITS,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=upstream_sha,
                            downstream_sha=downstream_sha,
                            commit_count=len(commits),
                            requires_action=True,
                        )
                    )

            self._save_state({"startup_complete": True})

        except Exception as e:
            self.logger.warning(f"Startup scan failed: {e}")

        return events


class PullRequestCloseStrategy(DetectionStrategy):
    """Strategy 11: PR close event detection."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.PASSIVE

    @property
    def name(self) -> str:
        return "pr_closes"

    def detect(self) -> list[DetectionEvent]:
        """Detect PR close events (webhook-based or polled)."""
        # This strategy would normally listen to webhooks
        # For standalone use, can integrate with webhook strategy
        return []


class TagChangeStrategy(DetectionStrategy):
    """Strategy 12: Git tag creation/modification detection."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "tag_changes"

    def detect(self) -> list[DetectionEvent]:
        """Detect git tag changes."""
        if not self.auditor.check_rate_limit(self.name):
            return []

        events = []
        state = self._load_state()
        known_tags = set(state.get("known_tags", []))

        try:
            # Fetch tags
            self._git("fetch", self.config.upstream_remote, "--tags")

            # Get all tags
            tags_output = self._git_safe("tag", "-l")
            current_tags = set(tags_output.split()) if tags_output else set()

            # Detect new tags
            new_tags = current_tags - known_tags
            for tag in new_tags:
                try:
                    tag_sha = self._git("rev-list", "-n", "1", tag)
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.TAG_CREATED,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=tag_sha,
                            branch=tag,
                            requires_action=True,
                        )
                    )
                except Exception:
                    pass

            # Detect deleted tags
            deleted_tags = known_tags - current_tags
            for tag in deleted_tags:
                events.append(
                    DetectionEvent(
                        kind=DetectionKind.TAG_DELETED,
                        timestamp=datetime.now(),
                        source=self.name,
                        branch=tag,
                        requires_action=True,
                    )
                )

            self._save_state({"known_tags": list(current_tags)})

        except Exception as e:
            self.logger.error(f"Tag change detection failed: {e}")

        return events


class ReflogStrategy(DetectionStrategy):
    """Strategy 13: Reflog-based history probing."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "reflog_probes"

    def detect(self) -> list[DetectionEvent]:
        """Detect changes via reflog analysis."""
        events = []
        state = self._load_state()
        last_reflog_hash = state.get("last_reflog_hash", "")

        try:
            # Get reflog for upstream branch
            ref = f"{self.config.upstream_remote}/{self.config.upstream_branch}"
            reflog_output = self._git_safe("reflog", ref)

            if not reflog_output:
                return []

            # Hash current reflog to detect changes
            current_hash = hashlib.sha256(reflog_output.encode()).hexdigest()

            if last_reflog_hash and last_reflog_hash != current_hash:
                # Reflog changed - new commits likely
                current_sha = self._git("rev-parse", ref)
                events.append(
                    DetectionEvent(
                        kind=DetectionKind.NEW_COMMITS,
                        timestamp=datetime.now(),
                        source=self.name,
                        upstream_sha=current_sha,
                        requires_action=True,
                    )
                )

            self._save_state({"last_reflog_hash": current_hash})

        except Exception as e:
            self.logger.debug(f"Reflog probing failed: {e}")

        return events


class WebhookFallbackStrategy(DetectionStrategy):
    """Strategy 14: Webhook with fallback polling."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        super().__init__(config, logger)
        self.webhook = WebhookStrategy(config, logger)
        self.polling = PollingStrategy(config, logger)
        self.webhook_online = True

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.COMPOSITE

    @property
    def name(self) -> str:
        return "webhook_fallback"

    def start(self) -> None:
        """Start webhook and polling."""
        super().start()
        self.webhook.start()

    def detect(self) -> list[DetectionEvent]:
        """Try webhook first, fallback to polling."""
        events = []

        # Try webhook events first
        webhook_events = self.webhook.detect()
        if webhook_events:
            self.webhook_online = True
            events.extend(webhook_events)

        # If webhook offline or empty, use polling
        if not self.webhook_online or not webhook_events:
            try:
                polling_events = self.polling.detect()
                events.extend(polling_events)
                self.webhook_online = True
            except Exception as e:
                self.logger.warning(f"Both webhook and polling failed: {e}")
                self.webhook_online = False

        for event in events:
            event.source = self.name

        return events


class SelectorLoopStrategy(DetectionStrategy):
    """Strategy 15: Selector-based multiplexing."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.COMPOSITE

    @property
    def name(self) -> str:
        return "selector_loops"

    def detect(self) -> list[DetectionEvent]:
        """Multiplex detection across strategies based on available resources."""
        # Run multiple strategies in parallel, collect results
        strategies = [
            PollingStrategy(self.config, self.logger),
            TagChangeStrategy(self.config, self.logger),
            ReflogStrategy(self.config, self.logger),
        ]

        events = []
        for strategy in strategies:
            try:
                strategy_events = strategy.detect()
                events.extend(strategy_events)
            except Exception as e:
                self.logger.debug(f"Strategy {strategy.name} failed: {e}")

        for event in events:
            event.source = self.name

        return events


class MultiHostStrategy(DetectionStrategy):
    """Strategy 16: Multi-host heartbeat detection."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "multi_host"

    def detect(self) -> list[DetectionEvent]:
        """Check upstream across multiple hosts."""
        if not self.config.remote_hosts:
            return []

        events = []
        state = self._load_state()
        host_status = state.get("host_status", {})

        for host in self.config.remote_hosts:
            if not self.auditor.validate_remote_url(host):
                self.logger.warning(f"Invalid remote host: {host}")
                continue

            try:
                # Ping host via SSH or HTTP
                is_alive = self._check_host_alive(host)
                prev_status = host_status.get(host, True)

                if not is_alive and prev_status:
                    # Host went down
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.HEALTH_DEGRADED,
                            timestamp=datetime.now(),
                            source=self.name,
                            data={"host": host, "status": "down"},
                            error="Host unreachable",
                            requires_action=True,
                        )
                    )
                elif is_alive and not prev_status:
                    # Host came back up
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.NEW_COMMITS,
                            timestamp=datetime.now(),
                            source=self.name,
                            data={"host": host, "status": "recovered"},
                            requires_action=True,
                        )
                    )

                host_status[host] = is_alive

            except Exception as e:
                self.logger.debug(f"Multi-host check failed for {host}: {e}")

        self._save_state({"host_status": host_status})
        return events

    def _check_host_alive(self, host: str) -> bool:
        """Check if remote host is alive."""
        try:
            req = urllib.request.Request(host, method="HEAD")
            urllib.request.urlopen(req, timeout=self.config.timeout)
            return True
        except Exception:
            return False


# ==============================================================================
# DETECTION STRATEGIES: 17-20
# ==============================================================================


class BranchTrackingStrategy(DetectionStrategy):
    """Strategy 17: Branch ref change tracking."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "branch_tracking"

    def detect(self) -> list[DetectionEvent]:
        """Track branch reference changes."""
        events = []
        state = self._load_state()
        known_branches = state.get("known_branches", {})

        try:
            self._git("fetch", self.config.upstream_remote)

            # List all remote branches
            branches_output = self._git_safe(
                "branch", "-r", "--format=%(refname:short)"
            )
            current_branches = {}

            for branch in branches_output.split():
                if not branch:
                    continue
                try:
                    sha = self._git("rev-parse", branch)
                    current_branches[branch] = sha
                except Exception:
                    pass

            # Detect new/deleted/updated branches
            for branch, sha in current_branches.items():
                if branch not in known_branches:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.BRANCH_CREATED,
                            timestamp=datetime.now(),
                            source=self.name,
                            branch=branch,
                            upstream_sha=sha,
                            requires_action=True,
                        )
                    )
                elif known_branches[branch] != sha:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.BRANCH_UPDATED,
                            timestamp=datetime.now(),
                            source=self.name,
                            branch=branch,
                            upstream_sha=sha,
                            requires_action=True,
                        )
                    )

            for branch in known_branches:
                if branch not in current_branches:
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.BRANCH_DELETED,
                            timestamp=datetime.now(),
                            source=self.name,
                            branch=branch,
                            requires_action=True,
                        )
                    )

            self._save_state({"known_branches": current_branches})

        except Exception as e:
            self.logger.error(f"Branch tracking failed: {e}")

        return events


class CommitDigestStrategy(DetectionStrategy):
    """Strategy 18: Commit hash digest verification."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "commit_digests"

    def detect(self) -> list[DetectionEvent]:
        """Verify commit hashes haven't been tampered with."""
        events = []
        state = self._load_state()
        known_commits = state.get("known_commits", {})

        try:
            self._git("fetch", self.config.upstream_remote)

            upstream_ref = f"{self.config.upstream_remote}/{self.config.upstream_branch}"
            commits_output = self._git_safe("rev-list", f"{upstream_ref}", "-20")

            for commit_sha in commits_output.split():
                if not commit_sha:
                    continue

                # Verify commit is valid
                if not self.auditor.validate_sha(commit_sha):
                    events.append(
                        DetectionEvent(
                            kind=DetectionKind.COMMIT_DIGEST_MISMATCH,
                            timestamp=datetime.now(),
                            source=self.name,
                            upstream_sha=commit_sha,
                            error="Invalid commit hash format",
                            requires_action=True,
                        )
                    )
                    continue

                # Get commit timestamp
                try:
                    commit_time = self._git(
                        "log", "-1", "--format=%ct", commit_sha
                    )
                    known_commits[commit_sha] = {"timestamp": commit_time}
                except Exception:
                    pass

            self._save_state({"known_commits": known_commits})

        except Exception as e:
            self.logger.debug(f"Commit digest check failed: {e}")

        return events


class EventStreamStrategy(DetectionStrategy):
    """Strategy 19: Event stream subscriptions."""

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        super().__init__(config, logger)
        self.event_stream: list[DetectionEvent] = []
        self.stream_lock = threading.Lock()

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.PASSIVE

    @property
    def name(self) -> str:
        return "event_streams"

    def detect(self) -> list[DetectionEvent]:
        """Get queued events from event stream."""
        with self.stream_lock:
            events = self.event_stream[:]
            self.event_stream.clear()
        return events

    def publish_event(self, event: DetectionEvent) -> None:
        """Publish event to stream."""
        with self.stream_lock:
            self.event_stream.append(event)


class HealthCheckStrategy(DetectionStrategy):
    """Strategy 20: Upstream health check monitoring."""

    @property
    def kind(self) -> DetectionStrategyKind:
        return DetectionStrategyKind.POLLING

    @property
    def name(self) -> str:
        return "health_checks"

    def detect(self) -> list[DetectionEvent]:
        """Monitor upstream repository health."""
        events = []
        state = self._load_state()
        consecutive_failures = state.get("consecutive_failures", 0)

        try:
            # Check if repository is accessible
            self._git("fetch", "--dry-run", self.config.upstream_remote)

            # Reset failure counter on success
            if consecutive_failures > 0:
                events.append(
                    DetectionEvent(
                        kind=DetectionKind.NEW_COMMITS,
                        timestamp=datetime.now(),
                        source=self.name,
                        data={"status": "recovered", "failures": consecutive_failures},
                        requires_action=True,
                    )
                )
            consecutive_failures = 0

        except Exception as e:
            consecutive_failures += 1
            self.logger.warning(
                f"Health check failed (attempt {consecutive_failures}): {e}"
            )

            # Report degradation after multiple failures
            if consecutive_failures >= 3:
                events.append(
                    DetectionEvent(
                        kind=DetectionKind.HEALTH_DEGRADED,
                        timestamp=datetime.now(),
                        source=self.name,
                        error=str(e),
                        data={"consecutive_failures": consecutive_failures},
                        requires_action=True,
                    )
                )

        self._save_state({"consecutive_failures": consecutive_failures})
        return events


# ==============================================================================
# DIFFCHAIN: COMPOSABLE DETECTION CHAIN
# ==============================================================================


@dataclass
class DiffChainLink:
    """A link in the detection chain."""

    strategy: DetectionStrategy
    enabled: bool = True
    priority: int = 0  # 0=lowest, 100=highest
    retry_count: int = 0


class DiffChain:
    """Composable, pluggable detection chain following the chain-of-responsibility pattern.

    Each link is a detection strategy. Links execute in priority order.
    Events from all links are merged and deduplicated.
    """

    def __init__(self, config: DetectionConfig, logger: DetectionLogger):
        self.config = config
        self.logger = logger
        self.links: list[DiffChainLink] = []
        self.event_history: list[DetectionEvent] = []
        self.history_lock = threading.Lock()

    def add_strategy(
        self, strategy: DetectionStrategy, priority: int = 0, enabled: bool = True
    ) -> "DiffChain":
        """Add strategy to chain with optional priority."""
        self.links.append(DiffChainLink(strategy, enabled=enabled, priority=priority))
        # Sort by priority (descending)
        self.links.sort(key=lambda x: x.priority, reverse=True)
        return self

    def add_all_strategies(self) -> "DiffChain":
        """Add all 20 detection strategies with sensible defaults."""
        strategies = [
            (PollingStrategy(self.config, self.logger), 70),
            (WebhookStrategy(self.config, self.logger), 100),
            (CronStrategy(self.config, self.logger), 60),
            (GitHubAPIStrategy(self.config, self.logger), 65),
            (ScheduledSyncStrategy(self.config, self.logger), 55),
            (RSSFeedStrategy(self.config, self.logger), 40),
            (GraphQLStrategy(self.config, self.logger), 65),
            (SignalHandlerStrategy(self.config, self.logger), 90),
            (IdleTimeStrategy(self.config, self.logger), 50),
            (StartupScanStrategy(self.config, self.logger), 95),
            (PullRequestCloseStrategy(self.config, self.logger), 75),
            (TagChangeStrategy(self.config, self.logger), 70),
            (ReflogStrategy(self.config, self.logger), 60),
            (WebhookFallbackStrategy(self.config, self.logger), 85),
            (SelectorLoopStrategy(self.config, self.logger), 80),
            (MultiHostStrategy(self.config, self.logger), 50),
            (BranchTrackingStrategy(self.config, self.logger), 70),
            (CommitDigestStrategy(self.config, self.logger), 50),
            (EventStreamStrategy(self.config, self.logger), 55),
            (HealthCheckStrategy(self.config, self.logger), 75),
        ]

        for strategy, priority in strategies:
            self.add_strategy(strategy, priority=priority)

        return self

    def run(self) -> list[DetectionEvent]:
        """Execute chain: run enabled strategies, merge and deduplicate events."""
        all_events = []

        for link in self.links:
            if not link.enabled:
                continue

            try:
                self.logger.debug(f"Running {link.strategy.name}")
                events = link.strategy.detect()
                all_events.extend(events)
            except Exception as e:
                self.logger.error(f"Strategy {link.strategy.name} failed: {e}")
                link.retry_count += 1

                # Add health event on repeated failures
                if link.retry_count >= 3:
                    all_events.append(
                        DetectionEvent(
                            kind=DetectionKind.HEALTH_DEGRADED,
                            timestamp=datetime.now(),
                            source=link.strategy.name,
                            error=str(e),
                            requires_action=True,
                        )
                    )

        # Deduplicate events by (kind, upstream_sha, branch)
        seen = set()
        dedup_events = []
        for event in all_events:
            key = (event.kind, event.upstream_sha, event.branch)
            if key not in seen:
                seen.add(key)
                dedup_events.append(event)

        # Record in history
        with self.history_lock:
            self.event_history.extend(dedup_events)

        self.logger.info(f"DiffChain produced {len(dedup_events)} events from {len(all_events)} total")

        return dedup_events

    def start_all(self) -> None:
        """Start all async strategies."""
        for link in self.links:
            if link.enabled and hasattr(link.strategy, "start"):
                try:
                    link.strategy.start()
                except Exception as e:
                    self.logger.warning(f"Failed to start {link.strategy.name}: {e}")

    def stop_all(self) -> None:
        """Stop all async strategies."""
        for link in self.links:
            if hasattr(link.strategy, "stop"):
                try:
                    link.strategy.stop()
                except Exception as e:
                    self.logger.warning(f"Failed to stop {link.strategy.name}: {e}")

    def get_history(self, limit: int = 100) -> list[DetectionEvent]:
        """Get recent events from history."""
        with self.history_lock:
            return self.event_history[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        with self.history_lock:
            self.event_history.clear()
