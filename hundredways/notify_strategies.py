"""NOTIFY strategies: 10+ ways to alert on sync events.

Each strategy sends notifications about gate decisions, port status, etc.
Strategies compose via NotifyChain for multi-channel delivery.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


@dataclass
class NotifyMessage:
    """A notification message."""
    title: str
    body: str
    level: str  # info, warning, error
    metadata: dict = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}


class NotifyStrategy(ABC):
    """Base class for notify strategies."""

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @abstractmethod
    def notify(self, message: NotifyMessage) -> bool:
        """Send notification. Return True if successful."""
        pass


class StdoutNotify(NotifyStrategy):
    """Print to stdout: basic console logging."""

    def name(self) -> str:
        return "notify.stdout"

    def notify(self, message: NotifyMessage) -> bool:
        """Print to console."""
        prefix = f"[{message.level.upper()}]"
        print(f"{prefix} {message.title}")
        if message.body:
            print(f"  {message.body}")
        return True


class JsonLogNotify(NotifyStrategy):
    """JSON log file: structured logging."""

    def name(self) -> str:
        return "notify.json-log"

    def __init__(self, log_path: str = "/tmp/100ways_notify.jsonl"):
        self.log_path = log_path

    def notify(self, message: NotifyMessage) -> bool:
        """Append JSON line to log file."""
        try:
            log_entry = {
                "timestamp": message.timestamp,
                "level": message.level,
                "title": message.title,
                "body": message.body,
                "metadata": message.metadata
            }
            with open(self.log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            return True
        except Exception:
            return False


class EmailNotify(NotifyStrategy):
    """Email via SMTP."""

    def name(self) -> str:
        return "notify.email"

    def __init__(self, smtp_host: str, smtp_port: int, from_addr: str, to_addrs: list[str]):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    def notify(self, message: NotifyMessage) -> bool:
        """Send email."""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)
            msg["Subject"] = f"[{message.level.upper()}] {message.title}"

            body_text = f"{message.body}\n\nMetadata: {json.dumps(message.metadata, indent=2)}"
            msg.attach(MIMEText(body_text, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return True
        except Exception:
            return False


class WebhookNotify(NotifyStrategy):
    """POST to webhook URL."""

    def name(self) -> str:
        return "notify.webhook"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, message: NotifyMessage) -> bool:
        """POST JSON to webhook."""
        try:
            import urllib.request
            import json

            payload = {
                "title": message.title,
                "body": message.body,
                "level": message.level,
                "timestamp": message.timestamp,
                "metadata": message.metadata
            }

            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False


class SlackNotify(NotifyStrategy):
    """Slack webhook integration."""

    def name(self) -> str:
        return "notify.slack"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, message: NotifyMessage) -> bool:
        """Send Slack message via webhook."""
        try:
            import urllib.request
            import json

            # Slack color by level
            color_map = {"info": "#36a64f", "warning": "#ff9900", "error": "#ff0000"}
            color = color_map.get(message.level, "#808080")

            payload = {
                "attachments": [{
                    "color": color,
                    "title": message.title,
                    "text": message.body,
                    "footer": "100Ways Sync",
                    "ts": int(datetime.fromisoformat(message.timestamp).timestamp())
                }]
            }

            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False


class DiscordNotify(NotifyStrategy):
    """Discord webhook integration."""

    def name(self) -> str:
        return "notify.discord"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, message: NotifyMessage) -> bool:
        """Send Discord message via webhook."""
        try:
            import urllib.request
            import json

            payload = {
                "embeds": [{
                    "title": message.title,
                    "description": message.body,
                    "color": 3066993 if message.level == "info" else (16776960 if message.level == "warning" else 16711680)
                }]
            }

            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False


class SyslogNotify(NotifyStrategy):
    """Syslog integration."""

    def name(self) -> str:
        return "notify.syslog"

    def notify(self, message: NotifyMessage) -> bool:
        """Send to syslog."""
        try:
            import syslog

            # Map levels to syslog priorities
            priority_map = {
                "info": syslog.LOG_INFO,
                "warning": syslog.LOG_WARNING,
                "error": syslog.LOG_ERR
            }

            priority = priority_map.get(message.level, syslog.LOG_INFO)
            syslog.syslog(priority, f"{message.title}: {message.body}")
            return True
        except Exception:
            return False


class FileNotify(NotifyStrategy):
    """Append to file."""

    def name(self) -> str:
        return "notify.file"

    def __init__(self, file_path: str):
        self.file_path = file_path

    def notify(self, message: NotifyMessage) -> bool:
        """Append to file."""
        try:
            with open(self.file_path, "a") as f:
                f.write(f"[{message.timestamp}] [{message.level.upper()}] {message.title}\n")
                if message.body:
                    f.write(f"  {message.body}\n")
            return True
        except Exception:
            return False


class PagerDutyNotify(NotifyStrategy):
    """PagerDuty incident creation."""

    def name(self) -> str:
        return "notify.pagerduty"

    def __init__(self, integration_key: str):
        self.integration_key = integration_key

    def notify(self, message: NotifyMessage) -> bool:
        """Create PagerDuty incident."""
        try:
            import urllib.request
            import json

            # Only trigger on errors
            if message.level != "error":
                return True

            payload = {
                "routing_key": self.integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": message.title,
                    "severity": "critical" if message.level == "error" else "warning",
                    "source": "100Ways Sync",
                    "custom_details": message.metadata
                }
            }

            req = urllib.request.Request(
                "https://events.pagerduty.com/v2/enqueue",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            return False


class NotifyChain:
    """Compose multiple notify strategies."""

    def __init__(self, strategies: list[NotifyStrategy] = None):
        self.strategies = strategies or [StdoutNotify()]
        self.history = []

    def notify(self, message: NotifyMessage) -> list[bool]:
        """Send message via all strategies."""
        results = []
        for strategy in self.strategies:
            result = strategy.notify(message)
            results.append(result)
        self.history.append((message, results))
        return results

    def add_strategy(self, strategy: NotifyStrategy):
        """Add a strategy to the chain."""
        self.strategies.append(strategy)

    def filter_by_level(self, level: str) -> NotifyChain:
        """Create new chain that only sends at or above level."""
        level_order = {"info": 0, "warning": 1, "error": 2}
        new_chain = NotifyChain()

        for strategy in self.strategies:
            # Wrap strategy with level filter
            class FilteredStrategy(NotifyStrategy):
                def __init__(self, inner, min_level):
                    self.inner = inner
                    self.min_level = level_order.get(min_level, 0)

                def name(self):
                    return f"{self.inner.name()}-filtered"

                def notify(self, msg):
                    if level_order.get(msg.level, 0) >= self.min_level:
                        return self.inner.notify(msg)
                    return True

            new_chain.add_strategy(FilteredStrategy(strategy, level))

        return new_chain

    def to_dict(self) -> dict:
        """Serialize chain state."""
        return {
            "strategies": [s.name() for s in self.strategies],
            "count": len(self.strategies),
            "history_count": len(self.history)
        }
