# DETECT Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       DiffChain                              │
│  (Composable Detection Pipeline)                            │
└─────────────────────────────────────────────────────────────┘
        ▲              ▲              ▲              ▲
        │              │              │              │
        │              │              │              │
┌───────┴─┐  ┌────────┴──┐  ┌───────┴──┐  ┌───────┴──┐
│Webhook  │  │  Polling  │  │ GitHub   │  │ Others   │
│Strategy │  │  Strategy │  │   API    │  │          │
└────┬────┘  └─────┬─────┘  └────┬─────┘  └────┬─────┘
     │            │              │             │
     └────────────┼──────────────┼─────────────┘
                  │
     ┌────────────▼──────────────┐
     │   SecurityAuditor         │
     │  - Input validation       │
     │  - Rate limiting          │
     │  - State recovery         │
     └────────────┬──────────────┘
                  │
     ┌────────────▼──────────────┐
     │   DetectionEvent          │
     │  - kind                   │
     │  - timestamp              │
     │  - source                 │
     │  - metadata               │
     └────────────┬──────────────┘
                  │
     ┌────────────▼──────────────┐
     │   Application Handler     │
     └───────────────────────────┘
```

## Component Hierarchy

### 1. DetectionStrategy (Abstract Base)

All 20 strategies inherit from `DetectionStrategy`:

```python
class DetectionStrategy(ABC):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.auditor = SecurityAuditor(config, logger)
        self.lock = threading.Lock()
        self.name = self.__class__.__name__
    
    @abstractmethod
    def detect(self) -> list[DetectionEvent]:
        """Detect changes and return events."""
    
    @abstractmethod
    def configure(self, **kwargs):
        """Configure strategy parameters."""
    
    @abstractmethod
    def reset(self):
        """Reset strategy state."""
```

### 2. DetectionConfig

Configuration container with sensible defaults:

```python
@dataclass
class DetectionConfig:
    # Repository settings
    repo: str                                    # Path to Git repository
    upstream_remote: str = "origin"             # Remote name
    upstream_branch: str = "main"               # Branch to track
    
    # Polling settings
    poll_interval: int = 60                     # Seconds
    timeout: int = 5                            # Seconds
    max_retries: int = 3                        # Retry count
    
    # Webhook settings
    webhook_port: int = 5000                    # Flask port
    webhook_token: str = ""                     # HMAC secret
    
    # GitHub API settings
    github_token: str = ""                      # Personal access token
    
    # State management
    state_dir: str = ".detection_state"         # State directory
    
    # Performance settings
    rate_limit_per_hour: int = 60               # Rate limit
    batch_size: int = 10                        # Batch size
    
    # Logging
    enable_logging: bool = True
    log_level: str = "INFO"
    
    # Other settings
    dry_run: bool = False
    remote_hosts: list[str] = field(default_factory=list)
```

### 3. DetectionEvent

Data structure for detection results:

```python
@dataclass
class DetectionEvent:
    kind: DetectionKind              # Type of change (NEW_COMMITS, etc.)
    timestamp: datetime              # When detected
    source: str                       # Which strategy detected
    branch: str = ""                 # Branch affected
    upstream_sha: str = ""           # Commit SHA
    requires_action: bool = False    # Needs immediate handling
    data: dict[str, Any] = field(default_factory=dict)  # Extra metadata
```

### 4. DetectionKind (Event Types)

```python
class DetectionKind(Enum):
    NEW_COMMITS = "new_commits"           # New commits detected
    BRANCH_CREATED = "branch_created"     # New branch
    BRANCH_DELETED = "branch_deleted"     # Branch deleted
    TAG_CREATED = "tag_created"           # New tag
    TAG_DELETED = "tag_deleted"           # Tag deleted
    PR_OPENED = "pr_opened"               # PR opened
    PR_CLOSED = "pr_closed"               # PR closed
    PR_MERGED = "pr_merged"               # PR merged
    RELEASE_PUBLISHED = "release_published"  # Release created
    SYNC_NEEDED = "sync_needed"           # Sync needed
