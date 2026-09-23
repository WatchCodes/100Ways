# DETECT Quick Start Guide

## Installation

```bash
cd /root/100ways-work
pip install -e .
```

## 5-Minute Quick Start

### 1. Basic Polling

```python
from hundredways.detect import BasicPoller, DetectionConfig, DetectionLogger
import time

# Create config
config = DetectionConfig(
    repo="/path/to/your/repo",
    poll_interval=60,
)

# Create logger
logger = DetectionLogger("detector")

# Create poller
poller = BasicPoller(config, logger)

# Poll for changes
while True:
    events = poller.detect()
    for event in events:
        print(f"📢 Change detected: {event.kind} on {event.branch}")
    time.sleep(config.poll_interval)
```

### 2. GitHub Webhooks (Real-Time)

```python
from hundredways.detect import WebhookStrategy, DetectionConfig, DetectionLogger
import os

config = DetectionConfig(
    repo="/path/to/your/repo",
    webhook_port=5000,
    webhook_token=os.getenv("GITHUB_WEBHOOK_SECRET"),
)

logger = DetectionLogger("webhook")
webhook = WebhookStrategy(config, logger)

# Start server (in separate thread/process)
webhook.start_server()

# Handle incoming webhooks
from flask import Flask, request

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("X-Hub-Signature-256")
    
    if webhook.receive_webhook(payload, signature):
        events = webhook.detect()
        for event in events:
            print(f"🎉 Webhook event: {event.kind}")
        return {"status": "ok"}, 200
    return {"error": "Invalid signature"}, 401

if __name__ == "__main__":
    app.run(port=5000)
```

### 3. GitHub API Polling

```python
from hundredways.detect import GitHubAPIPoller, DetectionConfig, DetectionLogger
import os

config = DetectionConfig(
    repo="/path/to/your/repo",
    github_token=os.getenv("GITHUB_TOKEN"),
)

logger = DetectionLogger("github_api")
poller = GitHubAPIPoller(config, logger)

events = poller.detect()
for event in events:
    print(f"🔗 GitHub change: {event.kind}")
```

### 4. Combine Multiple Strategies (DiffChain)

```python
from hundredways.detect import (
    DiffChain, WebhookStrategy, BasicPoller, GitHubAPIPoller,
    DetectionConfig, DetectionLogger
)
import os

config = DetectionConfig(
    repo="/path/to/your/repo",
    webhook_port=5000,
    webhook_token=os.getenv("GITHUB_WEBHOOK_SECRET"),
    github_token=os.getenv("GITHUB_TOKEN"),
)

logger = DetectionLogger("diffchain")

# Create chain
chain = DiffChain(config, logger)

# Add strategies with priorities (lower = higher priority)
chain.add_strategy(WebhookStrategy(config, logger), priority=0)  # Real-time
chain.add_strategy(BasicPoller(config, logger), priority=1)      # Polling fallback
chain.add_strategy(GitHubAPIPoller(config, logger), priority=2)  # API backup

# Run chain
events = chain.run()

# All events are deduplicated and in priority order
for event in events:
    print(f"✅ Detected: {event.kind}")

# Get stats
stats = chain.get_stats()
print(f"Total events: {stats['total_events']}")
print(f"Avg latency: {stats['avg_latency_ms']}ms")
```

## Common Patterns

### Pattern 1: Rate-Limited Polling

```python
from hundredways.detect import RateLimitedPoller, DetectionConfig, DetectionLogger

config = DetectionConfig(
    repo="/path/to/your/repo",
    rate_limit_per_hour=100,
)

logger = DetectionLogger("ratelimit")
poller = RateLimitedPoller(config, logger)

# Automatically enforces rate limits
events = poller.detect()
```

### Pattern 2: Cron Scheduling

```python
from hundredways.detect import CronDetector, DetectionConfig, DetectionLogger

config = DetectionConfig(
    repo="/path/to/your/repo",
    cron_schedule="0 * * * *",  # Every hour
)

logger = DetectionLogger("cron")
detector = CronDetector(config, logger)

events = detector.detect()
```

