# NOTIFY Category: 20 Comprehensive Notification Ways

## Overview

The NOTIFY category implements a pluggable, production-grade notification system with 20 distinct delivery strategies. Built on the DiffChain pattern, it provides:

- **20 notification handlers** covering all major channels
- **Credential security** with automatic redaction
- **Payload signing** for webhook verification
- **Rate limiting** to prevent notification floods
- **Retry logic** with configurable delays
- **Delivery guarantees** via audit logs
- **Graceful fallbacks** on service failures
- **Mock integrations** for testing (no real API calls in tests)

## The 20 Ways

### 1. **notify.telegram** - Telegram Bot
Send messages to Telegram via bot token and chat ID.
- **Configuration**: `telegram_token`, `telegram_chat_id`
- **Supports**: Text, markdown formatting, icons
- **Error handling**: Logs HTTP errors gracefully

### 2. **notify.email** - SMTP Digest
Send email notifications via SMTP server.
- **Configuration**: `smtp_host`, `smtp_user`, `smtp_password`, `smtp_to`
- **Supports**: Multipart MIME, JSON attachment
- **Error handling**: Graceful connection failure

### 3. **notify.slack** - Slack Webhook
Post rich messages to Slack channels.
- **Configuration**: `slack_webhook` (incoming webhook URL)
- **Supports**: Colored attachments, timestamps, footer
- **Error handling**: Validates HTTP 200 response

### 4. **notify.discord** - Discord Webhook
Post embeds to Discord channels.
- **Configuration**: `discord_webhook` (webhook URL)
- **Supports**: Embedded messages, colors, footers
- **Error handling**: Accepts 200 or 204 status codes

### 5. **notify.matrix** - Matrix Message
Send messages to Matrix homeserver rooms.
- **Configuration**: `matrix_homeserver`, `matrix_token`, `matrix_room`
- **Supports**: Text messages, room IDs
- **Error handling**: Validates token validity

### 6. **notify.webhook-out** - Generic Webhook
Send JSON to any HTTP endpoint with optional HMAC signing.
- **Configuration**: `webhook_url`, `webhook_secret`, `sign_payloads`
- **Supports**: HMAC-SHA256 signature in headers
- **Error handling**: Logs HTTP status codes

### 7. **notify.desktop** - Desktop Notifications
Use notify-send or osascript for native desktop alerts.
- **Configuration**: Auto-detects notify-send/osascript
- **Supports**: Urgency levels (low/normal/critical)
- **Error handling**: Falls back gracefully if tools missing

### 8. **notify.bell** - Terminal Bell/Cue
Visual and audible terminal bell with status line.
- **Configuration**: None required
- **Supports**: BEL character, status message
- **Error handling**: Always succeeds

### 9. **notify.markdown-file** - Markdown Report
Append structured reports to markdown file.
- **Configuration**: `markdown_file`
- **Supports**: Multi-section reports, levels
- **Error handling**: Creates parent directories

### 10. **notify.log** - JSONL Event Log
Stream structured events to JSONL file.
- **Configuration**: `event_log_file`
- **Supports**: Valid JSON per line, full notification data
- **Error handling**: Atomic line writes

### 11. **notify.exec** - User Command
Execute a shell command with notification as JSON input.
- **Configuration**: `agent_command`
- **Supports**: stdin/stdout, exit code checks
- **Error handling**: Logs stderr on failure

### 12. **notify.signal** - Signal CLI Sender
Send Signal messages via signal-cli daemon.
- **Configuration**: `signal_phone`, `signal_recipient`
- **Supports**: Text messages to phone numbers
- **Error handling**: Requires signal-cli on PATH

### 13. **notify.gitlab** - GitLab MR Comment
Post notification as comment on GitLab merge request.
- **Configuration**: `gitlab_token`, `gitlab_project_id`, `gitlab_mr_id`
- **Supports**: Markdown formatting
- **Error handling**: API rate limit aware

### 14. **notify.sentry** - Sentry Event
Send error/critical events to Sentry.
- **Configuration**: `sentry_dsn`
- **Supports**: Only ERROR and CRITICAL levels (INFO/WARN skipped)
- **Error handling**: Extracts URL from DSN safely

### 15. **notify.pushover** - Pushover Push
Mobile push notification via Pushover API.
- **Configuration**: `pushover_token`, `pushover_user`
- **Supports**: Priority levels, timestamps
- **Error handling**: Validates JSON response

### 16. **notify.ntfy** - ntfy Topic
Publish to public ntfy topic with optional token.
- **Configuration**: `ntfy_topic`, `ntfy_token` (optional)
- **Supports**: Title, priority headers
- **Error handling**: Works without token for public topics

### 17. **notify.tail** - Tail Recap
Append short recap line to running log stream.
- **Configuration**: `tail_recap_file`
- **Supports**: Compact format with timestamp, level, title
- **Error handling**: Creates parent directories

### 18. **notify.atom** - Atom Feed Publish
Emit notification as entry in local Atom feed.
- **Configuration**: `atom_feed_file`
- **Supports**: RFC 4287 Atom format, feed creation
- **Error handling**: Creates feed structure automatically

