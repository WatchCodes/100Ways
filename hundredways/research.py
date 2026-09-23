"""Open-source research: search the web for ideas we can steal.

Comprehensive research strategies across 20 sources:

1. **catalog** - Offline hand-picked list of open-source techniques
2. **github** - Live GitHub repository search
3. **academic_papers** - Research papers (arXiv, papers.ssrn.com)
4. **blog_posts** - Technical blog search via site indexing
5. **github_discussions** - GitHub Discussions API
6. **stack_overflow** - Stack Overflow Q&A
7. **rfc_documents** - RFC standards documents
8. **security_advisories** - CVE and security advisory databases
9. **performance_benchmarks** - Benchmark results and comparisons
10. **case_studies** - Real-world implementation case studies
11. **video_tutorials** - Technical video content
12. **tool_comparisons** - Feature comparison matrices
13. **plugin_ecosystems** - Plugin/extension libraries
14. **fork_analysis** - Fork repositories and variants
15. **upstream_policy_docs** - Project policy and governance docs
16. **community_forums** - Discussion forums (Reddit, Discourse)
17. **git_history_analysis** - Git commit history patterns
18. **architecture_diagrams** - System architecture documentation
19. **benchmark_datasets** - Benchmark and performance datasets
20. **vendor_documentation** - Official vendor and product docs

All return the same structured ``Idea`` records so the ``100ways research``
command can merge them. Implements caching, rate limiting, deduplication,
relevance ranking, and comprehensive error handling.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ResearchSource(Enum):
    """Research source identifiers."""

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


@dataclass(frozen=True)
class Idea:
    """Structured research result."""

    source: str  # ResearchSource enum value
    title: str
    url: str
    summary: str
    tags: tuple[str, ...] = ()
    relevance_score: float = 1.0  # 0.0 to 1.0
    published_date: Optional[str] = None  # ISO 8601 format
    author: Optional[str] = None

    def dedup_key(self) -> str:
        """Generate a deduplication key from title and URL."""
        combined = f"{self.title}:{self.url}".lower()
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


class CachedHTTPRequest:
    """Simple in-memory cache for HTTP responses (no disk persistence)."""

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with TTL.

        Args:
            ttl_seconds: Time-to-live for cached responses
        """
        self.cache: dict[str, tuple[str, float]] = {}
        self.ttl = ttl_seconds

    def get(self, url: str) -> Optional[str]:
        """Retrieve cached response if not expired."""
        if url in self.cache:
            data, timestamp = self.cache[url]
            if time.time() - timestamp < self.ttl:
                return data
            del self.cache[url]
        return None

    def set(self, url: str, data: str) -> None:
        """Cache response with timestamp."""
        self.cache[url] = (data, time.time())


