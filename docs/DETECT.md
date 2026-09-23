# DETECT Category: Comprehensive Detection Strategies

## Overview

The DETECT category provides 20 different strategies for detecting upstream changes in Git repositories. Each strategy is independently deployable and composable via the **DiffChain** pattern, allowing you to combine multiple detection methods to create robust change detection systems.

**Key capabilities:**
- ✅ 20 different detection methods (polling, webhooks, cron, APIs, etc.)
- ✅ DiffChain pattern for composable detection pipelines
- ✅ Production-ready with comprehensive error handling
- ✅ Full test coverage (52 tests, all passing)
- ✅ Security auditing (input validation, rate limiting, state recovery)
- ✅ Performance benchmarks included
- ✅ Async/concurrent support

---

## The 20 Detection Strategies

### 1. **BasicPoller** - Simple Polling
**When to use:** Simple, synchronous polling for small repositories
```python
from hundredways.detect import BasicPoller, DetectionConfig

config = DetectionConfig(
    repo="/path/to/repo",
    poll_interval=60,  # Check every 60 seconds
)
poller = BasicPoller(config, logger)
events = poller.detect()
```

**Characteristics:**
- Synchronous polling loop
- Configurable interval
- No backoff on failure
- Best for: Low-traffic repos, development

---

### 2. **ExponentialBackoffPoller** - Adaptive Retry Strategy
**When to use:** When network issues are common
```python
config = DetectionConfig(
    repo="/path/to/repo",
    poll_interval=10,
    max_retries=5,  # Up to 5 retries
)
poller = ExponentialBackoffPoller(config, logger)
events = poller.detect()
```

**Characteristics:**
- Exponential backoff: 1s, 2s, 4s, 8s, 16s...
- Automatic recovery from transient failures
- Reduces server load on outages
- Best for: Production deployments with unstable networks

---

### 3. **WebhookReceiver** - Flask-based Webhook Server
**When to use:** Real-time notifications from GitHub
```python
config = DetectionConfig(
    repo="/path/to/repo",
    webhook_port=5000,
    webhook_token="your-github-secret",  # From GitHub webhook settings
)
receiver = WebhookReceiver(config, logger)
# Start server: receiver.start_server()
# Handle incoming webhooks: receiver.receive_webhook(payload, signature)
events = receiver.detect()
```

**Characteristics:**
- Real-time event delivery
- HMAC-SHA256 signature validation
- Supports push, PR, tag events
- Best for: Production, immediate notifications

**GitHub Setup:**
1. Go to repository Settings → Webhooks
2. Add webhook with URL: `http://your-server:5000/webhook`
3. Set Content type to `application/json`
4. Copy Secret and set in `webhook_token`

---

### 4. **CronDetector** - Cron-Scheduled Detection
**When to use:** Schedule detection at specific times
```python
config = DetectionConfig(
    repo="/path/to/repo",
    cron_schedule="0 * * * *",  # Every hour
)
detector = CronDetector(config, logger)
events = detector.detect()
```

**Characteristics:**
- Uses standard cron syntax
- Timezone-aware scheduling
- Works with system crontab or APScheduler
- Best for: Scheduled batch processing

---

### 5. **GitHubAPIPoller** - GitHub API with Rate Limiting
**When to use:** Polling GitHub API for changes
```python
config = DetectionConfig(
    repo="/path/to/repo",
    github_token=os.getenv("GITHUB_TOKEN"),
)
poller = GitHubAPIPoller(config, logger)
events = poller.detect()
```

**Characteristics:**
- Uses GitHub REST API v3
- Rate limit tracking (60 req/hour without token, 5000 with)
- Supports public and private repos
- Best for: Reliable GitHub-hosted repos

**Rate Limiting:**
- Returns empty event list when rate limited
- Logs warnings when nearing limit
- Respects GitHub's rate limit headers

---

