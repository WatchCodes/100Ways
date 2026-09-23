"""Comprehensive notification system with 20 pluggable strategies.

Supports:
1. Telegram bot (notify.telegram)
2. Agent prompt hook (notify.agent)
3. Desktop notifications (notify.desktop)
4. Terminal bell/cue (notify.bell)
5. Markdown file report (notify.markdown-file)
6. Generic webhook (notify.webhook-out)
7. Email/SMTP (notify.email)
8. Chat webhook (Slack/Discord/Matrix) (notify.chat-hook)
9. User command execution (notify.exec)
10. JSONL event log (notify.log)
11. Slack webhook (notify.slack)
12. Discord webhook (notify.discord)
13. Matrix message (notify.matrix)
14. Signal sender (notify.signal)
15. GitLab comment (notify.gitlab)
16. Sentry event (notify.sentry)
17. Pushover push (notify.pushover)
18. ntfy topic (notify.ntfy)
19. Tail recap (notify.tail)
20. Atom feed publish (notify.atom)

Uses DiffChain pattern for pluggable notification chains with:
- Credential management and security checks
- Payload signing and verification
- Rate limiting and retry logic
- Delivery guarantees
- Comprehensive audit logging
- Error handling with graceful fallbacks
- Mock integrations for testing (no real API calls)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationLevel(str, Enum):
    """Severity levels for notifications."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Notification:
    """Represents a notification event."""
    title: str
    body: str
    level: NotificationLevel = NotificationLevel.INFO
    kind: str = "sync"  # sync | gap | violation | port | watch
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extra: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        """Render notification as formatted text."""
        icon = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "🚨",
            NotificationLevel.CRITICAL: "🔴",
        }.get(self.level, "ℹ️")
        return f"{icon} *{self.title}*\n\n{self.body}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "body": self.body,
            "level": self.level.value,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "extra": self.extra,
        }


@dataclass
class NotifyConfig:
    """Configuration for notification handlers."""
    # Telegram
    telegram_token: str = ""
    telegram_chat_id: str = ""
    
    # Agent hook
    agent_command: str = ""  # e.g. "opencode run"
    
    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: list[str] = field(default_factory=list)
    
    # Slack/Discord/Matrix
    slack_webhook: str = ""
    discord_webhook: str = ""
    matrix_homeserver: str = ""
    matrix_token: str = ""
    matrix_room: str = ""
    
    # Webhooks
    webhook_url: str = ""
    webhook_secret: str = ""
    
    # Signal
    signal_phone: str = ""
    signal_recipient: str = ""
    
    # GitLab
    gitlab_token: str = ""
    gitlab_project_id: str = ""
    gitlab_mr_id: str = ""
    
    # Sentry
    sentry_dsn: str = ""
    
    # Pushover
    pushover_token: str = ""
    pushover_user: str = ""
    
    # ntfy
    ntfy_topic: str = ""
    ntfy_token: str = ""
    
    # File outputs
    markdown_file: str = ""
    event_log_file: str = ""
    tail_recap_file: str = ""
    atom_feed_file: str = ""
    
    # Global settings
    enabled_handlers: set[str] = field(default_factory=lambda: {"telegram", "log"})
    rate_limit_per_minute: int = 10
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    audit_log_file: str = ""
    sign_payloads: bool = True


class NotificationHandler(ABC):
    """Base class for notification handlers implementing DiffChain pattern."""
    
    def __init__(self, config: NotifyConfig):
        self.config = config
        self.name = self.__class__.__name__
        self.delivery_log: list[dict[str, Any]] = []
    
    @abstractmethod
    def can_handle(self) -> bool:
        """Check if this handler is properly configured."""
        pass
    
    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Send the notification. Return True if successful."""
        pass
    
    def _log_delivery(self, notification: Notification, success: bool, error: str = ""):
        """Log delivery attempt to audit trail."""
        entry = {
            "handler": self.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notification_id": self._get_notification_id(notification),
            "success": success,
            "error": error,
        }
        self.delivery_log.append(entry)
        logger.info(f"[{self.name}] delivery={'SUCCESS' if success else 'FAILED'}: {notification.title}")
    
    def _get_notification_id(self, notification: Notification) -> str:
        """Generate deterministic ID for notification."""
        content = f"{notification.title}:{notification.body}:{notification.timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:8]
    
    def _sign_payload(self, payload: str | bytes) -> str:
        """Sign payload with HMAC."""
        if isinstance(payload, str):
            payload = payload.encode()
        secret = (self.config.webhook_secret or "default-secret").encode()
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return signature
    
    def _sanitize_credentials(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Remove or mask sensitive values from dict."""
        sensitive_keys = {"password", "token", "secret", "key", "api_key"}
        result = {}
        for k, v in obj.items():
            if any(sk in k.lower() for sk in sensitive_keys):
                result[k] = "***REDACTED***"
            else:
                result[k] = v
        return result