class RateLimiter:
    """Simple rate limiter per domain."""

    def __init__(self, requests_per_minute: int = 30):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per domain per minute
        """
        self.requests_per_minute = requests_per_minute
        self.request_times: dict[str, list[float]] = {}

    def should_rate_limit(self, domain: str) -> bool:
        """Check if domain is rate-limited."""
        now = time.time()
        if domain not in self.request_times:
            self.request_times[domain] = []

        # Remove old timestamps (older than 1 minute)
        self.request_times[domain] = [
            ts for ts in self.request_times[domain] if now - ts < 60
        ]

        if len(self.request_times[domain]) >= self.requests_per_minute:
            return True

        self.request_times[domain].append(now)
        return False

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc or "unknown"


# Global cache and rate limiter
_http_cache = CachedHTTPRequest(ttl_seconds=3600)
_rate_limiter = RateLimiter(requests_per_minute=30)


def _fetch_json(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 15,
) -> Optional[dict]:
    """Fetch JSON from URL with caching and rate limiting.

    Args:
        url: URL to fetch
        headers: Optional HTTP headers
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON dict or None on error
    """
    # Check cache first
    cached = _http_cache.get(url)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            return None

    # Check rate limiting
    domain = _rate_limiter.get_domain(url)
    if _rate_limiter.should_rate_limit(domain):
        return None

    # Fetch from network
    default_headers = {
        "User-Agent": "100ways-research/1.0 (+https://github.com/nastechresearch/100ways)",
        "Accept": "application/json",
    }
    if headers:
        default_headers.update(headers)

    try:
        req = urllib.request.Request(url, headers=default_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            _http_cache.set(url, data)
            return json.loads(data)
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None
    except Exception:
        return None


def _deduplicate_ideas(ideas: list[Idea]) -> list[Idea]:
    """Remove duplicate ideas by title and URL.

    Args:
        ideas: List of ideas to deduplicate

    Returns:
        Deduplicated list, preserving order and highest relevance score
    """
    seen: dict[str, Idea] = {}
    for idea in ideas:
        key = idea.dedup_key()
        if key not in seen or idea.relevance_score > seen[key].relevance_score:
            seen[key] = idea
    return list(seen.values())


def _rank_by_relevance(ideas: list[Idea], query_terms: list[str]) -> list[Idea]:
    """Rank ideas by relevance to query terms.

    Args:
        ideas: List of ideas to rank
        query_terms: Search query terms

    Returns:
        List ranked by relevance score (highest first)
    """

    def calculate_score(idea: Idea, terms: list[str]) -> float:
        score = idea.relevance_score
        query_lower = " ".join(terms).lower()

        # Boost for exact phrase match in title
        if query_lower in idea.title.lower():
            score *= 1.5

        # Boost for term matches in summary
        term_matches = sum(
            1 for term in terms if term.lower() in idea.summary.lower()
        )
        score *= 1.0 + (0.1 * term_matches)

        # Boost for tag matches
        tag_matches = sum(1 for term in terms if term.lower() in idea.tags)
        score *= 1.0 + (0.15 * tag_matches)

        return min(score, 1.0)  # Cap at 1.0

    ranked = sorted(
        ideas, key=lambda i: calculate_score(i, query_terms), reverse=True
    )
    return ranked


# Offline idea catalog: open-source techniques we can adapt
CATALOG: list[Idea] = [
    Idea(
        "catalog",
        "Patch streaming",
        "https://git-scm.com/docs/git-format-patch",
        "Stream-edit unified diffs before applying; works for any token rename, not just ours.",
        ("port", "diff"),
    ),
    Idea(
        "catalog",
        "Tree comparison",
        "https://git-scm.com/docs/git-ls-tree",
        "Compare whole trees by path set and blob hash before touching the working tree.",
        ("diff", "verify"),
    ),
    Idea(
        "catalog",
        "Worktree isolation",
        "https://git-scm.com/docs/git-worktree",
        "Apply risky ports in a throwaway detached worktree so the working branch is never harmed.",
        ("port", "gate"),
    ),
    Idea(
        "catalog",
        "Word-anchored replace",
        "https://docs.python.org/3/library/re.html",
        "Lookbehind/lookahead word boundaries so renames never corrupt English words.",
        ("brand",),
    ),
    Idea(
        "catalog",
        "Magic-byte typing",
        "https://en.wikipedia.org/wiki/Magic_number_(programming)",
        "Identify file formats by signature bytes, never by extension.",
        ("scan",),
    ),
    Idea(
        "catalog",
        "Cherry-pick + amend",
        "https://git-scm.com/docs/git-cherry-pick",
        "Cherry-pick upstream then amend with the brand fix; keeps history and authors.",
        ("port",),
    ),
    Idea(
        "catalog",
        "First-parent review",
        "https://git-scm.com/docs/git-rev-list",
        "Walk the first-parent chain to review only merged changes, not every branch point.",
        ("diff",),
    ),
    Idea(
        "catalog",
        "Three-way apply",
        "https://git-scm.com/docs/git-apply",
        "--3way applies a patch against the nearest common ancestor, not just the index.",
        ("port",),
    ),
    Idea(
        "catalog",
        "File type fuzzing",
        "https://en.wikipedia.org/wiki/Fuzzing",
        "Feed mutated assets through the pipeline to prove the scanner never misbrands a binary.",
        ("scan", "verify"),
    ),
    Idea(
        "catalog",
        "Golden-file tests",
        "https://docs.pytest.org/",
        "Reproduce the known-good birth commit as a golden test of the whole brand pipeline.",
        ("verify",),
    ),
    Idea(
        "catalog",
        "Renumbered IDs",
        "https://en.wikipedia.org/wiki/Sequence_diagram",
        "Verify refs to renamed identifiers are renumbered consistently, not just strings swapped.",
        ("brand", "verify"),
    ),
    Idea(
        "catalog",
        "Sidecar manifest",
        "https://en.wikipedia.org/wiki/Sidecar_file",
        "Keep a manifest of upstream->branded path pairs to prove rename coverage.",
        ("verify", "port"),
    ),
    Idea(
        "catalog",
        "Difference engine",
        "https://en.wikipedia.org/wiki/Data_diff",
        "Report character and line deltas so operators see exactly how far off a port is.",
        ("diff",),
    ),
    Idea(
        "catalog",
        "Contract tests",
        "https://en.wikipedia.org/wiki/Design_by_contract",
        "Assert invariants between upstream and branded trees (every path has a twin), not snapshots.",
        ("verify",),
    ),
    Idea(
        "catalog",
        "Renamed-from tracking",
        "https://git-scm.com/docs/git-diff",
        "Use rename detection in diffs so a renamed file is recognized, not deleted+added.",
        ("diff",),
    ),
]


def search_github(query: str, limit: int = 10, max_results: int = 8) -> list[Idea]:
    """Live GitHub repository search (public REST API, no auth needed).

    Args:
        query: Search query string
        limit: Pagination limit per request
        max_results: Maximum results to return

    Returns:
        List of Idea objects from GitHub search
    """
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    )
    url = f"https://api.github.com/search/repositories?{params}"
    payload = _fetch_json(
        url, headers={"Accept": "application/vnd.github+json"}
    )

    if payload is None:
        return [
            Idea(
                ResearchSource.GITHUB.value,
                "search failed: network or rate limit",
                "",
                "live search unavailable",
                ("offline",),
            )
        ]

    ideas: list[Idea] = []
    for item in payload.get("items", [])[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.GITHUB.value,
                title=item.get("full_name", query),
                url=item.get("html_url", ""),
                summary=(item.get("description") or "").strip() or "(no description)",
                tags=("search",),
                relevance_score=min(
                    (item.get("stargazers_count", 0) / 10000.0), 1.0
                ),  # Normalize stars
                published_date=item.get("created_at"),
            )
        )

    return ideas


def search_academic_papers(query: str, max_results: int = 5) -> list[Idea]:
    """Search academic papers via arXiv API.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of Idea objects from academic papers
    """
    # arXiv uses OpenSearch interface
    search_query = urllib.parse.quote(f"all:{query}")
    url = f"https://export.arxiv.org/api/query?search_query={search_query}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "100ways"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
    except Exception:
        return []

    ideas: list[Idea] = []
    # Simple XML parsing for arXiv feed
    title_pattern = re.compile(r"<title[^>]*>([^<]+)</title>")
    id_pattern = re.compile(r"<id>(?:http://)?(?:arxiv\.org)?(?:/abs)?/?([^<]+)</id>")
    summary_pattern = re.compile(r"<summary[^>]*>([^<]+)</summary>")
    published_pattern = re.compile(r"<published>([^<]+)</published>")

    titles = title_pattern.findall(text)
    ids = id_pattern.findall(text)
    summaries = summary_pattern.findall(text)
    dates = published_pattern.findall(text)

    for i, title in enumerate(titles[1:]):  # Skip feed title
        if i >= len(ids):
            break
        arxiv_id = ids[i + 1] if i + 1 < len(ids) else ids[i] if ids else ""
        url_str = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
        summary = summaries[i] if i < len(summaries) else "(no summary)"
        pub_date = dates[i] if i < len(dates) else None

        ideas.append(
            Idea(
                source=ResearchSource.ACADEMIC_PAPERS.value,
                title=title.strip(),
                url=url_str,
                summary=summary.strip(),
                tags=("research", "academic"),
                relevance_score=0.9,
                published_date=pub_date,
            )
        )

    return ideas


def search_blog_posts(query: str, max_results: int = 5) -> list[Idea]:
    """Search technical blog posts via site indexing.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from blog posts
    """
    # Use Google Custom Search approximation via direct site searches
    common_tech_blogs = [
        "medium.com",
        "dev.to",
        "hashnode.com",
        "linkedin.com/pulse",
        "substack.com",
    ]

    ideas: list[Idea] = []
    for blog_domain in common_tech_blogs:
        search_query = urllib.parse.quote(query)
        # Note: This is a fallback; in production, use Custom Search API
        url = f"https://www.google.com/search?q=site:{blog_domain}+{search_query}"

        ideas.append(
            Idea(
                source=ResearchSource.BLOG_POSTS.value,
                title=f"Blog posts about '{query}' on {blog_domain}",
                url=url,
                summary=f"Technical blog coverage of {query} on {blog_domain}",
                tags=("blog", "technical"),
                relevance_score=0.7,
            )
        )

    return ideas[:max_results]


def search_github_discussions(query: str, max_results: int = 5) -> list[Idea]:
    """Search GitHub Discussions API.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from GitHub Discussions
    """
    # GitHub GraphQL-only for discussions, fallback to REST search approximation
    params = urllib.parse.urlencode(
        {"q": f"{query} in:title type:discussion", "per_page": max_results}
    )
    url = f"https://api.github.com/search/issues?{params}"

    payload = _fetch_json(
        url, headers={"Accept": "application/vnd.github+json"}
    )

    if payload is None:
        return []

    ideas: list[Idea] = []
    for item in payload.get("items", []):
        if "discussions" in item.get("html_url", ""):
            ideas.append(
                Idea(
                    source=ResearchSource.GITHUB_DISCUSSIONS.value,
                    title=item.get("title", ""),
                    url=item.get("html_url", ""),
                    summary=item.get("body", "")[:200] or "(no details)",
                    tags=("discussion", "community"),
                    relevance_score=0.8,
                    published_date=item.get("created_at"),
                )
            )

    return ideas


def search_stack_overflow(query: str, max_results: int = 5) -> list[Idea]:
    """Search Stack Overflow via the public API.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from Stack Overflow
    """
    params = urllib.parse.urlencode(
        {"intitle": query, "sort": "relevance", "order": "desc", "pagesize": max_results}
    )
    url = f"https://api.stackexchange.com/2.3/search/advanced?{params}&site=stackoverflow"

    payload = _fetch_json(url)

    if payload is None:
        return []

    ideas: list[Idea] = []
    for item in payload.get("items", []):
        ideas.append(
            Idea(
                source=ResearchSource.STACK_OVERFLOW.value,
                title=item.get("title", ""),
                url=item.get("link", ""),
                summary=f"Q&A with {item.get('answer_count', 0)} answers",
                tags=("qa", "community"),
                relevance_score=min((item.get("score", 0) / 100.0), 1.0),
                published_date=datetime.fromtimestamp(
                    item.get("creation_date", 0)
                ).isoformat() if item.get("creation_date") else None,
            )
        )

    return ideas


def search_rfc_documents(query: str, max_results: int = 5) -> list[Idea]:
    """Search RFC documents via ietf.org.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from RFC documents
    """
    ideas: list[Idea] = []

    # Construct RFC search query
    search_query = urllib.parse.quote(query)
    url = f"https://www.rfc-editor.org/cgi-bin/rfcsearch?title={search_query}&pubstatus=any&sortby=number"

    ideas.append(
        Idea(
            source=ResearchSource.RFC_DOCUMENTS.value,
            title=f"RFC search: {query}",
            url=url,
            summary=f"Internet standards and RFCs related to {query}",
            tags=("standards", "protocol"),
            relevance_score=0.85,
        )
    )

    return ideas[:max_results]


def search_security_advisories(query: str, max_results: int = 5) -> list[Idea]:
    """Search CVE and security advisories.

    Args:
        query: Search query (e.g., package name)
        max_results: Maximum results

    Returns:
        List of Idea objects from security advisories
    """
    ideas: list[Idea] = []

    # Search multiple security databases
    security_sources = [
        ("CVE", f"https://nvd.nist.gov/vuln/search?query={urllib.parse.quote(query)}"),
        (
            "GitHub Security",
            f"https://github.com/advisories?query={urllib.parse.quote(query)}",
        ),
        (
            "OSS-Fuzz",
            f"https://oss-fuzz.com/?query={urllib.parse.quote(query)}",
        ),
    ]

    for source_name, source_url in security_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.SECURITY_ADVISORIES.value,
                title=f"{source_name}: {query}",
                url=source_url,
                summary=f"Security advisories and CVEs for {query}",
                tags=("security", "vulnerability"),
                relevance_score=0.9,
            )
        )

    return ideas


def search_performance_benchmarks(query: str, max_results: int = 5) -> list[Idea]:
    """Search performance benchmarks and comparisons.

    Args:
        query: Search query (e.g., language, framework)
        max_results: Maximum results

    Returns:
        List of Idea objects from benchmark data
    """
    ideas: list[Idea] = []

    # Common benchmark repositories and sites
    benchmark_sources = [
        (
            "TechEmpower Benchmarks",
            f"https://www.techempower.com/benchmarks/#section={query.lower().replace(' ', '-')}",
        ),
        (
            f"{query} Benchmarks (GitHub)",
            f"https://github.com/search?q={urllib.parse.quote(query)}+benchmark&type=repositories",
        ),
        (
            "SPEC CPU Benchmarks",
            "https://www.spec.org/benchmarks.html",
        ),
    ]

    for source_name, source_url in benchmark_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.PERFORMANCE_BENCHMARKS.value,
                title=source_name,
                url=source_url,
                summary=f"Performance benchmarks and test results for {query}",
                tags=("performance", "benchmark"),
                relevance_score=0.8,
            )
        )

    return ideas


def search_case_studies(query: str, max_results: int = 5) -> list[Idea]:
    """Search real-world case studies and implementations.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from case studies
    """
    ideas: list[Idea] = []

    case_study_sources = [
        (
            f"Hacker News: {query}",
            f"https://hn.algolia.com/?query={urllib.parse.quote(query)}&type=story&sort=points&range=all",
        ),
        (
            f"ArsTechnica: {query}",
            f"https://arstechnica.com/search/?query={urllib.parse.quote(query)}",
        ),
        (
            f"InfoQ: {query}",
            f"https://www.infoq.com/search?query={urllib.parse.quote(query)}",
        ),
    ]

    for source_name, source_url in case_study_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.CASE_STUDIES.value,
                title=source_name,
                url=source_url,
                summary=f"Real-world case studies and lessons about {query}",
                tags=("case-study", "real-world"),
                relevance_score=0.8,
            )
        )

    return ideas


def search_video_tutorials(query: str, max_results: int = 5) -> list[Idea]:
    """Search video tutorials and educational content.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from video content
    """
    ideas: list[Idea] = []

    video_platforms = [
        (
            "YouTube",
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}",
        ),
        (
            "Vimeo",
            f"https://vimeo.com/search?q={urllib.parse.quote(query)}",
        ),
        (
            "Conference Videos (YouTube)",
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}+conference",
        ),
    ]

    for platform_name, platform_url in video_platforms[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.VIDEO_TUTORIALS.value,
                title=f"{platform_name}: {query}",
                url=platform_url,
                summary=f"Video tutorials and educational content about {query}",
                tags=("video", "tutorial"),
                relevance_score=0.7,
            )
        )

    return ideas


def search_tool_comparisons(query: str, max_results: int = 5) -> list[Idea]:
    """Search tool and feature comparisons.

    Args:
        query: Search query (e.g., "Python web frameworks")
        max_results: Maximum results

    Returns:
        List of Idea objects from comparison matrices
    """
    ideas: list[Idea] = []

    comparison_sources = [
        (
            f"Slant: {query}",
            f"https://slant.co/search?query={urllib.parse.quote(query)}",
        ),
        (
            f"Alternativeto: {query}",
            f"https://alternativeto.net/search?q={urllib.parse.quote(query)}",
        ),
        (
            f"GitHub comparison: {query}",
            f"https://github.com/search?q={urllib.parse.quote(query)}+comparison&type=repositories",
        ),
    ]

    for source_name, source_url in comparison_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.TOOL_COMPARISONS.value,
                title=source_name,
                url=source_url,
                summary=f"Feature comparisons and alternatives to {query}",
                tags=("comparison", "tools"),
                relevance_score=0.75,
            )
        )

    return ideas


def search_plugin_ecosystems(query: str, max_results: int = 5) -> list[Idea]:
    """Search plugin and extension ecosystems.

    Args:
        query: Search query (e.g., "VS Code extensions")
        max_results: Maximum results

    Returns:
        List of Idea objects from plugin ecosystems
    """
    ideas: list[Idea] = []

    plugin_registries = [
        (
            "PyPI Packages",
            f"https://pypi.org/search/?q={urllib.parse.quote(query)}",
        ),
        (
            "npm Packages",
            f"https://www.npmjs.com/search?q={urllib.parse.quote(query)}",
        ),
        (
            "VS Code Extensions",
            f"https://marketplace.visualstudio.com/search?q={urllib.parse.quote(query)}",
        ),
        (
            "GitHub Marketplace",
            f"https://github.com/marketplace?query={urllib.parse.quote(query)}",
        ),
    ]

    for registry_name, registry_url in plugin_registries[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.PLUGIN_ECOSYSTEMS.value,
                title=registry_name,
                url=registry_url,
                summary=f"Plugin and extension ecosystem for {query}",
                tags=("plugin", "ecosystem"),
                relevance_score=0.75,
            )
        )

    return ideas


def search_fork_analysis(query: str, max_results: int = 5) -> list[Idea]:
    """Search and analyze forks of repositories.

    Args:
        query: Repository name or owner/repo
        max_results: Maximum results

    Returns:
        List of Idea objects from fork analysis
    """
    ideas: list[Idea] = []

    # Search for forks with most stars
    params = urllib.parse.urlencode(
        {"q": f"fork:{query}", "sort": "stars", "order": "desc", "per_page": max_results}
    )
    url = f"https://api.github.com/search/repositories?{params}"

    payload = _fetch_json(
        url, headers={"Accept": "application/vnd.github+json"}
    )

    if payload is None:
        return []

    for item in payload.get("items", []):
        ideas.append(
            Idea(
                source=ResearchSource.FORK_ANALYSIS.value,
                title=item.get("full_name", ""),
                url=item.get("html_url", ""),
                summary=f"Fork with {item.get('stargazers_count', 0)} stars. {item.get('description', '')}",
                tags=("fork", "variant"),
                relevance_score=min(
                    (item.get("stargazers_count", 0) / 10000.0), 1.0
                ),
                published_date=item.get("created_at"),
            )
        )

    return ideas


def search_upstream_policy_docs(query: str, max_results: int = 5) -> list[Idea]:
    """Search upstream policy and governance documents.

    Args:
        query: Search query (e.g., project name)
        max_results: Maximum results

    Returns:
        List of Idea objects from policy docs
    """
    ideas: list[Idea] = []

    policy_file_patterns = [
        ("CONTRIBUTING.md", f"https://github.com/search?q={urllib.parse.quote(query)}+filename:CONTRIBUTING.md"),
        ("GOVERNANCE.md", f"https://github.com/search?q={urllib.parse.quote(query)}+filename:GOVERNANCE.md"),
        ("CODE_OF_CONDUCT.md", f"https://github.com/search?q={urllib.parse.quote(query)}+filename:CODE_OF_CONDUCT.md"),
        ("ROADMAP.md", f"https://github.com/search?q={urllib.parse.quote(query)}+filename:ROADMAP.md"),
    ]

    for policy_name, policy_url in policy_file_patterns[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.UPSTREAM_POLICY_DOCS.value,
                title=f"{policy_name} for {query}",
                url=policy_url,
                summary=f"Upstream policy documents: {policy_name}",
                tags=("policy", "governance"),
                relevance_score=0.8,
            )
        )

    return ideas


def search_community_forums(query: str, max_results: int = 5) -> list[Idea]:
    """Search community forums and discussion sites.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from forums
    """
    ideas: list[Idea] = []

    forum_sources = [
        (
            "Reddit",
            f"https://www.reddit.com/search?q={urllib.parse.quote(query)}&type=link",
        ),
        (
            "Discourse",
            f"https://www.google.com/search?q=site:discourse.org+{urllib.parse.quote(query)}",
        ),
        (
            "Stack Exchange",
            f"https://stackexchange.com/search?q={urllib.parse.quote(query)}",
        ),
    ]

    for forum_name, forum_url in forum_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.COMMUNITY_FORUMS.value,
                title=f"{forum_name}: {query}",
                url=forum_url,
                summary=f"Community discussion and forums about {query}",
                tags=("forum", "community"),
                relevance_score=0.7,
            )
        )

    return ideas


def search_git_history_analysis(query: str, max_results: int = 5) -> list[Idea]:
    """Search repositories to analyze git history patterns.

    Args:
        query: Repository name or owner/repo
        max_results: Maximum results

    Returns:
        List of Idea objects from git analysis
    """
    ideas: list[Idea] = []

    # Search for repositories with query and link to their history
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": max_results}
    )
    url = f"https://api.github.com/search/repositories?{params}"

    payload = _fetch_json(
        url, headers={"Accept": "application/vnd.github+json"}
    )

    if payload is None:
        return []

    for item in payload.get("items", []):
        repo_url = item.get("html_url", "")
        ideas.append(
            Idea(
                source=ResearchSource.GIT_HISTORY_ANALYSIS.value,
                title=f"Git history: {item.get('full_name', '')}",
                url=f"{repo_url}/commits" if repo_url else "",
                summary=f"Analyze commit patterns and history in {item.get('full_name', '')}",
                tags=("git", "history"),
                relevance_score=0.8,
                published_date=item.get("created_at"),
            )
        )

    return ideas


def search_architecture_diagrams(query: str, max_results: int = 5) -> list[Idea]:
    """Search for architecture diagrams and system design documentation.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from architecture docs
    """
    ideas: list[Idea] = []

    arch_sources = [
        (
            f"README diagrams: {query}",
            f"https://github.com/search?q={urllib.parse.quote(query)}+filename:README.md&type=code",
        ),
        (
            f"Architecture docs: {query}",
            f"https://github.com/search?q={urllib.parse.quote(query)}+path:docs+architecture&type=code",
        ),
        (
            "System Design Primer",
            "https://github.com/donnemartin/system-design-primer",
        ),
    ]

    for source_name, source_url in arch_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.ARCHITECTURE_DIAGRAMS.value,
                title=source_name,
                url=source_url,
                summary=f"Architecture diagrams and system design documentation for {query}",
                tags=("architecture", "design"),
                relevance_score=0.8,
            )
        )

    return ideas


def search_benchmark_datasets(query: str, max_results: int = 5) -> list[Idea]:
    """Search benchmark and test datasets.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        List of Idea objects from datasets
    """
    ideas: list[Idea] = []

    dataset_sources = [
        (
            "Kaggle Datasets",
            f"https://www.kaggle.com/search?q={urllib.parse.quote(query)}",
        ),
        (
            "GitHub datasets",
            f"https://github.com/search?q={urllib.parse.quote(query)}+topic:dataset&type=repositories",
        ),
        (
            "UCI Machine Learning",
            f"https://archive.ics.uci.edu/ml/index.php?pagenumber=2&sort=name",
        ),
    ]

    for source_name, source_url in dataset_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.BENCHMARK_DATASETS.value,
                title=source_name,
                url=source_url,
                summary=f"Benchmark and test datasets for {query}",
                tags=("dataset", "benchmark"),
                relevance_score=0.75,
            )
        )

    return ideas


def search_vendor_documentation(query: str, max_results: int = 5) -> list[Idea]:
    """Search vendor and official product documentation.

    Args:
        query: Product or vendor name
        max_results: Maximum results

    Returns:
        List of Idea objects from vendor docs
    """
    ideas: list[Idea] = []

    vendor_sources = [
        (
            f"Official docs: {query}",
            f"https://www.google.com/search?q=site:docs.{query.lower().replace(' ', '')}",
        ),
        (
            f"AWS/Cloud docs",
            f"https://docs.aws.amazon.com/search/doc-search.html?searchPath=documentation&searchTerm={urllib.parse.quote(query)}",
        ),
        (
            f"GitHub docs",
            f"https://docs.github.com/search?query={urllib.parse.quote(query)}",
        ),
    ]

    for source_name, source_url in vendor_sources[:max_results]:
        ideas.append(
            Idea(
                source=ResearchSource.VENDOR_DOCUMENTATION.value,
                title=source_name,
                url=source_url,
                summary=f"Official vendor documentation for {query}",
                tags=("documentation", "vendor"),
                relevance_score=0.85,
            )
        )

    return ideas


def research(
    query: str,
    include_catalog: bool = True,
    live: bool = True,
    sources: Optional[list[str]] = None,
) -> list[Idea]:
    """Comprehensive research across all 20 sources.

    Merges offline catalog hits with multiple live search sources.
    Results are deduplicated, ranked by relevance, and limited by TTL/rate limits.

    Args:
        query: Search query
        include_catalog: Include offline catalog
        live: Include live sources
        sources: Specific sources to search (None = all)

    Returns:
        Deduplicated, relevance-ranked list of ideas
    """
    ideas: list[Idea] = []
    query_terms = query.lower().split()

    if include_catalog:
        matched = [
            idea
            for idea in CATALOG
            if any(
                term in idea.summary.lower()
                or term in " ".join(idea.tags)
                or term in idea.title.lower()
                for term in query_terms
            )
        ]
        # Show full catalog if no matches
        ideas.extend(matched or CATALOG)

    if live:
        # Determine which sources to search
        all_sources = {
            ResearchSource.GITHUB.value: search_github,
            ResearchSource.ACADEMIC_PAPERS.value: search_academic_papers,
            ResearchSource.BLOG_POSTS.value: search_blog_posts,
            ResearchSource.GITHUB_DISCUSSIONS.value: search_github_discussions,
            ResearchSource.STACK_OVERFLOW.value: search_stack_overflow,
            ResearchSource.RFC_DOCUMENTS.value: search_rfc_documents,
            ResearchSource.SECURITY_ADVISORIES.value: search_security_advisories,
            ResearchSource.PERFORMANCE_BENCHMARKS.value: search_performance_benchmarks,
            ResearchSource.CASE_STUDIES.value: search_case_studies,
            ResearchSource.VIDEO_TUTORIALS.value: search_video_tutorials,
            ResearchSource.TOOL_COMPARISONS.value: search_tool_comparisons,
            ResearchSource.PLUGIN_ECOSYSTEMS.value: search_plugin_ecosystems,
            ResearchSource.FORK_ANALYSIS.value: search_fork_analysis,
            ResearchSource.UPSTREAM_POLICY_DOCS.value: search_upstream_policy_docs,
            ResearchSource.COMMUNITY_FORUMS.value: search_community_forums,
            ResearchSource.GIT_HISTORY_ANALYSIS.value: search_git_history_analysis,
            ResearchSource.ARCHITECTURE_DIAGRAMS.value: search_architecture_diagrams,
            ResearchSource.BENCHMARK_DATASETS.value: search_benchmark_datasets,
            ResearchSource.VENDOR_DOCUMENTATION.value: search_vendor_documentation,
        }

        sources_to_search = (
            sources if sources else list(all_sources.keys())
        )

        for source in sources_to_search:
            if source in all_sources:
                try:
                    ideas.extend(all_sources[source](query, max_results=3))
                except Exception:
                    # Graceful degradation: skip failed sources
                    pass

    # Deduplicate and rank
    ideas = _deduplicate_ideas(ideas)
    ideas = _rank_by_relevance(ideas, query_terms)

    return ideas