### 19. **notify.chat-hook** - Chat Webhook (Legacy)
Generic chat webhook handler for matrix/discord/slack.
- **Configuration**: Handler-specific webhook URLs
- **Supports**: Markdown, timestamps
- **Error handling**: Handler-specific validation

### 20. **notify.agent** - Agent Prompt Hook
Pipe notification to opencode agent as prompt.
- **Configuration**: `agent_command`
- **Supports**: Structured prompts, agent integration
- **Error handling**: CLI availability checks

## Architecture: DiffChain Pattern

The notification system uses the DiffChain pattern for composable, pluggable handlers:

```python
# Configuration
config = NotifyConfig(
    enabled_handlers={"notify.telegram", "notify.log", "notify.slack"},
    rate_limit_per_minute=10,
    max_retries=3,
)

# Chain initialization
chain = NotificationChain(config)

# Send notification through all enabled handlers
result = chain.notify(notification)
```

### Handler Base Class

All 20 handlers inherit from `NotificationHandler`:

```python
class NotificationHandler(ABC):
    def can_handle(self) -> bool:
        """Check if handler is properly configured."""
        
    def send(self, notification: Notification) -> bool:
        """Send notification, return True on success."""
```

### Notification Flow

1. **Rate Limiting**: Check per-minute quota
2. **Handler Selection**: Run only enabled, configured handlers
3. **Parallel Execution**: Each handler runs independently
4. **Failure Isolation**: One handler's failure doesn't block others
5. **Audit Logging**: Log all attempts to audit trail
6. **Result Aggregation**: Return composite success/failure

## Security Features

### 1. Credential Management
- Automatic redaction of sensitive keys in logs
- Environment variable support for all credentials
- No credential storage in code

```python
config = NotifyConfig(
    telegram_token=os.getenv("TELEGRAM_TOKEN"),
    smtp_password=os.getenv("SMTP_PASSWORD"),
)
```

### 2. Payload Signing
Webhook payloads can be cryptographically signed with HMAC-SHA256:

```python
config = NotifyConfig(
    webhook_url="https://example.com/webhook",
    webhook_secret="my-secret-key",
    sign_payloads=True,
)
# Payload receives X-Notification-Signature header
```

### 3. No Credential Leaks
- Credentials masked in delivery logs
- Exception messages don't expose secrets
- Sanitized audit trails

### 4. XSS Prevention
- Markdown escaping in handlers
- JSON encoding for structured data
- No HTML injection vectors

## Rate Limiting

Rate limit notifications per minute to prevent floods:

```python
config = NotifyConfig(rate_limit_per_minute=10)
chain = NotificationChain(config)

# First 10 notifications in a minute succeed
for i in range(10):
    chain.notify(notification)  # All succeed

# 11th notification is blocked
result = chain.notify(notification)  # result.success == False
```

## Error Handling

All handlers implement graceful fallback on service outages:

```python
# If Telegram API is down:
handler = TelegramHandler(config)
result = handler.send(notification)  # Returns False, logs error

# Chain continues to other handlers:
chain.notify(notification)  # Slack/email still sent
```

## Retry Logic

Configurable retry policy for transient failures:

```python
config = NotifyConfig(
    max_retries=3,
    retry_delay_seconds=1.0,
)
```

## Delivery Guarantees

Audit log tracks all delivery attempts:

```python
# Enable audit logging
config = NotifyConfig(audit_log_file="/var/log/notify-audit.jsonl")

# Each notification recorded with:
# - timestamp
# - handler results
# - success/failure per handler
# - error messages
```

Audit format:
```json
{
  "timestamp": "2026-09-23T08:34:04.123456+00:00",
  "notification": {
    "title": "Sync Complete",
    "body": "123 commits ported",
    "level": "info",
    "kind": "port",
    "timestamp": "2026-09-23T08:34:00+00:00"
  },
  "result": {
    "success": true,
    "handler_results": {
      "TelegramHandler": true,
      "SlackHandler": true
    }
  }
}
```

## Usage Examples

### Basic Setup

```python
from hundredways.notify import Notifier, NotifyConfig, Notification, NotificationLevel

config = NotifyConfig(
    telegram_token="your-token",
    telegram_chat_id="123456",
    slack_webhook="https://hooks.slack.com/...",
    enabled_handlers={"notify.telegram", "notify.slack"},
)

notifier = Notifier(config)

notification = Notification(
    title="Sync Complete",
    body="Successfully ported 42 commits",
    level=NotificationLevel.INFO,
    kind="port",
)

notifier.notify(notification)
```

### Full Configuration

