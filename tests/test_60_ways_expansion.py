"""Tests for 60+ new expansion strategies."""

import pytest
import tempfile
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# Test DETECT strategies
def test_detect_strategies_import():
    """Test DETECT module imports."""
    from hundredways.detect_strategies import (
        GitFetchPolling, GitRevListPolling, GitHashPolling,
        ReflogPolling, CommitMessageGrep, FileWatchPolling,
        AuthorFilterPolling, DetectChain, DetectEvent
    )
    assert GitFetchPolling is not None


def test_detect_event_creation():
    """Test DetectEvent dataclass."""
    from hundredways.detect_strategies import DetectEvent
    
    event = DetectEvent(
        strategy="detect.poll",
        old_head="abc123",
        new_head="def456",
        commit_count=5,
        timestamp=1234567890.0,
        metadata={"source": "git-fetch"}
    )
    
    assert event.strategy == "detect.poll"
    assert event.commit_count == 5
    assert event.metadata["source"] == "git-fetch"


def test_detect_chain_composition():
    """Test DetectChain composes strategies."""
    from hundredways.detect_strategies import (
        DetectChain, GitFetchPolling, GitRevListPolling
    )
    
    chain = DetectChain([GitFetchPolling(), GitRevListPolling()])
    assert len(chain.strategies) == 2
    
    chain.add_strategy(GitFetchPolling())
    assert len(chain.strategies) == 3
    
    state = chain.to_dict()
    assert state["count"] == 3
    assert "detect.poll" in state["strategies"]


# Test DIFF strategies
def test_diff_strategies_import():
    """Test DIFF module imports."""
    from hundredways.diff_strategies import (
        GitDiffNumstat, GitDiffNameStatus, BlobHashDiff,
        TreeDiff, RangeDiff, SemanticDiff, DiffChain, FileDiff
    )
    assert GitDiffNumstat is not None


def test_file_diff_creation():
    """Test FileDiff dataclass."""
    from hundredways.diff_strategies import FileDiff
    
    diff = FileDiff(
        path="README.md",
        status="modified",
        old_hash="abc123",
        new_hash="def456",
        additions=10,
        deletions=5,
        similarity=0.95,
        diff_type="content"
    )
    
    assert diff.path == "README.md"
    assert diff.additions == 10
    assert diff.similarity == 0.95


def test_diff_result_summary():
    """Test DiffResult with summary."""
    from hundredways.diff_strategies import FileDiff, DiffResult
    
    files = [
        FileDiff(path="a.py", status="modified", additions=5, deletions=2),
        FileDiff(path="b.py", status="added", additions=20, deletions=0),
        FileDiff(path="c.py", status="deleted", additions=0, deletions=10),
    ]
    
    result = DiffResult(
        strategy="diff.numstat",
        old_ref="abc123",
        new_ref="def456",
        files=files,
        summary={
            "files_changed": 3,
            "total_additions": 25,
            "total_deletions": 12
        }
    )
    
    assert result.strategy == "diff.numstat"
    assert len(result.files) == 3
    assert result.summary["total_additions"] == 25


def test_diff_chain_composition():
    """Test DiffChain composes strategies."""
    from hundredways.diff_strategies import (
        DiffChain, GitDiffNumstat, BlobHashDiff
    )
    
    chain = DiffChain([GitDiffNumstat(), BlobHashDiff()])
    assert len(chain.strategies) == 2
    
    chain.add_strategy(GitDiffNumstat())
    assert len(chain.strategies) == 3
    
    state = chain.to_dict()
    assert state["count"] == 3


# Test NOTIFY strategies
def test_notify_strategies_import():
    """Test NOTIFY module imports."""
    from hundredways.notify_strategies import (
        StdoutNotify, JsonLogNotify, EmailNotify,
        WebhookNotify, SlackNotify, DiscordNotify,
        SyslogNotify, FileNotify, PagerDutyNotify,
        NotifyChain, NotifyMessage
    )
    assert StdoutNotify is not None