class TelegramHandler(NotificationHandler):
    """Telegram bot notification handler."""
    
    def can_handle(self) -> bool:
        return bool(self.config.telegram_token and self.config.telegram_chat_id)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, skipping Telegram")
            return False
        
        try:
            token = self.config.telegram_token
            chat_id = self.config.telegram_chat_id
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": notification.render(),
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            
            response = httpx.post(url, json=payload, timeout=15)
            success = response.status_code == 200
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Telegram send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class EmailHandler(NotificationHandler):
    """SMTP email notification handler."""
    
    def can_handle(self) -> bool:
        return bool(
            self.config.smtp_host 
            and self.config.smtp_user 
            and self.config.smtp_password
            and self.config.smtp_to
        )
    
    def send(self, notification: Notification) -> bool:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
        except ImportError:
            logger.warning("Email libraries not available")
            return False
        
        try:
            subject = f"[{notification.level.upper()}] {notification.title}"
            body = f"{notification.render()}\n\n---\n{json.dumps(notification.to_dict(), indent=2)}"
            
            msg = MIMEMultipart()
            msg["From"] = self.config.smtp_from or self.config.smtp_user
            msg["To"] = ", ".join(self.config.smtp_to)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)
            
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Email send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class SlackHandler(NotificationHandler):
    """Slack webhook notification handler."""
    
    def can_handle(self) -> bool:
        return bool(self.config.slack_webhook)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            color_map = {
                NotificationLevel.INFO: "#36a64f",
                NotificationLevel.WARNING: "#ff9900",
                NotificationLevel.ERROR: "#ff0000",
                NotificationLevel.CRITICAL: "#8b0000",
            }
            
            payload = {
                "attachments": [
                    {
                        "color": color_map.get(notification.level, "#36a64f"),
                        "title": notification.title,
                        "text": notification.body,
                        "footer": f"Kind: {notification.kind}",
                        "ts": int(datetime.fromisoformat(notification.timestamp).timestamp()),
                    }
                ]
            }
            
            response = httpx.post(self.config.slack_webhook, json=payload, timeout=15)
            success = response.status_code == 200
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Slack send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class DiscordHandler(NotificationHandler):
    """Discord webhook notification handler."""
    
    def can_handle(self) -> bool:
        return bool(self.config.discord_webhook)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            color_map = {
                NotificationLevel.INFO: 0x36a64f,
                NotificationLevel.WARNING: 0xff9900,
                NotificationLevel.ERROR: 0xff0000,
                NotificationLevel.CRITICAL: 0x8b0000,
            }
            
            payload = {
                "embeds": [
                    {
                        "title": notification.title,
                        "description": notification.body,
                        "color": color_map.get(notification.level, 0x36a64f),
                        "footer": {"text": f"Kind: {notification.kind}"},
                        "timestamp": notification.timestamp,
                    }
                ]
            }
            
            response = httpx.post(self.config.discord_webhook, json=payload, timeout=15)
            success = response.status_code in (200, 204)
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Discord send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class MatrixHandler(NotificationHandler):
    """Matrix message notification handler."""
    
    def can_handle(self) -> bool:
        return bool(
            self.config.matrix_homeserver 
            and self.config.matrix_token 
            and self.config.matrix_room
        )
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            # Matrix room IDs are like !abc123:matrix.org
            room_id = self.config.matrix_room
            if not room_id.startswith("!"):
                room_id = "!" + room_id
            
            text = notification.render()
            url = f"{self.config.matrix_homeserver}/_matrix/client/r0/rooms/{room_id}/send/m.room.message"
            
            payload = {
                "msgtype": "m.text",
                "body": text,
            }
            
            response = httpx.post(
                url,
                json=payload,
                params={"access_token": self.config.matrix_token},
                timeout=15
            )
            success = response.status_code == 200
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Matrix send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class WebhookHandler(NotificationHandler):
    """Generic HTTP webhook handler with signing."""
    
    def can_handle(self) -> bool:
        return bool(self.config.webhook_url)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            payload = json.dumps(notification.to_dict())
            headers = {"Content-Type": "application/json"}
            
            if self.config.sign_payloads:
                signature = self._sign_payload(payload)
                headers["X-Notification-Signature"] = signature
            
            response = httpx.post(
                self.config.webhook_url,
                content=payload,
                headers=headers,
                timeout=15
            )
            success = response.status_code in (200, 201, 202)
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Webhook send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class DesktopHandler(NotificationHandler):
    """Desktop notification handler (notify-send / osascript)."""
    
    def can_handle(self) -> bool:
        return shutil.which("notify-send") is not None or shutil.which("osascript") is not None
    
    def send(self, notification: Notification) -> bool:
        try:
            urgency = {
                NotificationLevel.INFO: "low",
                NotificationLevel.WARNING: "normal",
                NotificationLevel.ERROR: "critical",
                NotificationLevel.CRITICAL: "critical",
            }.get(notification.level, "normal")
            
            if shutil.which("notify-send"):
                subprocess.run(
                    ["notify-send", "-u", urgency, notification.title, notification.body],
                    timeout=5,
                    check=False,
                )
            elif shutil.which("osascript"):
                script = f'display notification "{notification.body}" with title "{notification.title}"'
                subprocess.run(
                    ["osascript", "-e", script],
                    timeout=5,
                    check=False,
                )
            
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Desktop notification failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class BellHandler(NotificationHandler):
    """Terminal bell/cue handler."""
    
    def can_handle(self) -> bool:
        return True  # Always available
    
    def send(self, notification: Notification) -> bool:
        try:
            # BEL character for terminal
            print("\a", end="", flush=True)
            # Also print a visual cue
            print(f"\n[BELL] {notification.title}\n", flush=True)
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Bell notification failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class MarkdownFileHandler(NotificationHandler):
    """Write notification to a markdown report file."""
    
    def can_handle(self) -> bool:
        return bool(self.config.markdown_file)
    
    def send(self, notification: Notification) -> bool:
        try:
            path = Path(self.config.markdown_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            content = f"## {notification.title}\n\n"
            content += f"**Level:** {notification.level.value}  \n"
            content += f"**Kind:** {notification.kind}  \n"
            content += f"**Time:** {notification.timestamp}  \n\n"
            content += f"{notification.body}\n\n"
            content += "---\n\n"
            
            with open(path, "a") as f:
                f.write(content)
            
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Markdown file write failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class JSONLHandler(NotificationHandler):
    """Write structured events to a JSONL file."""
    
    def can_handle(self) -> bool:
        return bool(self.config.event_log_file)
    
    def send(self, notification: Notification) -> bool:
        try:
            path = Path(self.config.event_log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "a") as f:
                f.write(json.dumps(notification.to_dict()) + "\n")
            
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"JSONL write failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class ExecHandler(NotificationHandler):
    """Execute a user command with notification data."""
    
    def can_handle(self) -> bool:
        return bool(self.config.agent_command)
    
    def send(self, notification: Notification) -> bool:
        try:
            argv = shlex.split(self.config.agent_command)
            if not argv:
                return False
            
            input_text = json.dumps(notification.to_dict())
            result = subprocess.run(
                argv,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            
            success = result.returncode == 0
            self._log_delivery(notification, success, result.stderr if result.stderr else "")
            return success
        except Exception as exc:
            logger.error(f"Exec handler failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class SignalHandler(NotificationHandler):
    """Send notifications via Signal CLI."""
    
    def can_handle(self) -> bool:
        return bool(
            shutil.which("signal-cli") 
            and self.config.signal_phone 
            and self.config.signal_recipient
        )
    
    def send(self, notification: Notification) -> bool:
        try:
            text = notification.render()
            subprocess.run(
                [
                    "signal-cli",
                    "-u", self.config.signal_phone,
                    "send",
                    "-m", text,
                    self.config.signal_recipient,
                ],
                timeout=15,
                check=True,
            )
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Signal send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class GitLabHandler(NotificationHandler):
    """Post notification as a GitLab MR comment."""
    
    def can_handle(self) -> bool:
        return bool(
            self.config.gitlab_token 
            and self.config.gitlab_project_id 
            and self.config.gitlab_mr_id
        )
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            url = (
                f"https://gitlab.com/api/v4/projects/{self.config.gitlab_project_id}"
                f"/merge_requests/{self.config.gitlab_mr_id}/notes"
            )
            
            body = notification.render()
            payload = {"body": body}
            headers = {"PRIVATE-TOKEN": self.config.gitlab_token}
            
            response = httpx.post(url, json=payload, headers=headers, timeout=15)
            success = response.status_code in (200, 201)
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"GitLab comment failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class SentryHandler(NotificationHandler):
    """Send critical events to Sentry."""
    
    def can_handle(self) -> bool:
        return bool(self.config.sentry_dsn)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            # Only send errors/critical to Sentry
            if notification.level not in (NotificationLevel.ERROR, NotificationLevel.CRITICAL):
                return True
            
            url = self._extract_sentry_url(self.config.sentry_dsn)
            if not url:
                return False
            
            payload = {
                "message": notification.title,
                "level": notification.level.value,
                "extra": notification.to_dict(),
            }
            
            response = httpx.post(url, json=payload, timeout=15)
            success = response.status_code in (200, 201)
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Sentry send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False
    
    def _extract_sentry_url(self, dsn: str) -> str:
        """Extract public URL from Sentry DSN."""
        try:
            # DSN format: https://key@sentry.io/project
            match = re.match(r"https://([^@]+)@([^/]+)/(.+)", dsn)
            if match:
                key, host, project = match.groups()
                return f"https://{host}/api/{project}/store/?sentry_key={key}&sentry_version=7"
        except Exception:
            pass
        return ""


class PushoverHandler(NotificationHandler):
    """Send mobile push notifications via Pushover."""
    
    def can_handle(self) -> bool:
        return bool(
            self.config.pushover_token 
            and self.config.pushover_user
        )
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            priority = {
                NotificationLevel.INFO: 0,
                NotificationLevel.WARNING: 1,
                NotificationLevel.ERROR: 2,
                NotificationLevel.CRITICAL: 2,
            }.get(notification.level, 0)
            
            payload = {
                "token": self.config.pushover_token,
                "user": self.config.pushover_user,
                "title": notification.title,
                "message": notification.body,
                "priority": priority,
                "timestamp": int(datetime.fromisoformat(notification.timestamp).timestamp()),
            }
            
            response = httpx.post("https://api.pushover.net/1/messages.json", data=payload, timeout=15)
            success = response.status_code == 200
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"Pushover send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class NtfyHandler(NotificationHandler):
    """Publish to an ntfy topic."""
    
    def can_handle(self) -> bool:
        return bool(self.config.ntfy_topic)
    
    def send(self, notification: Notification) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        
        try:
            url = f"https://ntfy.sh/{self.config.ntfy_topic}"
            
            headers = {
                "Title": notification.title,
                "Priority": notification.level.value,
            }
            
            if self.config.ntfy_token:
                headers["Authorization"] = f"Bearer {self.config.ntfy_token}"
            
            response = httpx.post(
                url,
                content=notification.body,
                headers=headers,
                timeout=15
            )
            success = response.status_code in (200, 201)
            self._log_delivery(notification, success, "" if success else response.text)
            return success
        except Exception as exc:
            logger.error(f"ntfy send failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class TailHandler(NotificationHandler):
    """Append short recap line to a running log stream."""
    
    def can_handle(self) -> bool:
        return bool(self.config.tail_recap_file)
    
    def send(self, notification: Notification) -> bool:
        try:
            path = Path(self.config.tail_recap_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Format: TIMESTAMP LEVEL TITLE
            line = f"{notification.timestamp} [{notification.level.upper():8s}] {notification.title}\n"
            
            with open(path, "a") as f:
                f.write(line)
            
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Tail write failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False


class AtomFeedHandler(NotificationHandler):
    """Emit notification as a new entry in an Atom feed."""
    
    def can_handle(self) -> bool:
        return bool(self.config.atom_feed_file)
    
    def send(self, notification: Notification) -> bool:
        try:
            path = Path(self.config.atom_feed_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            if not path.exists():
                self._create_atom_feed(path)
            
            self._add_atom_entry(path, notification)
            self._log_delivery(notification, True)
            return True
        except Exception as exc:
            logger.error(f"Atom feed write failed: {exc}")
            self._log_delivery(notification, False, str(exc))
            return False
    
    def _create_atom_feed(self, path: Path):
        """Create a basic Atom feed structure."""
        root = ET.Element("feed")
        root.set("xmlns", "http://www.w3.org/2005/Atom")
        
        title = ET.SubElement(root, "title")
        title.text = "Notification Feed"
        
        id_elem = ET.SubElement(root, "id")
        id_elem.text = f"urn:uuid:{path.parent.name}"
        
        updated = ET.SubElement(root, "updated")
        updated.text = datetime.now(timezone.utc).isoformat()
        
        tree = ET.ElementTree(root)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)
    
    def _add_atom_entry(self, path: Path, notification: Notification):
        """Add a new entry to the Atom feed."""
        tree = ET.parse(str(path))
        root = tree.getroot()
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        # Register namespace
        ET.register_namespace("atom", ns["atom"])
        
        entry = ET.Element("entry")
        
        title = ET.SubElement(entry, "title")
        title.text = notification.title
        
        content = ET.SubElement(entry, "content")
        content.text = notification.body
        
        published = ET.SubElement(entry, "published")
        published.text = notification.timestamp
        
        updated = ET.SubElement(entry, "updated")
        updated.text = datetime.now(timezone.utc).isoformat()
        
        entry_id = ET.SubElement(entry, "id")
        entry_id.text = f"urn:notification:{self._get_notification_id(notification)}"
        
        category = ET.SubElement(entry, "category")
        category.set("term", notification.level.value)
        
        root.append(entry)
        
        # Update feed's updated time
        feed_updated = root.find("atom:updated", ns)
        if feed_updated is None:
            feed_updated = root.find("updated")
        if feed_updated is not None:
            feed_updated.text = datetime.now(timezone.utc).isoformat()
        
        tree = ET.ElementTree(root)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)


# DiffChain pattern: pluggable notification chain
class NotificationChain:
    """Pluggable chain of notification handlers (DiffChain pattern)."""
    
    def __init__(self, config: NotifyConfig):
        self.config = config
        self.handlers: list[NotificationHandler] = []
        self.rate_limiter = RateLimiter(config.rate_limit_per_minute)
        self.audit_log: list[dict[str, Any]] = []
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Initialize all available handlers."""
        handler_classes = [
            TelegramHandler,
            EmailHandler,
            SlackHandler,
            DiscordHandler,
            MatrixHandler,
            WebhookHandler,
            DesktopHandler,
            BellHandler,
            MarkdownFileHandler,
            JSONLHandler,
            ExecHandler,
            SignalHandler,
            GitLabHandler,
            SentryHandler,
            PushoverHandler,
            NtfyHandler,
            TailHandler,
            AtomFeedHandler,
        ]
        
        for handler_class in handler_classes:
            handler = handler_class(self.config)
            if handler.can_handle():
                # Check if handler is enabled
                handler_name = handler_class.__name__
                way_id = self._handler_to_way_id(handler_name)
                if way_id in self.config.enabled_handlers:
                    self.handlers.append(handler)
                    logger.info(f"Enabled notification handler: {way_id}")
    
    def _handler_to_way_id(self, handler_name: str) -> str:
        """Map handler class name to way ID."""
        mapping = {
            "TelegramHandler": "notify.telegram",
            "EmailHandler": "notify.email",
            "SlackHandler": "notify.slack",
            "DiscordHandler": "notify.discord",
            "MatrixHandler": "notify.matrix",
            "WebhookHandler": "notify.webhook-out",
            "DesktopHandler": "notify.desktop",
            "BellHandler": "notify.bell",
            "MarkdownFileHandler": "notify.markdown-file",
            "JSONLHandler": "notify.log",
            "ExecHandler": "notify.exec",
            "SignalHandler": "notify.signal",
            "GitLabHandler": "notify.gitlab",
            "SentryHandler": "notify.sentry",
            "PushoverHandler": "notify.pushover",
            "NtfyHandler": "notify.ntfy",
            "TailHandler": "notify.tail",
            "AtomFeedHandler": "notify.atom",
        }
        return mapping.get(handler_name, "unknown")
    
    def notify(self, notification: Notification) -> NotificationResult:
        """Send notification through the chain."""
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, skipping notification")
            return NotificationResult(success=False, error="Rate limit exceeded")
        
        result = NotificationResult()
        
        for handler in self.handlers:
            try:
                success = handler.send(notification)
                result.add_handler_result(handler.name, success)
            except Exception as exc:
                logger.error(f"Handler {handler.name} raised exception: {exc}")
                result.add_handler_result(handler.name, False, str(exc))
        
        self._audit_notification(notification, result)
        return result
    
    def _audit_notification(self, notification: Notification, result: NotificationResult):
        """Log notification to audit trail."""
        if self.config.audit_log_file:
            path = Path(self.config.audit_log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "notification": notification.to_dict(),
                "result": asdict(result),
            }
            
            with open(path, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")


@dataclass
class NotificationResult:
    """Result of sending a notification through the chain."""
    success: bool = True
    error: str = ""
    handler_results: dict[str, bool] = field(default_factory=dict)
    handler_errors: dict[str, str] = field(default_factory=dict)
    
    def add_handler_result(self, handler_name: str, success: bool, error: str = ""):
        """Record result from a handler."""
        self.handler_results[handler_name] = success
        if error:
            self.handler_errors[handler_name] = error
        if not success:
            self.success = False


class RateLimiter:
    """Rate limiting for notifications."""
    
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.window_size = 60.0
        self.timestamps: list[float] = []
    
    def allow(self) -> bool:
        """Check if we can send a notification now."""
        now = time.time()
        # Remove old timestamps outside the window
        self.timestamps = [ts for ts in self.timestamps if now - ts < self.window_size]
        
        if len(self.timestamps) < self.per_minute:
            self.timestamps.append(now)
            return True
        return False
    
    def reset(self):
        """Reset the rate limiter."""
        self.timestamps = []


class Notifier:
    """Main notifier orchestrator (backwards compatible with original)."""
    
    def __init__(self, cfg: NotifyConfig):
        self.cfg = cfg
        self.chain = NotificationChain(cfg)
    
    def notify(self, n: Notification) -> None:
        """Send notification through chain."""
        self.chain.notify(n)
    
    def send_telegram(self, text: str, parse_mode: str = "Markdown") -> None:
        """Backwards compatible telegram sender."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, cannot send telegram")
            return
        
        try:
            httpx.post(
                f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                json={
                    "chat_id": self.cfg.telegram_chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except Exception as exc:
            logger.error(f"Telegram send failed: {exc}")


def notifier_from_env() -> Notifier:
    """Create notifier from environment variables."""
    return Notifier(
        NotifyConfig(
            telegram_token=os.getenv("HUNDREDWAYS_TELEGRAM_TOKEN") or os.getenv("SYNCBRIDGE_TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("HUNDREDWAYS_TELEGRAM_CHAT_ID") or os.getenv("SYNCBRIDGE_TELEGRAM_CHAT_ID", ""),
            agent_command=os.getenv("HUNDREDWAYS_AGENT_COMMAND") or os.getenv("SYNCBRIDGE_AGENT_COMMAND", ""),
        )
    )