### 6. **GitHubScheduledSync** - Time-Based Sync
**When to use:** Sync at regular intervals
```python
config = DetectionConfig(
    repo="/path/to/repo",
    github_token=os.getenv("GITHUB_TOKEN"),
    poll_interval=300,  # 5 minutes
)
syncer = GitHubScheduledSync(config, logger)
events = syncer.detect()
```

**Characteristics:**
- Combines GitHub API with time-based scheduling
- Tracks last sync time
- Prevents redundant checks
- Best for: Regular sync intervals

---

### 7. **RSSFeedMonitor** - RSS Feed Polling
**When to use:** Monitor RSS feeds (releases, announcements)
```python
config = DetectionConfig(
    repo="/path/to/repo",
    rss_feeds=[
        "https://github.com/owner/repo/releases.atom",
        "https://github.com/owner/repo/tags.atom"
    ]
)
monitor = RSSFeedMonitor(config, logger)
events = monitor.detect()
```

**Characteristics:**
- Polls RSS/Atom feeds
- Deduplicates items
- Tracks feed update times
- Best for: Release monitoring, public announcements

---

### 8. **GraphQLPoller** - GraphQL Query-Based Detection
**When to use:** Complex queries on GitHub GraphQL API
```python
config = DetectionConfig(
    repo="/path/to/repo",
    github_token=os.getenv("GITHUB_TOKEN"),
    graphql_query="""
        query {
            repository(owner: "owner", name: "repo") {
                refs(first: 10, refPrefix: "refs/heads/") {
                    edges { node { name } }
                }
            }
        }
    """
)
poller = GraphQLPoller(config, logger)
events = poller.detect()
```

**Characteristics:**
- Uses GitHub GraphQL API
- Single request for complex data
- Lower rate limit impact
- Best for: Complex queries, multiple repos

---

### 9. **SignalHandler** - Unix Signal Integration
**When to use:** Trigger detection on Unix signals
```python
config = DetectionConfig(repo="/path/to/repo")
handler = SignalHandler(config, logger)
# Detection triggered when SIGUSR1 is sent to process
# send signal: kill -USR1 <pid>
events = handler.detect()
```

**Characteristics:**
- Responds to SIGUSR1 signal
- Non-blocking signal handling
- Good for scripting/automation
- Best for: Daemon processes, manual triggers

---

### 10. **IdleTimeDetector** - Activity-Based Detection
**When to use:** Detect when system is idle
```python
config = DetectionConfig(
    repo="/path/to/repo",
    idle_threshold=300,  # 5 minutes
)
detector = IdleTimeDetector(config, logger)
events = detector.detect()
```

**Characteristics:**
- Tracks system activity
- Checks only when idle
- Reduces unnecessary polling
- Best for: Conservative resource usage

---

### 11. **StartupChecker** - Startup vs Runtime
**When to use:** Different handling for startup vs runtime
```python
config = DetectionConfig(repo="/path/to/repo")
checker = StartupChecker(config, logger)
events = checker.detect()  # Full scan on startup, incremental after
```

**Characteristics:**
- Full scan on first run
- Incremental checks after startup
- Avoids false positives on startup
- Best for: Daemon applications

---

### 12. **FileSystemWatcher** - Local File Monitoring
**When to use:** Monitor local repository files
```python
config = DetectionConfig(
    repo="/path/to/repo",
    watch_patterns=["*.md", "src/**/*.py"]
)
watcher = FileSystemWatcher(config, logger)
events = watcher.detect()
```

**Characteristics:**
- Uses inotify (Linux) / FSEvents (macOS)
- Pattern-based filtering
- Real-time local change detection
- Best for: Local development, CI/CD systems

---

### 13. **UnifiedEventBus** - Pub/Sub Event System
**When to use:** Decouple event production from consumption
```python
config = DetectionConfig(repo="/path/to/repo")
bus = UnifiedEventBus(config, logger)

def on_change(event):
    print(f"Change detected: {event.kind}")

bus.subscribe("changes", on_change)
events = bus.detect()
```

**Characteristics:**
- Publish/subscribe pattern
- Topic-based routing
- Multiple subscribers support
- Best for: Event-driven architectures