def test_notify_message_creation():
    """Test NotifyMessage dataclass."""
    from hundredways.notify_strategies import NotifyMessage
    
    msg = NotifyMessage(
        title="Test Alert",
        body="Something happened",
        level="warning",
        metadata={"user": "test"}
    )
    
    assert msg.title == "Test Alert"
    assert msg.level == "warning"
    assert msg.timestamp is not None


def test_stdout_notify():
    """Test StdoutNotify strategy."""
    from hundredways.notify_strategies import StdoutNotify, NotifyMessage
    
    strategy = StdoutNotify()
    assert strategy.name() == "notify.stdout"
    
    msg = NotifyMessage("Test", "Body", "info")
    result = strategy.notify(msg)
    assert result is True


def test_json_log_notify(tmp_path):
    """Test JsonLogNotify strategy."""
    from hundredways.notify_strategies import JsonLogNotify, NotifyMessage
    
    log_file = tmp_path / "test.jsonl"
    strategy = JsonLogNotify(str(log_file))
    
    msg = NotifyMessage("Alert", "Test body", "error")
    result = strategy.notify(msg)
    
    assert result is True
    assert log_file.exists()
    
    # Verify JSON content
    content = log_file.read_text()
    parsed = json.loads(content.strip())
    assert parsed["title"] == "Alert"
    assert parsed["level"] == "error"


def test_notify_chain_composition():
    """Test NotifyChain composes strategies."""
    from hundredways.notify_strategies import (
        NotifyChain, StdoutNotify, JsonLogNotify, NotifyMessage
    )
    
    chain = NotifyChain([StdoutNotify()])
    assert len(chain.strategies) == 1
    
    chain.add_strategy(StdoutNotify())
    assert len(chain.strategies) == 2
    
    msg = NotifyMessage("Test", "Body", "info")
    results = chain.notify(msg)
    assert all(results)
    
    state = chain.to_dict()
    assert state["count"] == 2


def test_notify_filter_by_level():
    """Test filtering notifications by level."""
    from hundredways.notify_strategies import (
        NotifyChain, StdoutNotify, NotifyMessage
    )
    
    chain = NotifyChain([StdoutNotify()])
    error_chain = chain.filter_by_level("error")
    
    assert error_chain is not None
    assert len(error_chain.strategies) > 0


# Test RESEARCH strategies
def test_research_strategies_import():
    """Test RESEARCH module imports."""
    from hundredways.research_strategies import (
        GitHubCodeSearch, GitHubTopicSearch, PyPISearch,
        NPMSearch, OpenSourcePRMining, LicenseAudit,
        TrendAnalysis, PatternCatalog, ResearchChain, ResearchResult
    )
    assert GitHubCodeSearch is not None


def test_research_result_creation():
    """Test ResearchResult dataclass."""
    from hundredways.research_strategies import ResearchResult
    
    result = ResearchResult(
        strategy="research.github-code",
        source="github.com",
        title="Example Repo",
        url="https://github.com/example/repo",
        description="A test repository",
        stars=150,
        relevance=0.8,
        tags=["fork-sync", "git"]
    )
    
    assert result.title == "Example Repo"
    assert result.stars == 150
    assert result.relevance == 0.8
    assert result.discovered_at is not None


def test_github_code_search():
    """Test GitHubCodeSearch strategy."""
    from hundredways.research_strategies import GitHubCodeSearch
    
    strategy = GitHubCodeSearch()
    assert strategy.name() == "research.github-code"
    
    results = strategy.research("fork-sync")
    assert isinstance(results, list)


def test_research_chain_composition():
    """Test ResearchChain composes strategies."""
    from hundredways.research_strategies import (
        ResearchChain, GitHubCodeSearch, PyPISearch
    )
    
    chain = ResearchChain([GitHubCodeSearch(), PyPISearch()])
    assert len(chain.strategies) == 2
    
    chain.add_strategy(GitHubCodeSearch())
    assert len(chain.strategies) == 3


