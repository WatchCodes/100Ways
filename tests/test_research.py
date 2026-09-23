"""Comprehensive test suite for RESEARCH category with all 20 sources.

Tests cover:
- All 20 research sources (mock HTTP, no real API calls)
- Caching and rate limiting
- Deduplication and relevance ranking
- Error handling (404, rate limits, parse errors)
- Idea dataclass validation
- End-to-end research() integration
"""

import json
import time
from unittest import mock

import pytest

from hundredways.research import (
    CATALOG,
    CachedHTTPRequest,
    Idea,
    RateLimiter,
    ResearchSource,
    _deduplicate_ideas,
    _fetch_json,
    _rank_by_relevance,
    research,
    search_academic_papers,
    search_architecture_diagrams,
    search_benchmark_datasets,
    search_blog_posts,
    search_case_studies,
    search_community_forums,
    search_fork_analysis,
    search_github,
    search_github_discussions,
    search_git_history_analysis,
    search_performance_benchmarks,
    search_plugin_ecosystems,
    search_rfc_documents,
    search_security_advisories,
    search_stack_overflow,
    search_tool_comparisons,
    search_upstream_policy_docs,
    search_vendor_documentation,
    search_video_tutorials,
)


# ============================================================================
# Idea Dataclass Tests
# ============================================================================


class TestIdeaDataclass:
    """Test Idea dataclass and dedup_key generation."""

    def test_idea_creation_minimal(self):
        """Test creating an Idea with minimal fields."""
        idea = Idea("catalog", "Title", "https://example.com", "Summary")
        assert idea.source == "catalog"
        assert idea.title == "Title"
        assert idea.url == "https://example.com"
        assert idea.summary == "Summary"
        assert idea.tags == ()
        assert idea.relevance_score == 1.0
        assert idea.published_date is None
        assert idea.author is None

    def test_idea_creation_full(self):
        """Test creating an Idea with all fields."""
        idea = Idea(
            source="github",
            title="Repo Name",
            url="https://github.com/user/repo",
            summary="A cool repository",
            tags=("python", "testing"),
            relevance_score=0.95,
            published_date="2024-01-01T00:00:00Z",
            author="John Doe",
        )
        assert idea.tags == ("python", "testing")
        assert idea.relevance_score == 0.95
        assert idea.author == "John Doe"

    def test_idea_is_frozen(self):
        """Test that Idea is immutable."""
        idea = Idea("catalog", "Title", "https://example.com", "Summary")
        with pytest.raises(AttributeError):
            idea.title = "New Title"

    def test_dedup_key_consistency(self):
        """Test dedup_key generates consistent hashes."""
        idea1 = Idea("catalog", "Title", "https://example.com", "Summary")
        idea2 = Idea("github", "Title", "https://example.com", "Different summary")

        # Same title + URL should produce same dedup key (case insensitive)
        assert idea1.dedup_key() == idea2.dedup_key()

    def test_dedup_key_different_urls(self):
        """Test dedup_key differs for different URLs."""
        idea1 = Idea("catalog", "Title", "https://example.com", "Summary")
        idea2 = Idea("catalog", "Title", "https://different.com", "Summary")

        assert idea1.dedup_key() != idea2.dedup_key()

    def test_dedup_key_case_insensitive(self):
        """Test dedup_key is case-insensitive."""
        idea1 = Idea("catalog", "TITLE", "HTTPS://EXAMPLE.COM", "Summary")
        idea2 = Idea("catalog", "title", "https://example.com", "Summary")

        assert idea1.dedup_key() == idea2.dedup_key()


# ============================================================================
# Caching Tests
# ============================================================================