```

### 5. DiffChain (Composition)

Orchestrates multiple strategies:

```python
class DiffChain:
    def __init__(self, config, logger):
        self.strategies = []                # List of strategies
        self.events = []                    # Event history
        self.dedup_cache = set()            # Deduplication
        self.metrics = {}                   # Performance metrics
    
    def add_strategy(self, strategy, priority=999):
        """Add strategy with priority."""
        self.strategies.append((priority, strategy))
        self.strategies.sort(key=lambda x: x[0])
    
    def run(self) -> list[DetectionEvent]:
        """Execute all strategies, deduplicate events."""
        all_events = []
        for priority, strategy in self.strategies:
            try:
                events = strategy.detect()
                all_events.extend(events)
            except Exception as e:
                self.logger.error(f"Strategy {strategy.name} failed: {e}")
        
        # Deduplicate
        unique = []
        for event in all_events:
            key = (event.kind, event.branch, event.upstream_sha)
            if key not in self.dedup_cache:
                unique.append(event)
                self.dedup_cache.add(key)
        
        return unique
```

### 6. SecurityAuditor

Validates inputs and enforces security policies:

```python
class SecurityAuditor:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.state_dir = Path(config.state_dir)
        self.call_log = {}                  # Rate limit tracking
    
    def validate_repo_path(self, path):
        """Ensure path is valid Git repository."""
    
    def validate_sha(self, sha):
        """Validate Git SHA format."""
    
    def validate_branch_name(self, name):
        """Validate branch name."""
    
    def validate_remote_url(self, url):
        """Validate remote URL."""
    
    def can_call(self, strategy) -> bool:
        """Check rate limit before external call."""
    
    def validate_webhook_signature(self, payload, signature, secret):
        """Validate HMAC-SHA256 webhook signature."""
    
    def recover_corrupted_state(self, strategy) -> dict:
        """Recover from state file corruption."""
```

## Execution Flow

### Polling Strategy Flow

```
detect() called
    │
    ├─→ SecurityAuditor.can_call() [Rate limit check]
    │
    ├─→ Git command: git fetch origin
    │
    ├─→ Compare: upstream vs local
    │
    ├─→ Create DetectionEvent if changed
    │
    ├─→ Save state to disk
    │
    └─→ Return events
```

### Webhook Strategy Flow

```
receive_webhook(payload, signature)
    │
    ├─→ SecurityAuditor.validate_webhook_signature()
    │
    ├─→ Parse GitHub payload
    │
    ├─→ Create DetectionEvent
    │
    ├─→ Queue event
    │
    └─→ Return success

detect()
    │
    └─→ Return queued events
```

### DiffChain Flow

```
chain.run()
    │
    ├─→ For each strategy (priority order):
    │   │
    │   ├─→ Call strategy.detect()
    │   │
    │   ├─→ Catch exceptions
    │   │
    │   └─→ Collect events
    │
    ├─→ Deduplicate events
    │
    ├─→ Update metrics
    │
    └─→ Return unique events
```

## Data Persistence

### State File Format

State files stored as JSON in `state_dir/`:

```json
{
  "strategy": "polling_strategy",
  "last_check": "2026-09-23T08:35:52.105Z",
  "last_upstream_sha": "abc123def456...",
  "last_local_sha": "def456abc123...",
  "event_count": 42,
  "errors": [],
  "version": 1
}
```

### Backup Strategy

```
Primary:   state_dir/strategy_name.json
Backup 1:  state_dir/strategy_name.json.bak
Backup 2:  state_dir/strategy_name.json.bak2
```

On corruption, automatically falls back to most recent valid backup.

## Error Handling Strategy

### Error Hierarchy

```
DetectionError (Base)
    ├── ConfigurationError
    ├── NetworkError
    ├── RateLimitError
    ├── StateCorruptionError
    ├── TimeoutError
    └── PermissionError
```

### Retry Strategy

**ExponentialBackoffPoller:**
- Attempt 1: immediate
- Attempt 2: 1s delay
- Attempt 3: 2s delay
- Attempt 4: 4s delay
- Attempt 5: 8s delay
- Max: 3 (configurable)

### Graceful Degradation

- **RateLimitError**: Skip this cycle, retry next
- **NetworkError**: Exponential backoff, continue
- **StateCorruptionError**: Recover from backup, continue
- **TimeoutError**: Skip this check, try again later

## Performance Characteristics

### Strategy Benchmarks

| Strategy | Latency | Throughput | Overhead |
|----------|---------|-----------|----------|
| Polling | 1-5s | 60/min | ~50ms |
| Webhook | <100ms | unlimited | <10ms |
| GitHub API | 0.5-2s | 5k/hr | ~100ms |
| RSS Feed | 1-3s | 20/min | ~50ms |
| Async | <500ms | unlimited | variable |

### Memory Usage

- Per strategy: ~1-2 MB (state + queue)
- DiffChain overhead: ~100 KB (dedup cache)
- Event history: ~10 KB per 1000 events

### CPU Usage

- Polling: Low (<1%)
- Webhook: Very low (<0.1%)
- Async: Medium (2-5% with multiple tasks)
- DiffChain: Low (<1% for coordination)

## Extensibility

### Adding a New Strategy

```python
from hundredways.detect import DetectionStrategy, DetectionEvent, DetectionKind
from dataclasses import dataclass