```python
config = NotifyConfig(
    # Telegram
    telegram_token=os.getenv("TELEGRAM_TOKEN"),
    telegram_chat_id=os.getenv("TELEGRAM_CHAT"),
    
    # Email
    smtp_host="smtp.example.com",
    smtp_user="alerts@example.com",
    smtp_password=os.getenv("SMTP_PASSWORD"),
    smtp_to=["ops@example.com"],
    
    # Slack
    slack_webhook=os.getenv("SLACK_WEBHOOK"),
    
    # Discord
    discord_webhook=os.getenv("DISCORD_WEBHOOK"),
    
    # Webhooks
    webhook_url="https://example.com/api/notify",
    webhook_secret=os.getenv("WEBHOOK_SECRET"),
    sign_payloads=True,
    
    # File outputs
    markdown_file="/tmp/sync-report.md",
    event_log_file="/var/log/sync-events.jsonl",
    tail_recap_file="/var/log/sync-tail.log",
    audit_log_file="/var/log/notify-audit.jsonl",
    
    # Rate limiting
    rate_limit_per_minute=10,
    max_retries=3,
    retry_delay_seconds=1.0,
    
    enabled_handlers={
        "notify.telegram",
        "notify.slack",
        "notify.email",
        "notify.log",
        "notify.markdown-file",
    },
)

notifier = Notifier(config)
```

### From Environment Variables

```python
from hundredways.notify import notifier_from_env

# Uses HUNDREDWAYS_TELEGRAM_TOKEN, HUNDREDWAYS_TELEGRAM_CHAT_ID
notifier = notifier_from_env()
notifier.notify(notification)
```

### Error Levels

```python
# INFO level
info = Notification(
    "Sync started",
    "Beginning port cycle",
    level=NotificationLevel.INFO,
)

# WARNING level
warning = Notification(
    "Gap detected",
    "5 commits behind upstream",
    level=NotificationLevel.WARNING,
)

# ERROR level (sent to Sentry)
error = Notification(
    "Port failed",
    "git apply returned exit code 1",
    level=NotificationLevel.ERROR,
)

# CRITICAL level
critical = Notification(
    "System down",
    "Database unreachable",
    level=NotificationLevel.CRITICAL,
)
```

## Testing

All handlers include mock integrations for testing:

```python
import pytest
from unittest.mock import patch
from hundredways.notify import SlackHandler, NotifyConfig, Notification

def test_slack_notification():
    config = NotifyConfig(slack_webhook="https://hooks.slack.com/...")
    handler = SlackHandler(config)
    
    with patch("httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        
        notification = Notification("Test", "Body")
        assert handler.send(notification) is True
```

Run full test suite:
```bash
pytest tests/test_notify.py -v
```

## Production Deployment

### 1. Configure Handlers
Set environment variables for each handler:
```bash
export HUNDREDWAYS_TELEGRAM_TOKEN=xxx
export HUNDREDWAYS_SLACK_WEBHOOK=https://...
export SMTP_PASSWORD=xxx
```

### 2. Enable Handlers
```python
config = NotifyConfig(
    enabled_handlers={
        "notify.telegram",
        "notify.slack",
        "notify.email",
    }
)
```

### 3. Monitor Audit Log
```bash
tail -f /var/log/notify-audit.jsonl | jq .
```

### 4. Set Rate Limits
```python
config = NotifyConfig(
    rate_limit_per_minute=100,  # Adjust for your volume
    max_retries=5,
)
```

### 5. Verify Handler Coverage
```python
chain = NotificationChain(config)
print(f"Enabled handlers: {len(chain.handlers)}")
for h in chain.handlers:
    print(f"  - {h.name}")
```

## Performance

- **No blocking I/O**: All handlers are standalone
- **Independent failures**: One handler's timeout doesn't block others
- **Rate limiting**: Prevents notification storms
- **Memory efficient**: Streaming JSON to files
- **Audit trail**: Minimal overhead, appended atomically

## Migration Guide

### From Old notifier.py

The new system is backwards compatible:

```python
# Old code still works
from hundredways.notifier import Notifier, NotifyConfig, Notification
notifier = Notifier(config)
notifier.notify(notification)

# But you can also use new features
from hundredways.notify import NotificationChain
chain = NotificationChain(config)
result = chain.notify(notification)
print(f"Success: {result.success}")
```

## Troubleshooting

### Telegram Failing
1. Verify token is valid: `curl https://api.telegram.org/botXXX/getMe`
2. Check chat ID is correct
3. Ensure httpx is installed

### Email Not Sending
1. Verify SMTP credentials
2. Check firewall allows port 587
3. Review exception in delivery_log

### Rate Limited
Increase `rate_limit_per_minute` or implement queuing upstream:

```python
config = NotifyConfig(rate_limit_per_minute=100)
```

### Missing Mock in Tests
Ensure all HTTP calls are mocked:

```python
with patch("httpx.post") as mock_post:
    mock_post.return_value.status_code = 200
    handler.send(notification)
```

## Future Extensions

- **SMS via Twilio** (notify.sms)
- **Pagerduty** (notify.pagerduty)
- **Datadog** (notify.datadog)
- **Splunk** (notify.splunk)
- **Custom webhooks** with templating
- **Delivery receipts** (read confirmations)
- **Rate limiting by handler** (different limits per channel)
- **Batch notifications** (group multiple events)
- **Circuit breakers** (disable failing handlers temporarily)

## References

- DiffChain Pattern: Pluggable handler chains for extensibility
- RFC 4287: Atom Syndication Format
- HMAC: https://en.wikipedia.org/wiki/HMAC
- Python asyncio: For future async support