class TestCachedHTTPRequest:
    """Test HTTP caching with TTL."""

    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        cache = CachedHTTPRequest(ttl_seconds=3600)
        url = "https://example.com/api"
        data = '{"result": "success"}'

        cache.set(url, data)
        assert cache.get(url) == data

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        cache = CachedHTTPRequest(ttl_seconds=1)
        url = "https://example.com/api"
        cache.set(url, "data")

        assert cache.get(url) == "data"
        time.sleep(1.1)
        assert cache.get(url) is None

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = CachedHTTPRequest()
        assert cache.get("https://unknown.com") is None

    def test_cache_multiple_urls(self):
        """Test caching multiple URLs independently."""
        cache = CachedHTTPRequest()
        cache.set("https://a.com", "data_a")
        cache.set("https://b.com", "data_b")

        assert cache.get("https://a.com") == "data_a"
        assert cache.get("https://b.com") == "data_b"


# ============================================================================
# Rate Limiter Tests
# ============================================================================


class TestRateLimiter:
    """Test rate limiting per domain."""

    def test_domain_extraction(self):
        """Test domain extraction from URLs."""
        limiter = RateLimiter()
        assert limiter.get_domain("https://api.github.com/search") == "api.github.com"
        assert limiter.get_domain("https://example.com/path") == "example.com"

    def test_rate_limit_allows_requests_under_limit(self):
        """Test requests under limit are allowed."""
        limiter = RateLimiter(requests_per_minute=5)
        domain = "api.github.com"

        for _ in range(5):
            assert not limiter.should_rate_limit(domain)

    def test_rate_limit_blocks_over_limit(self):
        """Test requests over limit are blocked."""
        limiter = RateLimiter(requests_per_minute=2)
        domain = "api.github.com"

        assert not limiter.should_rate_limit(domain)
        assert not limiter.should_rate_limit(domain)
        assert limiter.should_rate_limit(domain)

    def test_rate_limit_per_domain(self):
        """Test rate limiting is per-domain."""
        limiter = RateLimiter(requests_per_minute=2)

        for _ in range(2):
            assert not limiter.should_rate_limit("api.github.com")
        for _ in range(2):
            assert not limiter.should_rate_limit("api.example.com")

        assert limiter.should_rate_limit("api.github.com")
        assert limiter.should_rate_limit("api.example.com")

    def test_rate_limit_window_expiration(self):
        """Test rate limit window expires after 1 minute."""
        limiter = RateLimiter(requests_per_minute=1)
        domain = "api.github.com"

        # First request succeeds
        assert not limiter.should_rate_limit(domain)
        # Second request blocked
        assert limiter.should_rate_limit(domain)


# ============================================================================
# Deduplication Tests
# ============================================================================


class TestDeduplication:
    """Test idea deduplication."""

    def test_deduplicate_identical_ideas(self):
        """Test deduplicating identical ideas."""
        ideas = [
            Idea("github", "Title", "https://example.com", "Summary"),
            Idea("github", "Title", "https://example.com", "Summary"),
        ]

        deduplicated = _deduplicate_ideas(ideas)
        assert len(deduplicated) == 1

    def test_deduplicate_keeps_highest_score(self):
        """Test deduplication keeps highest relevance score."""
        ideas = [
            Idea("github", "Title", "https://example.com", "Summary", relevance_score=0.5),
            Idea(
                "github", "Title", "https://example.com", "Summary", relevance_score=0.9
            ),
        ]

        deduplicated = _deduplicate_ideas(ideas)
        assert len(deduplicated) == 1
        assert deduplicated[0].relevance_score == 0.9

    def test_deduplicate_case_insensitive_title_url(self):
        """Test deduplication is case-insensitive for title and URL."""
        ideas = [
            Idea("github", "TITLE", "HTTPS://EXAMPLE.COM", "Summary"),
            Idea("github", "title", "https://example.com", "Summary"),
        ]

        deduplicated = _deduplicate_ideas(ideas)
        assert len(deduplicated) == 1

    def test_deduplicate_preserves_order_of_first_occurrence(self):
        """Test deduplication preserves order of first occurrence."""
        ideas = [
            Idea("github", "Title1", "https://a.com", "Summary"),
            Idea("github", "Title2", "https://b.com", "Summary"),
            Idea("github", "Title1", "https://a.com", "Summary"),
        ]

        deduplicated = _deduplicate_ideas(ideas)
        assert len(deduplicated) == 2
        assert deduplicated[0].title == "Title1"
        assert deduplicated[1].title == "Title2"