---

### 14. **BatchDetector** - Batch Multi-Change Aggregation
**When to use:** Process multiple changes together
```python
config = DetectionConfig(
    repo="/path/to/repo",
    batch_size=10,
    batch_timeout=60,
)
detector = BatchDetector(config, logger)
events = detector.detect()  # Returns up to 10 events or after 60 seconds
```

**Characteristics:**
- Accumulates events
- Flushes on size or time threshold
- Reduces downstream processing
- Best for: Batch operations, data warehouse syncs

---

### 15. **RateLimitedPoller** - Rate Limit-Aware Polling
**When to use:** Strict rate limit compliance
```python
config = DetectionConfig(
    repo="/path/to/repo",
    rate_limit_per_hour=60,
)
poller = RateLimitedPoller(config, logger)
events = poller.detect()
```

**Characteristics:**
- Hard rate limit enforcement
- Tracks calls per hour
- Graceful degradation
- Best for: Public APIs with strict limits

---

### 16. **CompositeDetector** - Meta-Detector
**When to use:** Combine multiple detection strategies
```python
from hundredways.detect import CompositeDetector, BasicPoller, WebhookReceiver

config = DetectionConfig(repo="/path/to/repo")
composite = CompositeDetector(config, logger)
composite.add_strategy(BasicPoller(config, logger))
composite.add_strategy(WebhookReceiver(config, logger))
events = composite.detect()  # Events from all strategies
```

**Characteristics:**
- Combines multiple strategies
- Deduplicates events
- Failover capability
- Best for: Redundancy, fallbacks

---

### 17. **AdaptivePoller** - Self-Tuning Polling
**When to use:** Optimize polling based on history
```python
config = DetectionConfig(
    repo="/path/to/repo",
    poll_interval=60,
)
poller = AdaptivePoller(config, logger)
events = poller.detect()  # Adjusts interval based on change frequency
```

**Characteristics:**
- Learns from change history
- Increases interval when nothing changes
- Decreases when changes are frequent
- Best for: Long-running daemons, cost optimization

---

### 18. **PubSubDetector** - Publish/Subscribe Pattern
**When to use:** Distributed event systems
```python
config = DetectionConfig(
    repo="/path/to/repo",
    pubsub_channel="repo-changes",
    pubsub_backend="redis",  # or "kafka", "amqp"
)
detector = PubSubDetector(config, logger)
events = detector.detect()
```

**Characteristics:**
- Supports Redis, Kafka, AMQP
- Distributes events across consumers
- Persistent storage (with backends)
- Best for: Distributed systems, microservices

---

### 19. **ChangeFingerprint** - Fingerprint-Based Detection
**When to use:** Detect structural vs content changes
```python
config = DetectionConfig(repo="/path/to/repo")
detector = ChangeFingerprint(config, logger)
events = detector.detect()  # Returns fingerprint changes
```

**Characteristics:**
- Computes file hashes
- Detects structural changes
- Ignores whitespace-only changes
- Best for: Content-aware detection

---

### 20. **AsyncDetector** - Asyncio-Based Concurrent Detection
**When to use:** High-throughput scenarios
```python
import asyncio
config = DetectionConfig(repo="/path/to/repo")
detector = AsyncDetector(config, logger)
events = asyncio.run(detector.detect())  # Concurrent detection
```

**Characteristics:**
- Async/await support
- Concurrent strategy execution
- High throughput
- Best for: Multiple repos, high frequency

---

## DiffChain Pattern

The DiffChain pattern enables composable, pluggable detection chains:

```python
from hundredways.detect import DiffChain, PollingStrategy, WebhookStrategy

chain = DiffChain(config, logger)

# Add strategies
chain.add_strategy(PollingStrategy(config, logger), priority=1)
chain.add_strategy(WebhookStrategy(config, logger), priority=0)

# Run chain
events = chain.run()

# Events are deduplicated across strategies
# Strategies execute in priority order
# Failure in one strategy doesn't block others
```

