# RESEARCH Category API Reference

Quick reference for all 20 research sources and main entry points.

## Table of Contents

- [Main Function](#main-function)
- [The 20 Research Sources](#the-20-research-sources)
- [Data Structures](#data-structures)
- [Helper Classes](#helper-classes)
- [Examples](#examples)

## Main Function

### `research(query, include_catalog=True, live=True, sources=None)`

Comprehensive research across all 20 sources with caching, rate limiting, and deduplication.

**Parameters:**
- `query` (str): Search terms, space-separated for multi-term queries
- `include_catalog` (bool, default=True): Include offline catalog
- `live` (bool, default=True): Include live API sources
- `sources` (list[str], default=None): Specific source names to search; if None, searches all available

**Returns:**
- `list[Idea]`: Deduplicated, relevance-ranked ideas

**Raises:**
- None (graceful degradation on all errors)

**Examples:**
```python
# All sources
ideas = research("fork synchronization")

# Offline only (instant)
ideas = research("patch management", live=False)

# Specific sources
ideas = research("python", sources=["github", "blog_posts"])

# With live sources
ideas = research("microservices", include_catalog=False, live=True)
```

---

## The 20 Research Sources

### 1. Catalog (`"catalog"`)

```python
def research("term", include_catalog=True, live=False)
```

**Description:** Offline hand-curated list of 15 open-source techniques

**Returns:** 15 Idea objects (always available)

**Example:**
```python
ideas = research("patch", include_catalog=True, live=False)
# Returns Idea("catalog", "Patch streaming", "https://git-scm.com/...", ...)
```

### 2. GitHub (`"github"`)

```python
search_github(query, limit=10, max_results=8)
```

**Description:** Live GitHub repository search (public REST API)

**Parameters:**
- `query` (str): Search query
- `limit` (int): Pagination size (per request)
- `max_results` (int): Maximum results to return

**Returns:** Up to 8 `Idea` objects from top-starred repos

**Rate Limit:** 30 req/min (unauthenticated)

**Example:**
```python
repos = search_github("fork sync", limit=10, max_results=5)
# Returns top 5 repos sorted by stars
```

### 3. Academic Papers (`"academic_papers"`)

```python
search_academic_papers(query, max_results=5)
```

**Description:** arXiv papers (physics, CS, mathematics)

**Parameters:**
- `query` (str): Search query
- `max_results` (int): Limit results

**Returns:** Parsed arXiv entries with summaries and dates

**Example:**
```python
papers = search_academic_papers("distributed systems", max_results=3)
# Returns (title, URL to arxiv, summary, published_date)
```

### 4. Blog Posts (`"blog_posts"`)

```python
search_blog_posts(query, max_results=5)
```

**Description:** Technical blog search (Medium, Dev.to, Hashnode, etc.)

**Returns:** Blog aggregator links and search results

**Note:** Uses Google site search (no API credentials needed)

**Example:**
```python
blogs = search_blog_posts("kubernetes", max_results=3)
# Returns blog aggregators for multiple platforms
```

### 5. GitHub Discussions (`"github_discussions"`)

```python
search_github_discussions(query, max_results=5)
```

**Description:** GitHub Discussions (community Q&A)

**Returns:** Discussion threads with titles and summaries

**Example:**
```python
discussions = search_github_discussions("async rust", max_results=5)
# Returns community discussions from GitHub
```

### 6. Stack Overflow (`"stack_overflow"`)

```python
search_stack_overflow(query, max_results=5)
```

**Description:** Stack Overflow Q&A (scored by community)

**Parameters:**
- `query` (str): Search query
- `max_results` (int): Limit results

**Returns:** Top questions with score and answer count

**Ranking Signal:** Score (higher = more helpful)

**Example:**
```python
qa = search_stack_overflow("python async", max_results=5)
# Returns (title, URL, score, answer_count, created_date)
```

### 7. RFC Documents (`"rfc_documents"`)

```python
search_rfc_documents(query, max_results=5)
```

**Description:** Internet standards (IETF RFCs)

**Returns:** RFC search link and matching standards

**Authority:** Formal technical specifications

**Example:**
```python
rfcs = search_rfc_documents("HTTP", max_results=3)
# Returns links to HTTP-related RFCs (2616, 7231, etc.)
```

### 8. Security Advisories (`"security_advisories"`)

```python
search_security_advisories(query, max_results=5)
```

**Description:** CVE and vulnerability databases

**Sources:** NVD, GitHub Security, OSS-Fuzz

**Returns:** Multiple security databases with search links

**Example:**
```python
vulns = search_security_advisories("openssl", max_results=3)
# Returns CVE search, GitHub advisories, OSS-Fuzz results
```

### 9. Performance Benchmarks (`"performance_benchmarks"`)

```python
search_performance_benchmarks(query, max_results=5)
```

**Description:** Performance data and benchmarks

**Sources:** TechEmpower, SPEC, GitHub benchmarks

**Returns:** Benchmark comparison links

**Example:**
```python
benches = search_performance_benchmarks("Python web", max_results=3)
# Returns TechEmpower, SPEC, and GitHub benchmark results
```

### 10. Case Studies (`"case_studies"`)

```python
search_case_studies(query, max_results=5)
```

**Description:** Real-world implementations and lessons

**Sources:** Hacker News, ArsTechnica, InfoQ

**Returns:** Articles with case studies and technical analysis

**Example:**
```python
cases = search_case_studies("microservices migration", max_results=3)
# Returns real-world case studies and lessons learned
```

### 11. Video Tutorials (`"video_tutorials"`)

```python
search_video_tutorials(query, max_results=5)
```

**Description:** Technical video content

**Platforms:** YouTube, Vimeo, conference recordings

**Returns:** Video platform search links

**Example:**
```python
videos = search_video_tutorials("git workflow", max_results=3)
# Returns YouTube, Vimeo, and conference video results
```

### 12. Tool Comparisons (`"tool_comparisons"`)

```python
search_tool_comparisons(query, max_results=5)
```

**Description:** Feature matrices and tool alternatives

**Sources:** Slant, AlternativeTo, GitHub

**Returns:** Comparison platform links

**Example:**
```python
comps = search_tool_comparisons("Python testing", max_results=3)
# Returns tool comparison pages
```

### 13. Plugin Ecosystems (`"plugin_ecosystems"`)

```python
search_plugin_ecosystems(query, max_results=5)
```

**Description:** Package registries and extension marketplaces

**Registries:** PyPI, npm, VS Code Marketplace, GitHub Apps

**Returns:** Registry links for each platform

**Example:**
```python
plugins = search_plugin_ecosystems("VS Code", max_results=4)
# Returns PyPI, npm, VS Code Marketplace, GitHub Apps
```

### 14. Fork Analysis (`"fork_analysis"`)

```python
search_fork_analysis(query, max_results=5)
```

**Description:** Repository forks and variants

**API:** GitHub search with fork filter

**Ranking Signal:** Star count (popular forks)

**Returns:** Most-starred forks of a repository

**Example:**
```python
forks = search_fork_analysis("tensorflow", max_results=5)
# Returns popular TensorFlow forks with descriptions
```

### 15. Upstream Policy Docs (`"upstream_policy_docs"`)

```python
search_upstream_policy_docs(query, max_results=5)
```

**Description:** Governance and policy documents

**Files:** CONTRIBUTING.md, GOVERNANCE.md, CODE_OF_CONDUCT.md, ROADMAP.md

**Returns:** Links to policy file patterns

**Example:**
```python
policy = search_upstream_policy_docs("kubernetes", max_results=4)
# Returns policy doc patterns for Kubernetes project
```

### 16. Community Forums (`"community_forums"`)

```python
search_community_forums(query, max_results=5)
```

**Description:** Discussion communities

**Platforms:** Reddit, Discourse, Stack Exchange

**Returns:** Forum search links

**Example:**
```python
forums = search_community_forums("rust", max_results=3)
# Returns Reddit, Discourse, Stack Exchange results
```

### 17. Git History Analysis (`"git_history_analysis"`)

```python
search_git_history_analysis(query, max_results=5)
```

**Description:** Commit history and patterns

**API:** GitHub repository commits

**Returns:** Links to commit history of matching repos

**Example:**
```python
history = search_git_history_analysis("linux", max_results=3)
# Returns top Linux projects' commit history links
```

### 18. Architecture Diagrams (`"architecture_diagrams"`)

```python
search_architecture_diagrams(query, max_results=5)
```

**Description:** System design and architecture docs

**Sources:** READMEs, /docs folders, architecture files

**Returns:** Links to architecture documentation

**Example:**
```python
arch = search_architecture_diagrams("distributed systems", max_results=3)
# Returns architecture docs and design patterns
```

### 19. Benchmark Datasets (`"benchmark_datasets"`)

```python
search_benchmark_datasets(query, max_results=5)
```

**Description:** Test and performance datasets

**Registries:** Kaggle, UCI ML, GitHub

**Returns:** Dataset registry links

**Example:**
```python
datasets = search_benchmark_datasets("NLP", max_results=3)
# Returns Kaggle, UCI ML, and GitHub datasets
```

### 20. Vendor Documentation (`"vendor_documentation"`)

```python
search_vendor_documentation(query, max_results=5)
```

**Description:** Official product documentation

**Sources:** AWS, GitHub Docs, vendor sites

**Returns:** Official documentation links

**Example:**
```python
docs = search_vendor_documentation("AWS Lambda", max_results=3)
# Returns official AWS, GitHub, and vendor docs
```

---

## Data Structures

### `Idea` Dataclass

```python
@dataclass(frozen=True)
class Idea:
    source: str                          # e.g., "github", "catalog"
    title: str                           # Item title
    url: str                             # Direct URL
    summary: str                         # 200-char description
    tags: tuple[str, ...] = ()           # e.g., ("python", "testing")
    relevance_score: float = 1.0         # 0.0-1.0
    published_date: Optional[str] = None # ISO 8601
    author: Optional[str] = None         # Original author
```

**Methods:**

`dedup_key() -> str`
- Returns SHA256 hash of (title:url) for deduplication
- Case-insensitive
- Returns 16-character hex string

**Example:**
```python
idea = Idea("github", "myrepo", "https://github.com/a/b", "Desc", tags=("python",))
key = idea.dedup_key()  # Stable across runs
```

### `ResearchSource` Enum

```python
class ResearchSource(Enum):
    CATALOG = "catalog"
    GITHUB = "github"
    ACADEMIC_PAPERS = "academic_papers"
    BLOG_POSTS = "blog_posts"
    GITHUB_DISCUSSIONS = "github_discussions"
    STACK_OVERFLOW = "stack_overflow"
    RFC_DOCUMENTS = "rfc_documents"
    SECURITY_ADVISORIES = "security_advisories"
    PERFORMANCE_BENCHMARKS = "performance_benchmarks"
    CASE_STUDIES = "case_studies"
    VIDEO_TUTORIALS = "video_tutorials"
    TOOL_COMPARISONS = "tool_comparisons"
    PLUGIN_ECOSYSTEMS = "plugin_ecosystems"
    FORK_ANALYSIS = "fork_analysis"
    UPSTREAM_POLICY_DOCS = "upstream_policy_docs"
    COMMUNITY_FORUMS = "community_forums"
    GIT_HISTORY_ANALYSIS = "git_history_analysis"
    ARCHITECTURE_DIAGRAMS = "architecture_diagrams"
    BENCHMARK_DATASETS = "benchmark_datasets"
    VENDOR_DOCUMENTATION = "vendor_documentation"
```

**Usage:**
```python
source = ResearchSource.GITHUB.value  # "github"
for source in ResearchSource:
    print(source.value)  # All 20 sources
```

---

## Helper Classes

### `CachedHTTPRequest`

In-memory HTTP cache with TTL.

```python
cache = CachedHTTPRequest(ttl_seconds=3600)

cache.set(url, json_data)        # Cache response
cached = cache.get(url)          # Retrieve if not expired
cache.cache.clear()              # Clear all
cache.cache.pop(url, None)       # Clear specific URL
```

**Global Instance:**
```python
from hundredways.research import _http_cache
_http_cache.get("https://...")
```

### `RateLimiter`

Per-domain rate limiting with sliding window.

```python
limiter = RateLimiter(requests_per_minute=30)

if limiter.should_rate_limit(domain):
    # Skip request
    pass

domain = limiter.get_domain(url)  # Extract domain
```

**Global Instance:**
```python
from hundredways.research import _rate_limiter
_rate_limiter.should_rate_limit("api.github.com")
```

---

## Helper Functions

### `_fetch_json(url, headers=None, timeout=15)`

Fetch JSON with caching and rate limiting.

**Parameters:**
- `url` (str): URL to fetch
- `headers` (dict, optional): HTTP headers
- `timeout` (int): Request timeout (default 15s)

**Returns:**
- `dict` or `None`: Parsed JSON or None on error

**Features:**
- Uses HTTP cache (1h TTL)
- Respects rate limits
- Graceful error handling

**Example:**
```python
from hundredways.research import _fetch_json

data = _fetch_json("https://api.github.com/...", headers={"Accept": "application/json"})
if data:
    print(data["key"])
```

### `_deduplicate_ideas(ideas)`

Remove duplicate ideas by title+URL hash.

**Parameters:**
- `ideas` (list[Idea]): Ideas to deduplicate

**Returns:**
- `list[Idea]`: Deduplicated list (preserves highest scores)

**Example:**
```python
from hundredways.research import _deduplicate_ideas

ideas = [
    Idea("...", "Title", "url", "desc"),
    Idea("...", "Title", "url", "desc"),  # Duplicate
]
deduped = _deduplicate_ideas(ideas)
assert len(deduped) == 1
```

### `_rank_by_relevance(ideas, query_terms)`

Rank ideas by relevance to query terms.

**Parameters:**
- `ideas` (list[Idea]): Ideas to rank
- `query_terms` (list[str]): Query terms to match

**Returns:**
- `list[Idea]`: Ranked by relevance (highest first)

**Scoring:**
- Exact phrase in title: ×1.5
- Term in summary: ×1.1 per term
- Tag match: ×1.15 per term
- Capped at 1.0

**Example:**
```python
from hundredways.research import _rank_by_relevance

ranked = _rank_by_relevance(ideas, ["python", "testing"])
best = ranked[0]  # Highest relevance
```

---

## Examples

### Search Everything

```python
from hundredways.research import research

results = research("fork synchronization")
print(f"Found {len(results)} ideas")

for idea in results[:10]:
    print(f"[{idea.source}] {idea.title}")
    print(f"  Score: {idea.relevance_score:.2%}")
    print(f"  {idea.url}\n")
```

### Fast Local Search

```python
from hundredways.research import research

# No network calls
results = research("git", include_catalog=True, live=False)
print(f"Catalog-only: {len(results)} results")
```

### Search Multiple Sources

```python
from hundredways.research import research

sources = ["github", "academic_papers", "stack_overflow"]
results = research("async python", sources=sources)
print(f"From {len(set(r.source for r in results))} sources: {len(results)} results")
```

### Direct Source Search

```python
from hundredways.research import search_github, search_stack_overflow

repos = search_github("machine learning", max_results=5)
qa = search_stack_overflow("Python machine learning", max_results=5)

for repo in repos:
    print(f"Repo: {repo.title}")

for question in qa:
    print(f"Q&A: {question.title}")
```

### Custom Processing

```python
from hundredways.research import research

ideas = research("testing")

# Filter by source
github_ideas = [i for i in ideas if i.source == "github"]

# Filter by score
high_quality = [i for i in ideas if i.relevance_score > 0.7]

# By tag
tagged = [i for i in ideas if "python" in i.tags]

# Export
for idea in ideas:
    print(f"{idea.source},{idea.title},{idea.url},{idea.relevance_score}")
```

---

## Constants

### `CATALOG`

```python
from hundredways.research import CATALOG

len(CATALOG)  # 15 ideas
for idea in CATALOG:
    print(idea)
```

---

## Global State

```python
from hundredways.research import _http_cache, _rate_limiter

# Cache
_http_cache.cache           # dict of cached URLs
_http_cache.ttl             # seconds

# Rate limiter
_rate_limiter.request_times # dict of domain -> [timestamps]
_rate_limiter.requests_per_minute  # limit

# Reset
_http_cache.cache.clear()
_rate_limiter.request_times.clear()
```

---

## Performance Tips

1. **Reuse results**: Cache research results locally if querying repeatedly
2. **Use offline**: `live=False` for instant results
3. **Specific sources**: Pass `sources` list to skip slow/irrelevant sources
4. **Batch queries**: Call `research()` once with multiple terms, not multiple times

---

## See Also

- [Full RESEARCH Guide](RESEARCH_GUIDE.md)
- [Tests](../tests/test_research.py)
- [Source Code](../hundredways/research.py)