### Pattern 3: File System Monitoring

```python
from hundredways.detect import FileSystemWatcher, DetectionConfig, DetectionLogger

config = DetectionConfig(
    repo="/path/to/your/repo",
    watch_patterns=["*.md", "src/**/*.py"],
)

logger = DetectionLogger("watch")
watcher = FileSystemWatcher(config, logger)

events = watcher.detect()
```

### Pattern 4: Adaptive Polling

```python
from hundredways.detect import AdaptivePoller, DetectionConfig, DetectionLogger
import time

config = DetectionConfig(
    repo="/path/to/your/repo",
    poll_interval=60,
)

logger = DetectionLogger("adaptive")
poller = AdaptivePoller(config, logger)

# Automatically adjusts interval based on change frequency
while True:
    events = poller.detect()
    interval = poller.get_current_interval()
    print(f"Current interval: {interval}s")
    time.sleep(interval)
```

## Environment Setup

### GitHub Token

```bash
# Create a Personal Access Token
# Go to: https://github.com/settings/tokens
# Copy and set environment variable:
export GITHUB_TOKEN=ghp_...
```

### Webhook Secret

```bash
# Generate a random secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set in GitHub webhook settings
# Copy and set environment variable:
export GITHUB_WEBHOOK_SECRET=...
```

## Error Handling

```python
from hundredways.detect import (
    DetectionError, RateLimitError, NetworkError,
    BasicPoller, DetectionConfig, DetectionLogger
)

config = DetectionConfig(repo="/path/to/your/repo")
logger = DetectionLogger("error_handling")
poller = BasicPoller(config, logger)

try:
    events = poller.detect()
except RateLimitError:
    print("Rate limited, will retry later")
except NetworkError:
    print("Network error, retrying with backoff")
except DetectionError as e:
    print(f"Detection failed: {e}")
```

## Logging

```python
from hundredways.detect import DetectionLogger

# Create logger
logger = DetectionLogger("myapp", level="DEBUG")

# Use logger
logger.debug("Debug info")
logger.info("Important info")
logger.warning("Warning message")
logger.error("Error message")
```

## Testing Your Setup

```bash
# Run all detection tests
pytest tests/test_detect.py -v

# Run specific strategy tests
pytest tests/test_detect.py::TestPollingStrategy -v

# Run with coverage
pytest tests/test_detect.py --cov=hundredways.detect

# Run performance benchmarks
pytest tests/test_detect.py::TestPerformanceBenchmarks -v
```

## Next Steps

- Read [DETECT.md](DETECT.md) for comprehensive documentation
- Explore all 20 detection strategies
- Combine strategies with DiffChain
- Set up webhooks for real-time detection
- Monitor logs for issues
- Optimize based on performance benchmarks

## Troubleshooting

### "Cannot find repository"

```python
# Make sure repo path exists and is a Git repository
config = DetectionConfig(repo="/path/to/your/repo")
# Verify: ls -la /path/to/your/repo/.git
```

### "Invalid GitHub token"

```python
# Check token is set correctly
import os
print(os.getenv("GITHUB_TOKEN"))
# Regenerate from: https://github.com/settings/tokens
```

### "Webhook not triggering"

1. Ensure port is open: `netstat -an | grep 5000`
2. Check webhook is configured in GitHub: Settings → Webhooks
3. Verify signature token matches: `GITHUB_WEBHOOK_SECRET`
4. Look at logs for signature validation errors

### "Rate limit exceeded"

```python
# Use GitHub token for higher limits
config = DetectionConfig(
    repo="/path/to/your/repo",
    github_token=os.getenv("GITHUB_TOKEN"),
)

# Or use RateLimitedPoller
from hundredways.detect import RateLimitedPoller
poller = RateLimitedPoller(config, logger)
```

## Support

For issues or questions:
1. Check logs: Look for DEBUG level messages
2. Run tests: `pytest tests/test_detect.py -v`
3. Review examples: See [DETECT.md](DETECT.md)
4. Check configuration: Validate with `dry_run=True`