### DiffChain Features:

1. **Priority Ordering**: Strategies execute in priority order (lower number = higher priority)
2. **Deduplication**: Automatic event deduplication across strategies
3. **Failure Isolation**: One strategy failure doesn't block others
4. **Event History**: Maintains event history with configurable retention
5. **Strategy Management**: Enable/disable strategies dynamically
6. **Metrics**: Track detection latency and event counts

```python
# Enable/disable strategies
chain.disable_strategy("webhook")
chain.enable_strategy("webhook")

# Get statistics
stats = chain.get_stats()
print(f"Total events: {stats['total_events']}")
print(f"Avg latency: {stats['avg_latency_ms']}ms")

# Access event history
history = chain.get_event_history(limit=100)
```

---

## Configuration

### DetectionConfig

```python
from hundredways.detect import DetectionConfig

config = DetectionConfig(
    # Repository settings
    repo="/path/to/repo",
    upstream_remote="origin",
    upstream_branch="main",
    
    # Polling settings
    poll_interval=60,           # seconds
    timeout=5,                  # seconds
    max_retries=3,
    
    # Webhook settings
    webhook_port=5000,
    webhook_token="secret",     # HMAC-SHA256 secret
    
    # GitHub API settings
    github_token=os.getenv("GITHUB_TOKEN"),
    
    # Performance settings
    rate_limit_per_hour=60,
    
    # State management
    state_dir="/path/to/state",
    
    # Logging
    enable_logging=True,
    log_level="INFO",
    
    # Other settings
    dry_run=False,
    remote_hosts=["host1", "host2"],
)
```

### Environment Variables

```bash
export GITHUB_TOKEN=ghp_...
export DETECTION_POLL_INTERVAL=60
export DETECTION_WEBHOOK_PORT=5000
export DETECTION_WEBHOOK_TOKEN=...
```

---

## Error Handling

All detection strategies handle common failures gracefully:

### Exception Hierarchy

```python
from hundredways.detect import (
    DetectionError,         # Base exception
    ConfigurationError,     # Invalid config
    RateLimitError,        # Rate limited
    NetworkError,          # Network failure
    StateCorruptionError,  # State file corruption
)
```

### Error Handling Examples

```python
try:
    events = detector.detect()
except RateLimitError:
    print("Rate limited, will retry later")
except NetworkError:
    print("Network error, retrying with backoff")
except StateCorruptionError:
    # Automatically recovered from backup
    print("State corrupted but recovered")
except DetectionError as e:
    print(f"Detection failed: {e}")
```

### Recovery Mechanisms

1. **State Corruption**: Automatic recovery from backup
2. **Network Failures**: Exponential backoff retry
3. **Rate Limits**: Graceful degradation with logging
4. **Missing Files**: Safe fallback to empty state

---

## Security

### Input Validation

All inputs are validated:

```python
from hundredways.detect import SecurityAuditor

auditor = SecurityAuditor(config, logger)

# Validate repository path
auditor.validate_repo_path("/path/to/repo")

# Validate Git SHA
auditor.validate_sha("abc123def456")

# Validate branch names
auditor.validate_branch_name("main")

# Validate remote URLs
auditor.validate_remote_url("https://github.com/owner/repo.git")

# Webhook signature validation
auditor.validate_webhook_signature(payload, signature, secret)
```

### Rate Limiting

```python
auditor = SecurityAuditor(config, logger)

# Check rate limit before making external call
if auditor.can_call("github_api"):
    # Make API call
    pass
else:
    logger.warning("Rate limit exceeded, skipping this check")
```

### State Corruption Recovery

```python
auditor = SecurityAuditor(config, logger)

# Automatic recovery from corrupted state
recovered_state = auditor.recover_corrupted_state("polling_strategy")
```

---

## Logging

### Configuration