def test_research_deduplication():
    """Test research deduplication by URL."""
    from hundredways.research_strategies import (
        ResearchChain, ResearchResult, GitHubCodeSearch
    )
    
    chain = ResearchChain()
    
    # Manually add duplicate results
    result1 = ResearchResult(
        strategy="test",
        source="test",
        title="Test",
        url="https://example.com",
        description="Test"
    )
    result2 = ResearchResult(
        strategy="test",
        source="test",
        title="Test2",
        url="https://example.com",
        description="Test2"
    )
    
    chain.discoveries = [result1, result2]
    results = chain.research()
    
    # Should deduplicate to 1
    urls = [r.url for r in results]
    assert len(set(urls)) == len(urls)


# Test WATCH strategies
def test_watch_strategies_import():
    """Test WATCH module imports."""
    from hundredways.watch_strategies import (
        RepoHeartbeat, StaleBranchDetection, UpstreamDrift,
        ConflictDetection, FailedGateAlert, DiskSpaceWatch,
        UnpushedCommits, LargeFileDetection, WatchChain, WatchEvent
    )
    assert RepoHeartbeat is not None


def test_watch_event_creation():
    """Test WatchEvent dataclass."""
    from hundredways.watch_strategies import WatchEvent
    
    event = WatchEvent(
        strategy="watch.heartbeat",
        event_type="alert",
        title="Repo unavailable",
        details="Cannot access repo",
        severity=8
    )
    
    assert event.strategy == "watch.heartbeat"
    assert event.severity == 8
    assert event.timestamp is not None


def test_watch_chain_composition():
    """Test WatchChain composes strategies."""
    from hundredways.watch_strategies import WatchChain
    
    chain = WatchChain()
    assert len(chain.strategies) == 0
    
    state = chain.to_dict()
    assert state["count"] == 0


def test_watch_chain_recent_events():
    """Test WatchChain filters recent events."""
    from hundredways.watch_strategies import WatchChain, WatchEvent
    
    chain = WatchChain()
    
    # Add old event
    old_event = WatchEvent(
        strategy="test",
        event_type="info",
        title="Old",
        details="Old event",
        severity=1
    )
    old_event.timestamp = (datetime.now() - timedelta(days=2)).isoformat()
    
    # Add new event
    new_event = WatchEvent(
        strategy="test",
        event_type="info",
        title="New",
        details="New event",
        severity=1
    )
    
    chain.event_history = [old_event, new_event]
    
    recent = chain.get_recent_events(24)
    assert len(recent) == 1
    assert recent[0].title == "New"


def test_watch_alert_summary():
    """Test WatchChain alert summary."""
    from hundredways.watch_strategies import WatchChain, WatchEvent
    
    chain = WatchChain()
    
    chain.event_history = [
        WatchEvent("s1", "alert", "A1", "D1", 8),
        WatchEvent("s2", "alert", "A2", "D2", 9),
        WatchEvent("s3", "warning", "W1", "D3", 5),
    ]
    
    summary = chain.alert_summary()
    assert summary["total_events"] == 3
    assert summary["alerts"] == 2
    assert summary["warnings"] == 1


# Integration test: all modules work together
def test_full_expansion_integration():
    """Test all 5 expansion modules integrate."""
    from hundredways.detect_strategies import DetectChain, GitFetchPolling
    from hundredways.diff_strategies import DiffChain, GitDiffNumstat
    from hundredways.notify_strategies import NotifyChain, StdoutNotify
    from hundredways.research_strategies import ResearchChain, GitHubCodeSearch
    from hundredways.watch_strategies import WatchChain
    
    # Create chains
    detect = DetectChain([GitFetchPolling()])
    diff = DiffChain([GitDiffNumstat()])
    notify = NotifyChain([StdoutNotify()])
    research = ResearchChain([GitHubCodeSearch()])
    watch = WatchChain()
    
    # Verify all compose
    assert detect.to_dict()["count"] == 1
    assert diff.to_dict()["count"] == 1
    assert notify.to_dict()["count"] == 1
    assert research.to_dict()["count"] == 1
    assert watch.to_dict()["count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