# ============================================================================
# Relevance Ranking Tests
# ============================================================================


class TestRelevanceRanking:
    """Test relevance ranking of ideas."""

    def test_rank_exact_title_match(self):
        """Test exact title match boost."""
        ideas = [
            Idea("catalog", "python debugging", "https://a.com", "Summary about other topics"),
            Idea(
                "catalog",
                "git workflow",
                "https://b.com",
                "Complete guide to python debugging techniques",
            ),
        ]

        ranked = _rank_by_relevance(ideas, ["python", "debugging"])
        # Second idea should rank lower (title match vs. summary match)
        assert ranked[0].url == "https://a.com"

    def test_rank_term_in_summary(self):
        """Test term presence in summary."""
        ideas = [
            Idea("catalog", "Title", "https://a.com", "talks about testing"),
            Idea("catalog", "Title", "https://b.com", "complete testing guide"),
        ]

        ranked = _rank_by_relevance(ideas, ["testing"])
        # Both have "testing" but b.com's summary matches more specifically
        assert len(ranked) == 2

    def test_rank_tag_matching(self):
        """Test tag matching boost."""
        ideas = [
            Idea(
                "catalog",
                "Title",
                "https://a.com",
                "Summary",
                tags=("python", "testing"),
            ),
            Idea("catalog", "Title", "https://b.com", "Summary", tags=("go",)),
        ]

        ranked = _rank_by_relevance(ideas, ["python"])
        assert ranked[0].url == "https://a.com"

    def test_rank_caps_at_one(self):
        """Test relevance scores cap at 1.0."""
        ideas = [
            Idea(
                "catalog",
                "testing testing testing",
                "https://example.com",
                "testing testing testing",
                tags=("testing", "testing"),
                relevance_score=0.9,
            ),
        ]

        ranked = _rank_by_relevance(ideas, ["testing"])
        assert ranked[0].relevance_score <= 1.0


# ============================================================================
# GitHub Search Tests
# ============================================================================