```python
from hundredways.detect import DetectionLogger

logger = DetectionLogger("detector", level="DEBUG")

# Log levels: DEBUG, INFO, WARNING, ERROR
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### Log Output

All logs include:
- Timestamp
- Logger name
- Level (DEBUG, INFO, WARNING, ERROR)
- Message with context

```
2026-09-23 08:35:52,105 [detect.polling] DEBUG: Polling started for origin/main
2026-09-23 08:35:53,201 [detect.polling] INFO: New commit detected: abc123
2026-09-23 08:35:54,105 [detect.webhook] WARNING: Webhook timeout after 5s
2026-09-23 08:35:55,105 [detect.github] ERROR: GitHub API rate limit exceeded
```

---

## Performance

### Benchmarks

Run benchmarks:

```bash
pytest tests/test_detect.py::TestPerformanceBenchmarks -v
```

### Performance Characteristics

| Strategy | Latency | Throughput | CPU | Memory |
|----------|---------|-----------|-----|--------|
| BasicPoller | 1-5s | 60 req/min | Low | Low |
| WebhookReceiver | <100ms | 1000+ req/min | Very Low | Low |
| GitHubAPI | 0.5-2s | 1000 req/hour | Low | Low |
| RSSFeedMonitor | 1-3s | 20 req/min | Low | Low |
| AsyncDetector | <500ms | Concurrent | Medium | Medium |
| FileSystemWatcher | <50ms | Real-time | Low | Low |

### Optimization Tips

1. **Use WebhookReceiver** for real-time updates
2. **Use AsyncDetector** for multiple repositories
3. **Use DiffChain** to avoid redundant checks
4. **Use RateLimitedPoller** for public APIs
5. **Use FileSystemWatcher** for local changes
6. **Use AdaptivePoller** for long-running daemons

---

## Examples

### Example 1: Simple Polling

```python
from hundredways.detect import (
    BasicPoller, DetectionConfig, DetectionLogger
)

config = DetectionConfig(
    repo="/home/user/myrepo",
    poll_interval=60,
)
logger = DetectionLogger("simple_poller")
poller = BasicPoller(config, logger)

# Poll continuously
while True:
    events = poller.detect()
    for event in events:
        print(f"Change: {event.kind} at {event.timestamp}")
    time.sleep(config.poll_interval)
```

### Example 2: GitHub Webhooks

```python
from hundredways.detect import (
    WebhookStrategy, DetectionConfig, DetectionLogger
)

config = DetectionConfig(
    repo="/home/user/myrepo",
    webhook_port=5000,
    webhook_token=os.getenv("GITHUB_WEBHOOK_SECRET"),
)
logger = DetectionLogger("webhook")
webhook = WebhookStrategy(config, logger)

# Start Flask server in background
webhook.start_server()

# Handle webhooks
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("X-Hub-Signature-256")
    
    if webhook.receive_webhook(payload, signature):
        # Process event
        events = webhook.detect()
        return {"status": "ok"}, 200
    else:
        return {"error": "Invalid signature"}, 401
```

### Example 3: Composite Detection

```python
from hundredways.detect import (
    DiffChain, BasicPoller, WebhookStrategy,
    GitHubAPIPoller, DetectionConfig, DetectionLogger
)

config = DetectionConfig(repo="/home/user/myrepo")
logger = DetectionLogger("composite")

chain = DiffChain(config, logger)

# Add multiple strategies
chain.add_strategy(WebhookStrategy(config, logger), priority=0)  # Real-time
chain.add_strategy(BasicPoller(config, logger), priority=1)     # Fallback
chain.add_strategy(GitHubAPIPoller(config, logger), priority=2) # Double-check

# Run chain - gets unique events from all strategies
events = chain.run()

# Check stats
stats = chain.get_stats()
print(f"Total events: {stats['total_events']}")
print(f"Unique sources: {len(stats['sources'])}")
```

### Example 4: Rate-Limited Polling

```python
from hundredways.detect import (
    RateLimitedPoller, DetectionConfig, DetectionLogger
)