@dataclass
class MyStrategyConfig:
    """Config for MyStrategy."""
    my_param: str = "default"

class MyStrategy(DetectionStrategy):
    """Custom detection strategy."""
    
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.my_config = MyStrategyConfig()
    
    def detect(self) -> list[DetectionEvent]:
        """Implement your detection logic."""
        # Validate rate limit
        if not self.auditor.can_call(self.name):
            self.logger.warning("Rate limited")
            return []
        
        # Your detection logic here
        events = []
        
        # Create event if change detected
        if change_detected:
            events.append(DetectionEvent(
                kind=DetectionKind.NEW_COMMITS,
                timestamp=datetime.now(),
                source=self.name,
                data={"details": "..."}
            ))
        
        return events
    
    def configure(self, **kwargs):
        """Configure strategy."""
        for key, value in kwargs.items():
            setattr(self.my_config, key, value)
    
    def reset(self):
        """Reset strategy state."""
        self._load_state({})
```

### Registering Strategy in DiffChain

```python
chain = DiffChain(config, logger)
chain.add_strategy(MyStrategy(config, logger), priority=5)
events = chain.run()
```

## Testing Architecture

### Test Structure

```
tests/test_detect.py
├── TestSecurityAuditor (8 tests)
│   ├── Input validation
│   ├── Rate limiting
│   ├── Signature validation
│   └── State recovery
├── TestPollingStrategy (3 tests)
├── TestWebhookStrategy (4 tests)
├── ... (other strategies)
├── TestDiffChain (8 tests)
├── TestPerformanceBenchmarks (2 tests)
└── TestEdgeCases (4 tests)
```

### Test Categories

1. **Unit Tests**: Individual strategy behavior
2. **Integration Tests**: Strategy composition
3. **Security Tests**: Input validation, rate limits
4. **Performance Tests**: Latency and throughput
5. **Edge Cases**: Empty repo, corrupted state, etc.

### Fixtures

```python
@pytest.fixture
def git_repo():
    """Create temporary Git repository."""
    
@pytest.fixture
def upstream_repo():
    """Create temporary upstream repository."""
    
@pytest.fixture
def test_config(git_repo, upstream_repo):
    """DetectionConfig for testing."""
    
@pytest.fixture
def logger():
    """DetectionLogger for testing."""
```

## Logging Strategy

### Log Levels

- **DEBUG**: Detailed execution flow
- **INFO**: Important state changes
- **WARNING**: Recoverable errors, rate limits
- **ERROR**: Unrecoverable errors

### Log Format

```
2026-09-23 08:35:52,105 [detect.strategy_name] LEVEL: message
```

### Sample Logs

```
DEBUG: Polling started for origin/main
INFO: New commit detected: abc123
WARNING: Rate limit approaching (45/60 calls)
ERROR: State file corrupted, recovering from backup
```

## Security Considerations

### Input Validation

- ✅ Git SHAs: 40+ hex characters
- ✅ Branch names: alphanumeric, dash, underscore
- ✅ URLs: Must match pattern, https required
- ✅ Paths: Must be absolute, readable

### Secret Management

- ✅ Tokens passed via environment variables
- ✅ Never logged or stored in state files
- ✅ Webhook tokens validated with HMAC-SHA256
- ✅ No default credentials

### Rate Limiting

- ✅ Enforced at SecurityAuditor level
- ✅ Tracked per strategy
- ✅ Configurable limit
- ✅ Graceful degradation when exceeded

## Future Enhancements

1. **Clustering**: Distribute strategies across hosts
2. **Persistence**: Kafka/Redis event streaming
3. **Metrics**: Prometheus integration
4. **Alerting**: Send alerts on detection
5. **Machine Learning**: Predict change frequency
6. **Webhooks**: Custom webhook transformers
7. **Multi-Repo**: Built-in support for multiple repos
8. **Caching**: Reduce API calls with caching

---

See [DETECT.md](DETECT.md) for comprehensive documentation.