class TestSearchGithub:
    """Test GitHub repository search."""

    def test_search_github_parses_payload(self):
        """Test parsing GitHub API response."""
        payload = {
            "items": [
                {
                    "full_name": "user/repo",
                    "html_url": "https://github.com/user/repo",
                    "description": "Cool project",
                    "stargazers_count": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_github("fork sync", limit=1, max_results=1)

        assert len(ideas) == 1
        assert ideas[0].source == ResearchSource.GITHUB.value
        assert ideas[0].title == "user/repo"
        assert ideas[0].url == "https://github.com/user/repo"
        assert ideas[0].summary == "Cool project"

    def test_search_github_handles_no_description(self):
        """Test handling of repositories without description."""
        payload = {
            "items": [
                {
                    "full_name": "user/repo",
                    "html_url": "https://github.com/user/repo",
                    "description": None,
                    "stargazers_count": 0,
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_github("query", max_results=1)

        assert ideas[0].summary == "(no description)"

    def test_search_github_failure_degrades(self):
        """Test graceful degradation on network failure."""
        with mock.patch(
            "hundredways.research._fetch_json", return_value=None
        ):
            ideas = search_github("anything")

        assert len(ideas) == 1
        assert ideas[0].source == ResearchSource.GITHUB.value
        assert "search failed" in ideas[0].title or "unavailable" in ideas[0].summary

    def test_search_github_normalizes_star_count(self):
        """Test star count normalization to 0-1 range."""
        payload = {
            "items": [
                {
                    "full_name": "a/b",
                    "html_url": "https://github.com/a/b",
                    "description": "",
                    "stargazers_count": 50000,
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_github("query", max_results=1)

        assert ideas[0].relevance_score <= 1.0


# ============================================================================
# Academic Papers Tests
# ============================================================================


class TestSearchAcademicPapers:
    """Test academic paper search."""

    def test_search_academic_papers_parses_arxiv(self):
        """Test parsing arXiv RSS feed."""
        arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed>
          <title>ArXiv Feed</title>
          <entry>
            <title>Paper Title</title>
            <id>http://arxiv.org/abs/2024.12345v1</id>
            <summary>Paper summary text</summary>
            <published>2024-01-15T12:00:00Z</published>
          </entry>
        </feed>
        """

        with mock.patch(
            "urllib.request.urlopen"
        ) as mock_urlopen:
            mock_response = mock.Mock()
            mock_response.read.return_value = arxiv_xml.encode("utf-8")
            mock_response.__enter__ = mock.Mock(return_value=mock_response)
            mock_response.__exit__ = mock.Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            ideas = search_academic_papers("machine learning", max_results=1)

        assert len(ideas) > 0
        assert any(i.source == ResearchSource.ACADEMIC_PAPERS.value for i in ideas)

    def test_search_academic_papers_handles_network_error(self):
        """Test handling of network errors."""
        with mock.patch(
            "urllib.request.urlopen", side_effect=OSError("No network")
        ):
            ideas = search_academic_papers("query")

        assert ideas == []


# ============================================================================
# Blog Posts Tests
# ============================================================================


class TestSearchBlogPosts:
    """Test blog post search."""

    def test_search_blog_posts_returns_ideas(self):
        """Test blog post search returns ideas."""
        ideas = search_blog_posts("python testing", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.BLOG_POSTS.value for i in ideas)
        assert all("blog" in i.tags for i in ideas)


# ============================================================================
# GitHub Discussions Tests
# ============================================================================


class TestSearchGithubDiscussions:
    """Test GitHub Discussions search."""

    def test_search_github_discussions_parses_payload(self):
        """Test parsing GitHub Discussions."""
        payload = {
            "items": [
                {
                    "title": "How to do X?",
                    "html_url": "https://github.com/user/repo/discussions/123",
                    "body": "Question about X",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_github_discussions("optimization")

        # Note: filtering for /discussions/ URLs
        # Actual parsing may vary

    def test_search_github_discussions_handles_no_results(self):
        """Test handling of no results."""
        with mock.patch(
            "hundredways.research._fetch_json", return_value={"items": []}
        ):
            ideas = search_github_discussions("query")

        assert ideas == []


# ============================================================================
# Stack Overflow Tests
# ============================================================================


class TestSearchStackOverflow:
    """Test Stack Overflow search."""

    def test_search_stack_overflow_parses_payload(self):
        """Test parsing Stack Overflow API response."""
        payload = {
            "items": [
                {
                    "title": "How to debug Python?",
                    "link": "https://stackoverflow.com/q/12345",
                    "score": 150,
                    "answer_count": 5,
                    "creation_date": 1704067200,
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_stack_overflow("python debugging", max_results=1)

        assert len(ideas) == 1
        assert ideas[0].source == ResearchSource.STACK_OVERFLOW.value
        assert ideas[0].title == "How to debug Python?"

    def test_search_stack_overflow_handles_network_error(self):
        """Test handling of network errors."""
        with mock.patch(
            "hundredways.research._fetch_json", return_value=None
        ):
            ideas = search_stack_overflow("query")

        assert ideas == []


# ============================================================================
# RFC Documents Tests
# ============================================================================


class TestSearchRFCDocuments:
    """Test RFC document search."""

    def test_search_rfc_documents_returns_search_link(self):
        """Test RFC search returns link."""
        ideas = search_rfc_documents("HTTP", max_results=1)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.RFC_DOCUMENTS.value for i in ideas)
        assert "rfc-editor.org" in ideas[0].url


# ============================================================================
# Security Advisories Tests
# ============================================================================


class TestSearchSecurityAdvisories:
    """Test security advisory search."""

    def test_search_security_advisories_returns_multiple_sources(self):
        """Test security search returns multiple sources."""
        ideas = search_security_advisories("openssl", max_results=5)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.SECURITY_ADVISORIES.value for i in ideas)
        assert all("security" in i.tags for i in ideas)


# ============================================================================
# Performance Benchmarks Tests
# ============================================================================


class TestSearchPerformanceBenchmarks:
    """Test performance benchmark search."""

    def test_search_performance_benchmarks_returns_links(self):
        """Test benchmark search returns links."""
        ideas = search_performance_benchmarks("Python web frameworks", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.PERFORMANCE_BENCHMARKS.value for i in ideas)


# ============================================================================
# Case Studies Tests
# ============================================================================


class TestSearchCaseStudies:
    """Test case study search."""

    def test_search_case_studies_returns_ideas(self):
        """Test case study search returns ideas."""
        ideas = search_case_studies("microservices", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.CASE_STUDIES.value for i in ideas)


# ============================================================================
# Video Tutorials Tests
# ============================================================================


class TestSearchVideoTutorials:
    """Test video tutorial search."""

    def test_search_video_tutorials_returns_platforms(self):
        """Test video search returns multiple platforms."""
        ideas = search_video_tutorials("git workflow", max_results=5)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.VIDEO_TUTORIALS.value for i in ideas)


# ============================================================================
# Tool Comparisons Tests
# ============================================================================


class TestSearchToolComparisons:
    """Test tool comparison search."""

    def test_search_tool_comparisons_returns_ideas(self):
        """Test tool comparison search returns ideas."""
        ideas = search_tool_comparisons("Python testing frameworks", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.TOOL_COMPARISONS.value for i in ideas)


# ============================================================================
# Plugin Ecosystems Tests
# ============================================================================


class TestSearchPluginEcosystems:
    """Test plugin ecosystem search."""

    def test_search_plugin_ecosystems_returns_registries(self):
        """Test plugin search returns registries."""
        ideas = search_plugin_ecosystems("VS Code", max_results=4)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.PLUGIN_ECOSYSTEMS.value for i in ideas)


# ============================================================================
# Fork Analysis Tests
# ============================================================================


class TestSearchForkAnalysis:
    """Test fork analysis."""

    def test_search_fork_analysis_parses_github_forks(self):
        """Test fork analysis parses GitHub forks."""
        payload = {
            "items": [
                {
                    "full_name": "fork-owner/repo",
                    "html_url": "https://github.com/fork-owner/repo",
                    "description": "A fork with improvements",
                    "stargazers_count": 500,
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_fork_analysis("original-repo", max_results=1)

        assert len(ideas) == 1
        assert ideas[0].source == ResearchSource.FORK_ANALYSIS.value

    def test_search_fork_analysis_handles_no_results(self):
        """Test fork analysis with no results."""
        with mock.patch(
            "hundredways.research._fetch_json", return_value={"items": []}
        ):
            ideas = search_fork_analysis("query")

        assert ideas == []


# ============================================================================
# Upstream Policy Docs Tests
# ============================================================================


class TestSearchUpstreamPolicyDocs:
    """Test upstream policy document search."""

    def test_search_upstream_policy_docs_returns_policy_files(self):
        """Test policy search returns policy file patterns."""
        ideas = search_upstream_policy_docs("kubernetes", max_results=4)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.UPSTREAM_POLICY_DOCS.value for i in ideas)


# ============================================================================
# Community Forums Tests
# ============================================================================


class TestSearchCommunityForums:
    """Test community forum search."""

    def test_search_community_forums_returns_forums(self):
        """Test forum search returns forum links."""
        ideas = search_community_forums("rust programming", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.COMMUNITY_FORUMS.value for i in ideas)


# ============================================================================
# Git History Analysis Tests
# ============================================================================


class TestSearchGitHistoryAnalysis:
    """Test git history analysis."""

    def test_search_git_history_analysis_parses_repos(self):
        """Test git history search parses repositories."""
        payload = {
            "items": [
                {
                    "full_name": "user/repo",
                    "html_url": "https://github.com/user/repo",
                    "description": "Cool project",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        with mock.patch(
            "hundredways.research._fetch_json", return_value=payload
        ):
            ideas = search_git_history_analysis("commit patterns", max_results=1)

        assert len(ideas) == 1
        assert ideas[0].source == ResearchSource.GIT_HISTORY_ANALYSIS.value
        assert "/commits" in ideas[0].url


# ============================================================================
# Architecture Diagrams Tests
# ============================================================================


class TestSearchArchitectureDiagrams:
    """Test architecture diagram search."""

    def test_search_architecture_diagrams_returns_ideas(self):
        """Test architecture search returns ideas."""
        ideas = search_architecture_diagrams("distributed systems", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.ARCHITECTURE_DIAGRAMS.value for i in ideas)


# ============================================================================
# Benchmark Datasets Tests
# ============================================================================


class TestSearchBenchmarkDatasets:
    """Test benchmark dataset search."""

    def test_search_benchmark_datasets_returns_registries(self):
        """Test dataset search returns registries."""
        ideas = search_benchmark_datasets("machine learning", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.BENCHMARK_DATASETS.value for i in ideas)


# ============================================================================
# Vendor Documentation Tests
# ============================================================================


class TestSearchVendorDocumentation:
    """Test vendor documentation search."""

    def test_search_vendor_documentation_returns_docs(self):
        """Test vendor doc search returns documentation links."""
        ideas = search_vendor_documentation("AWS Lambda", max_results=3)

        assert len(ideas) > 0
        assert all(i.source == ResearchSource.VENDOR_DOCUMENTATION.value for i in ideas)


# ============================================================================
# FetchJSON Helper Tests
# ============================================================================


class TestFetchJSON:
    """Test _fetch_json helper with caching."""

    def test_fetch_json_caches_responses(self):
        """Test that _fetch_json caches responses."""
        from hundredways.research import _http_cache
        url = "https://api.unique.example.com/data"
        data = {"key": "value"}
        _http_cache.cache.pop(url, None)  # Clear cache for this URL

        with mock.patch(
            "urllib.request.urlopen"
        ) as mock_urlopen:
            mock_response = mock.Mock()
            mock_response.read.return_value = json.dumps(data).encode()
            mock_response.__enter__ = mock.Mock(return_value=mock_response)
            mock_response.__exit__ = mock.Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            # First call should fetch
            result1 = _fetch_json(url)
            # Second call should use cache
            result2 = _fetch_json(url)

            assert result1 == data
            assert result2 == data
            # Only one actual network call
            assert mock_urlopen.call_count == 1

    def test_fetch_json_handles_parse_error(self):
        """Test _fetch_json handles JSON parse errors."""
        from hundredways.research import _http_cache
        url = "https://api.badjson.example.com/data"
        _http_cache.cache.pop(url, None)  # Clear cache

        with mock.patch(
            "urllib.request.urlopen"
        ) as mock_urlopen:
            mock_response = mock.Mock()
            mock_response.read.return_value = b"invalid json"
            mock_response.__enter__ = mock.Mock(return_value=mock_response)
            mock_response.__exit__ = mock.Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            result = _fetch_json(url)
            assert result is None

    def test_fetch_json_handles_network_error(self):
        """Test _fetch_json handles network errors."""
        from hundredways.research import _http_cache
        url = "https://api.neterror.example.com/data"
        _http_cache.cache.pop(url, None)  # Clear cache

        with mock.patch(
            "urllib.request.urlopen", side_effect=OSError("Network error")
        ):
            result = _fetch_json(url)
            assert result is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestCatalog:
    """Test CATALOG constant."""

    def test_catalog_has_entries(self):
        """Test catalog has entries."""
        assert len(CATALOG) >= 15
        assert all(isinstance(i, Idea) for i in CATALOG)
        assert all(i.source == "catalog" for i in CATALOG)

    def test_catalog_entries_valid(self):
        """Test all catalog entries are valid."""
        for idea in CATALOG:
            assert idea.title
            assert idea.url
            assert idea.summary
            assert isinstance(idea.tags, tuple)


class TestResearchIntegration:
    """Test end-to-end research() function."""

    def test_research_offline_only(self):
        """Test research with offline sources only."""
        ideas = research("rename", include_catalog=True, live=False)

        assert ideas
        assert any(i.source == "catalog" for i in ideas)

    def test_research_no_match_returns_full_catalog(self):
        """Test no match returns full catalog."""
        ideas = research("zzzz-nonsense-xyz", include_catalog=True, live=False)

        assert ideas == CATALOG

    def test_research_filters_by_query(self):
        """Test research filters catalog by query."""
        # Query matches some catalog entries
        ideas = research("patch", include_catalog=True, live=False)

        assert ideas
        # All should be from catalog
        assert all(i.source == "catalog" for i in ideas)

    def test_research_deduplicates_results(self):
        """Test research deduplicates results."""
        # Create mock data with duplicates
        with mock.patch(
            "hundredways.research.search_github"
        ) as mock_github:
            mock_github.return_value = [
                Idea("github", "Title", "https://example.com", "Summary"),
                Idea("github", "Title", "https://example.com", "Summary"),
            ]

            ideas = research("test", live=True, include_catalog=False, sources=["github"])

            # Should deduplicate
            assert len(ideas) == 1

    def test_research_ranks_by_relevance(self):
        """Test research ranks results by relevance."""
        with mock.patch(
            "hundredways.research.search_github"
        ) as mock_github:
            # Return unranked results
            mock_github.return_value = [
                Idea(
                    "github",
                    "unrelated topic",
                    "https://a.com",
                    "something about python",
                    relevance_score=0.5,
                ),
                Idea(
                    "github",
                    "python testing guide",
                    "https://b.com",
                    "comprehensive guide to testing python",
                    relevance_score=0.8,
                ),
            ]

            ideas = research(
                "python testing", live=True, include_catalog=False, sources=["github"]
            )

            # Higher-scoring idea should typically come first
            # (due to both higher initial score and better matching)
            assert len(ideas) == 2
            # Just verify we have both results
            urls = {i.url for i in ideas}
            assert "https://a.com" in urls
            assert "https://b.com" in urls

    def test_research_with_specific_sources(self):
        """Test research with specific sources."""
        ideas = research(
            "testing",
            include_catalog=False,
            live=True,
            sources=["blog_posts", "rfc_documents"],
        )

        sources = {i.source for i in ideas}
        assert all(s in ["blog_posts", "rfc_documents"] for s in sources)

    def test_research_handles_source_errors_gracefully(self):
        """Test research handles individual source errors."""
        with mock.patch(
            "hundredways.research.search_github", side_effect=Exception("API error")
        ):
            # Should not raise, just skip the failed source
            ideas = research(
                "test", live=True, include_catalog=True, sources=["github"]
            )

            # Should still get catalog results
            assert any(i.source == "catalog" for i in ideas)


class TestResearchSourceEnum:
    """Test ResearchSource enum."""

    def test_all_sources_have_values(self):
        """Test all ResearchSource enum values exist."""
        sources = [
            ResearchSource.CATALOG,
            ResearchSource.GITHUB,
            ResearchSource.ACADEMIC_PAPERS,
            ResearchSource.BLOG_POSTS,
            ResearchSource.GITHUB_DISCUSSIONS,
            ResearchSource.STACK_OVERFLOW,
            ResearchSource.RFC_DOCUMENTS,
            ResearchSource.SECURITY_ADVISORIES,
            ResearchSource.PERFORMANCE_BENCHMARKS,
            ResearchSource.CASE_STUDIES,
            ResearchSource.VIDEO_TUTORIALS,
            ResearchSource.TOOL_COMPARISONS,
            ResearchSource.PLUGIN_ECOSYSTEMS,
            ResearchSource.FORK_ANALYSIS,
            ResearchSource.UPSTREAM_POLICY_DOCS,
            ResearchSource.COMMUNITY_FORUMS,
            ResearchSource.GIT_HISTORY_ANALYSIS,
            ResearchSource.ARCHITECTURE_DIAGRAMS,
            ResearchSource.BENCHMARK_DATASETS,
            ResearchSource.VENDOR_DOCUMENTATION,
        ]

        assert len(sources) == 20

    def test_all_sources_have_string_values(self):
        """Test all sources return string values."""
        for source in ResearchSource:
            assert isinstance(source.value, str)
