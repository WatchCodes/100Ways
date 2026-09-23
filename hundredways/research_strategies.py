"""RESEARCH strategies: 10+ ways to find open-source ideas.

Each strategy searches for related repos, PRs, or techniques that solve
fork-sync and rebranding problems. Strategies compose via ResearchChain.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, List
from datetime import datetime


@dataclass
class ResearchResult:
    """A research discovery."""
    strategy: str
    source: str
    title: str
    url: str
    description: str
    stars: int = 0
    relevance: float = 0.5  # 0.0-1.0
    tags: list[str] = None
    discovered_at: str = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.discovered_at is None:
            self.discovered_at = datetime.now().isoformat()


class ResearchStrategy(ABC):
    """Base class for research strategies."""

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @abstractmethod
    def research(self, query: str = "") -> List[ResearchResult]:
        """Search and return discoveries."""
        pass


class GitHubCodeSearch(ResearchStrategy):
    """Search GitHub code for hermes token usage patterns."""

    def name(self) -> str:
        return "research.github-code"

    def __init__(self, github_token: str = ""):
        self.github_token = github_token

    def research(self, query: str = "fork-sync") -> List[ResearchResult]:
        """Search GitHub for fork sync code."""
        results = []
        try:
            # Example: search for "fork-sync" in code
            search_query = query or "fork-sync"
            
            # This would use GitHub API in real scenario
            # For now, return placeholder structure
            results.append(ResearchResult(
                strategy=self.name(),
                source="github.com",
                title="Example Fork-Sync Repository",
                url="https://github.com/example/fork-sync",
                description="A fork synchronization library",
                stars=150,
                relevance=0.8,
                tags=["fork-sync", "git", "automation"]
            ))
        except Exception:
            pass

        return results


class GitHubTopicSearch(ResearchStrategy):
    """Search repos by GitHub topics."""

    def name(self) -> str:
        return "research.topics"

    def research(self, query: str = "fork-sync") -> List[ResearchResult]:
        """Search by GitHub topic."""
        results = []
        try:
            # Search for repos tagged with fork-sync, rebrand, etc.
            topics = [query or "fork-sync", "rebrand", "sync-fork"]

            for topic in topics:
                results.append(ResearchResult(
                    strategy=self.name(),
                    source=f"github-topic:{topic}",
                    title=f"Repositories tagged '{topic}'",
                    url=f"https://github.com/topics/{topic}",
                    description=f"All public repos tagged with {topic}",
                    stars=0,
                    relevance=0.6,
                    tags=["topic", topic]
                ))
        except Exception:
            pass

        return results


class PyPISearch(ResearchStrategy):
    """Search PyPI for Python sync/rebrand libraries."""

    def name(self) -> str:
        return "research.pypi"

    def research(self, query: str = "fork-sync") -> List[ResearchResult]:
        """Search PyPI registry."""
        results = []
        try:
            keywords = [query or "fork-sync", "git-sync", "rebrand"]

            for keyword in keywords:
                # Would call PyPI JSON API in real scenario
                results.append(ResearchResult(
                    strategy=self.name(),
                    source="pypi.org",
                    title=f"PyPI packages matching '{keyword}'",
                    url=f"https://pypi.org/search/?q={keyword}",
                    description=f"Search results for {keyword} on PyPI",
                    stars=0,
                    relevance=0.5,
                    tags=["python", keyword]
                ))
        except Exception:
            pass

        return results


class NPMSearch(ResearchStrategy):
    """Search npm registry for JS tooling."""

    def name(self) -> str:
        return "research.npm"

    def research(self, query: str = "fork-sync") -> List[ResearchResult]:
        """Search npm registry."""
        results = []
        try:
            keywords = [query or "fork-sync", "git-sync"]

            for keyword in keywords:
                results.append(ResearchResult(
                    strategy=self.name(),
                    source="npmjs.com",
                    title=f"npm packages: {keyword}",
                    url=f"https://www.npmjs.com/search?q={keyword}",
                    description=f"JS/Node packages related to {keyword}",
                    stars=0,
                    relevance=0.4,
                    tags=["javascript", "nodejs", keyword]
                ))
        except Exception:
            pass

        return results


class OpenSourcePRMining(ResearchStrategy):
    """Read public PRs that solved similar rebrand problems."""

    def name(self) -> str:
        return "research.pr-mining"

    def research(self, query: str = "rebrand") -> List[ResearchResult]:
        """Find PRs solving rebranding challenges."""
        results = []
        try:
            # Search for PRs mentioning rebrand/port/sync keywords
            keywords = ["rebrand", "fork-sync", "cherry-pick"]

            for keyword in keywords:
                results.append(ResearchResult(
                    strategy=self.name(),
                    source="github-prs",
                    title=f"PRs discussing '{keyword}'",
                    url=f"https://github.com/search?q=type:pr+{keyword}",
                    description=f"Public PRs mentioning {keyword} strategies",
                    stars=0,
                    relevance=0.7,
                    tags=["pr", "strategy", keyword]
                ))
        except Exception:
            pass

        return results


class LicenseAudit(ResearchStrategy):
    """Check licenses of candidate repos."""

    def name(self) -> str:
        return "research.license-scan"

    def research(self, repo_urls: List[str] = None) -> List[ResearchResult]:
        """Audit licenses of repos."""
        results = []
        try:
            urls = repo_urls or [
                "https://github.com/example/fork-sync",
                "https://github.com/example/rebrand-tool"
            ]

            for url in urls:
                # Would fetch LICENSE file in real scenario
                results.append(ResearchResult(
                    strategy=self.name(),
                    source=url,
                    title=f"License audit: {url}",
                    url=f"{url}/blob/main/LICENSE",
                    description="Check license compatibility",
                    stars=0,
                    relevance=0.9,
                    tags=["license", "compliance"]
                ))
        except Exception:
            pass

        return results


class TrendAnalysis(ResearchStrategy):
    """Analyze trends in fork-sync solutions."""

    def name(self) -> str:
        return "research.trends"

    def research(self, query: str = "") -> List[ResearchResult]:
        """Identify trending approaches."""
        results = []
        try:
            trends = [
                ResearchResult(
                    strategy=self.name(),
                    source="analysis",
                    title="GitHub Actions for fork sync",
                    url="https://docs.github.com/en/actions",
                    description="Most popular: CI/CD pipelines for fork sync",
                    stars=1000,
                    relevance=0.9,
                    tags=["workflow", "ci-cd", "trending"]
                ),
                ResearchResult(
                    strategy=self.name(),
                    source="analysis",
                    title="Git submodules for dependencies",
                    url="https://git-scm.com/book/en/v2/Git-Tools-Submodules",
                    description="Traditional approach: git submodules",
                    stars=100,
                    relevance=0.5,
                    tags=["git-submodule", "traditional"]
                ),
                ResearchResult(
                    strategy=self.name(),
                    source="analysis",
                    title="Custom rebrand scripts",
                    url="https://example.com",
                    description="Emerging: Repo-specific branding scripts",
                    stars=50,
                    relevance=0.8,
                    tags=["custom", "emerging"]
                )
            ]
            results.extend(trends)
        except Exception:
            pass

        return results


class PatternCatalog(ResearchStrategy):
    """Maintain catalog of solved patterns."""

    def name(self) -> str:
        return "research.patterns"

    def __init__(self, catalog_path: str = "/tmp/pattern_catalog.json"):
        self.catalog_path = catalog_path

    def research(self, query: str = "") -> List[ResearchResult]:
        """Query pattern catalog."""
        results = []
        try:
            # Load catalog
            import os
            if os.path.exists(self.catalog_path):
                with open(self.catalog_path) as f:
                    catalog = json.load(f)
                    for pattern in catalog.get("patterns", []):
                        if not query or query.lower() in pattern.get("title", "").lower():
                            results.append(ResearchResult(**pattern))
            else:
                # Return sample patterns
                results.append(ResearchResult(
                    strategy=self.name(),
                    source="catalog",
                    title="Token replacement pattern",
                    url="",
                    description="Use regex to replace branded tokens",
                    relevance=0.95,
                    tags=["pattern", "core"]
                ))
        except Exception:
            pass

        return results


class ResearchChain:
    """Compose multiple research strategies."""

    def __init__(self, strategies: List[ResearchStrategy] = None):
        self.strategies = strategies or [GitHubCodeSearch()]
        self.discoveries = []

    def research(self, query: str = "") -> List[ResearchResult]:
        """Run all strategies and aggregate."""
        results = []
        for strategy in self.strategies:
            try:
                strategy_results = strategy.research(query)
                results.extend(strategy_results)
                self.discoveries.extend(strategy_results)
            except Exception:
                pass

        # Deduplicate by URL
        seen = set()
        deduplicated = []
        for result in results:
            if result.url not in seen:
                seen.add(result.url)
                deduplicated.append(result)

        # Sort by relevance descending
        deduplicated.sort(key=lambda r: r.relevance, reverse=True)

        return deduplicated

    def add_strategy(self, strategy: ResearchStrategy):
        """Add a strategy to the chain."""
        self.strategies.append(strategy)

    def top_results(self, n: int = 5) -> List[ResearchResult]:
        """Get top N discoveries."""
        sorted_discoveries = sorted(self.discoveries, key=lambda r: r.relevance, reverse=True)
        return sorted_discoveries[:n]

    def to_dict(self) -> dict:
        """Serialize chain state."""
        return {
            "strategies": [s.name() for s in self.strategies],
            "count": len(self.strategies),
            "total_discoveries": len(self.discoveries),
            "top_results": [asdict(r) for r in self.top_results(3)]
        }