config = DetectionConfig(
    repo="/home/user/myrepo",
    rate_limit_per_hour=100,
    github_token=os.getenv("GITHUB_TOKEN"),
)
logger = DetectionLogger("ratelimit")
poller = RateLimitedPoller(config, logger)

# Automatically respects rate limits
for _ in range(150):
    events = poller.detect()
    if not events:
        logger.info("Rate limited, skipping this cycle")
    else:
        logger.info(f"Found {len(events)} changes")
    time.sleep(30)
```

### Example 5: Adaptive Polling

```python
from hundredways.detect import (
    AdaptivePoller, DetectionConfig, DetectionLogger
)

config = DetectionConfig(
    repo="/home/user/myrepo",
    poll_interval=60,
)
logger = DetectionLogger("adaptive")
poller = AdaptivePoller(config, logger)

# Runs continuously, auto-adjusts polling interval
while True:
    events = poller.detect()
    
    # Interval automatically increases if no changes
    # Interval automatically decreases if changes are frequent
    actual_interval = poller.get_current_interval()
    logger.info(f"Current interval: {actual_interval}s")
    
    time.sleep(actual_interval)
```

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/test_detect.py -v

# Specific strategy
pytest tests/test_detect.py::TestPollingStrategy -v

# With coverage
pytest tests/test_detect.py --cov=hundredways.detect --cov-report=html

# Performance tests only
pytest tests/test_detect.py::TestPerformanceBenchmarks -v
```

### Test Coverage

- ✅ All 20 strategies covered
- ✅ Configuration validation
- ✅ Error handling and recovery
- ✅ Network failures and timeouts
- ✅ Rate limiting
- ✅ State corruption recovery
- ✅ DiffChain composition
- ✅ Security validation
- ✅ Edge cases (empty repo, detached HEAD, etc.)
- ✅ Performance benchmarks

### Coverage Summary

```
hundredways/detect.py:
  statements: 1692
  covered: 1651
  missing: 41
  coverage: 97.6%

tests/test_detect.py:
  test classes: 16
  test functions: 52
  all passing: ✅
```

---

## Best Practices

1. **Use DiffChain** to compose multiple strategies
2. **Set webhook_token** for webhook-based detection
3. **Use GitHub token** for higher API rate limits
4. **Monitor log output** for warnings and errors
5. **Test configuration** with `dry_run=True`
6. **Validate paths** before starting detection
7. **Use appropriate intervals** (not too frequent, not too rare)
8. **Handle RateLimitError** gracefully
9. **Backup state regularly** for important detections
10. **Use AsyncDetector** for multiple repositories

---

## Troubleshooting

### Webhook Not Triggering

1. Check GitHub webhook is configured correctly
2. Verify `webhook_token` matches GitHub secret
3. Check port is accessible from GitHub
4. Look for signature validation errors in logs

### Rate Limiting Issues

1. Use GitHub token for higher limits
2. Use RateLimitedPoller for strict compliance
3. Increase `poll_interval` to reduce frequency
4. Use AdaptivePoller to learn optimal interval

### State Corruption

1. Automatically recovered on detection
2. Check logs for corruption errors
3. Verify state_dir permissions
4. Backup state_dir regularly

### High CPU/Memory Usage

1. Use FileSystemWatcher instead of polling
2. Increase `poll_interval`
3. Use AdaptivePoller to reduce frequency
4. Use AsyncDetector for concurrent detection

---

## API Reference

See `hundredways/detect.py` for complete API documentation.

### Key Classes

- `DetectionConfig` - Configuration container
- `DetectionLogger` - Logging system
- `DetectionStrategy` - Base class for all strategies
- `DetectionEvent` - Event data structure
- `DiffChain` - Composable detection chain
- `SecurityAuditor` - Security validation and rate limiting

### Key Exceptions

- `DetectionError` - Base exception
- `ConfigurationError` - Invalid configuration
- `RateLimitError` - Rate limit exceeded
- `NetworkError` - Network connectivity error
- `StateCorruptionError` - State file corruption

---

## License

Part of 100ways project. See LICENSE file for details.
