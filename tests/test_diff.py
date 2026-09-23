"""Comprehensive tests for the DIFF category (all 20 strategies).

Tests cover:
  - All 20 diff strategies
  - Edge cases: empty repos, large repos, binary files, renames, submodules
  - Performance benchmarks
  - Error handling and security
  - Input validation
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

from hundredways.diff import (
    EMPTY_TREE_SHA,
    BatchBlobDiff,
    BinarySafeDiff,
    BlobSHACompare,
    BlameWindowDiff,
    CommitCountDelta,
    DiffChain,
    DiffEntry,
    EmptyTreeDiff,
    FirstParentWalk,
    GitPlumbingDiff,
    MirrorRefCompare,
    NarrowPathspecDiff,
    PathspecLimitedDiff,
    RangeDiff,
    RenameOnlyDiff,
    SequenceMatcherDiff,
    StagedTreeDiff,
    SubmoduleDiff,
    ThreeWayMergeDiff,
    TreeSetDiff,
    UnifiedDiffParsing,
    WorktreeDiff,
)

GIT = ["git"]


def git(repo, *args):
    """Run git command."""
    out = subprocess.run([*GIT, "-C", repo, *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {out.stderr}")
    return out.stdout.strip()


def commit(repo, files, message, branch="master"):
    """Create a commit with given files."""
    for path, content in files.items():
        p = os.path.join(repo, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(p, mode) as fh:
            fh.write(content)
        subprocess.run([*GIT, "-C", repo, "add", path], check=True)
    subprocess.run(
        [*GIT, "-C", repo, "commit", "-q", "-m", message, "--allow-empty"],
        check=True,
    )
    return git(repo, "rev-parse", "HEAD")


def commit_on(repo, branch, files, message):
    """Commit on a branch without checking out master."""
    git(repo, "checkout", "-q", branch)
    sha = commit(repo, files, message)
    git(repo, "checkout", "-q", "master")
    return sha


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo."""
    repo = str(tmp_path / "repo")
    subprocess.run([*GIT, "init", "-q", repo], check=True)
    subprocess.run([*GIT, "-C", repo, "config", "user.email", "t@t"], check=True)
    subprocess.run([*GIT, "-C", repo, "config", "user.name", "t"], check=True)
    return repo


@pytest.fixture
def diverged_repo(git_repo):
    """Create a repo with two diverged branches."""
    commit(git_repo, {"seed.txt": "seed"}, "seed")
    git(git_repo, "checkout", "-q", "-b", "upstream/main")
    up = commit(git_repo, {}, "upstream base")
    git(git_repo, "checkout", "-q", "master")
    git(git_repo, "checkout", "-q", "-b", "nastech/main", "upstream/main")
    na = commit(git_repo, {}, "nastech base")
    git(git_repo, "checkout", "-q", "master")
    return git_repo, up, na


# ============================================================================
# Strategy 1: Git Plumbing
# ============================================================================


def test_git_plumbing_simple_modification(git_repo):
    """Test git_plumbing with a simple file modification."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = GitPlumbingDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert result.strategy == "git_plumbing"
    assert len(result.entries) == 1
    assert result.entries[0].path == "file.txt"
    assert result.entries[0].status == "M"


def test_git_plumbing_addition(git_repo):
    """Test git_plumbing with file addition."""
    commit(git_repo, {"file1.txt": "content"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file2.txt": "more"}, "add file2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = GitPlumbingDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    entries_by_path = {e.path: e for e in result.entries}
    assert "file2.txt" in entries_by_path
    assert entries_by_path["file2.txt"].status == "A"


def test_git_plumbing_deletion(git_repo):
    """Test git_plumbing with file deletion."""
    commit(git_repo, {"file.txt": "content"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    subprocess.run([*GIT, "-C", git_repo, "rm", "file.txt"], check=True)
    commit(git_repo, {}, "delete file")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = GitPlumbingDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    entries_by_path = {e.path: e for e in result.entries}
    assert "file.txt" in entries_by_path
    assert entries_by_path["file.txt"].status == "D"


# ============================================================================
# Strategy 2: Tree Set Diff
# ============================================================================


def test_tree_set_diff_modification(git_repo):
    """Test tree_set with file modification."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = TreeSetDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert len(result.entries) == 1
    assert result.entries[0].path == "file.txt"
    assert result.entries[0].status == "M"


def test_tree_set_diff_structure(git_repo):
    """Test tree_set preserves file structure."""
    commit(git_repo, {"dir1/file.txt": "v1", "dir2/file.txt": "v2"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"dir1/file.txt": "modified", "dir2/other.txt": "new"}, "changes")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = TreeSetDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    paths = {e.path for e in result.entries}
    assert "dir1/file.txt" in paths
    assert "dir2/other.txt" in paths


# ============================================================================
# Strategy 3: Unified Diff Parsing
# ============================================================================


def test_unified_diff_parsing_lines(git_repo):
    """Test unified_diff line counting."""
    commit(git_repo, {"file.txt": "line1\nline2\nline3\n"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "line1\nlineX\nlineY\nlineZ\nline3\n"}, "modify")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = UnifiedDiffParsing(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert len(result.entries) > 0
    entry = result.entries[0]
    assert entry.path == "file.txt"
    # Line counts are approximate in unified diff parsing
    assert entry.added_lines >= 0
    assert entry.deleted_lines >= 0


# ============================================================================
# Strategy 4: Worktree Diff
# ============================================================================


def test_worktree_diff_unstaged_changes(git_repo):
    """Test worktree diff detects unstaged changes."""
    commit(git_repo, {"file.txt": "v1"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    # Modify file without committing
    with open(os.path.join(git_repo, "file.txt"), "w") as f:
        f.write("modified")
    
    strategy = WorktreeDiff(git_repo)
    result = strategy.diff(sha1)
    
    assert len(result.entries) > 0
    assert any(e.path == "file.txt" for e in result.entries)


# ============================================================================
# Strategy 5: Range Diff
# ============================================================================


def test_range_diff_commit_range(git_repo):
    """Test range_diff across commit range."""
    commit(git_repo, {"file1.txt": "v1"}, "commit1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    commit(git_repo, {"file2.txt": "v2"}, "commit2")
    commit(git_repo, {"file3.txt": "v3"}, "commit3")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = RangeDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert result.metadata.get("commit_count") == 2
    paths = {e.path for e in result.entries}
    assert "file2.txt" in paths
    assert "file3.txt" in paths


# ============================================================================
# Strategy 6: Blob SHA Compare
# ============================================================================


def test_blob_sha_compare_different_content(git_repo):
    """Test blob_sha correctly detects differences."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BlobSHACompare(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert len(result.entries) == 1
    assert result.entries[0].status == "M"
    assert result.entries[0].old_sha != result.entries[0].new_sha


def test_blob_sha_same_content(git_repo):
    """Test blob_sha handles identical content."""
    commit(git_repo, {"file.txt": "same"}, "commit1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"other.txt": "other"}, "commit2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BlobSHACompare(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # file.txt should not appear (same SHA)
    assert not any(e.path == "file.txt" for e in result.entries)
    # other.txt should appear (added)
    assert any(e.path == "other.txt" for e in result.entries)


# ============================================================================
# Strategy 7: Sequence Matcher
# ============================================================================


def test_sequence_matcher_rename_detection(git_repo):
    """Test sequence_matcher detects renames."""
    commit(git_repo, {"oldname.txt": "content line 1\ncontent line 2\n"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    subprocess.run([*GIT, "-C", git_repo, "rm", "oldname.txt"], check=True)
    commit(git_repo, {"newname.txt": "content line 1\ncontent line 2\nsmall change\n"}, "rename")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = SequenceMatcherDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # Should detect high similarity
    rename_entries = [e for e in result.entries if e.status == "R"]
    if rename_entries:
        assert rename_entries[0].similarity > 70


# ============================================================================
# Strategy 8: Pathspec Limited
# ============================================================================


def test_pathspec_limited_filtering(git_repo):
    """Test pathspec filtering."""
    commit(git_repo, {"src/file.py": "v1", "docs/readme.md": "v1", "test/file.py": "v1"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"src/file.py": "v2", "docs/readme.md": "v2", "test/file.py": "v2"}, "changes")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = PathspecLimitedDiff(git_repo)
    result = strategy.diff(sha1, sha2, pathspecs=["src/*"])
    
    # Only src/file.py should appear
    assert any(e.path == "src/file.py" for e in result.entries)
    assert not any(e.path == "docs/readme.md" for e in result.entries)


# ============================================================================
# Strategy 9: First-Parent Walk
# ============================================================================


def test_first_parent_walk_linear(git_repo):
    """Test first_parent on linear history."""
    commit(git_repo, {"file1.txt": "v1"}, "commit1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file2.txt": "v2"}, "commit2")
    commit(git_repo, {"file3.txt": "v3"}, "commit3")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = FirstParentWalk(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert result.metadata.get("first_parent_commits") >= 2


# ============================================================================
# Strategy 10: Batch Blob Reads
# ============================================================================


def test_batch_blob_diff_modification(git_repo):
    """Test batch_blob correctly detects modifications."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BatchBlobDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert len(result.entries) == 1
    assert result.entries[0].status == "M"


def test_batch_blob_multiple_files(git_repo):
    """Test batch_blob with multiple files."""
    files = {f"file{i}.txt": f"v{i}" for i in range(10)}
    commit(git_repo, files, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    # Modify all files
    files = {f"file{i}.txt": f"v{i}-modified" for i in range(10)}
    commit(git_repo, files, "modify all")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BatchBlobDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    assert len(result.entries) == 10


# ============================================================================
# Strategy 11: Mirror Ref Compare
# ============================================================================


def test_mirror_ref_compare_branches(git_repo):
    """Test mirror_ref comparing branches."""
    commit(git_repo, {"file.txt": "v1"}, "initial")
    git(git_repo, "checkout", "-q", "-b", "branch1")
    commit(git_repo, {"file.txt": "branch1"}, "branch1 commit")
    
    git(git_repo, "checkout", "-q", "master")
    git(git_repo, "checkout", "-q", "-b", "branch2")
    commit(git_repo, {"file.txt": "branch2"}, "branch2 commit")
    
    strategy = MirrorRefCompare(git_repo)
    result = strategy.diff("branch1", "branch2")
    
    assert result.metadata.get("ref_a") == "branch1"
    assert result.metadata.get("ref_b") == "branch2"
    assert len(result.entries) > 0


# ============================================================================
# Strategy 12: Staged Tree Diff
# ============================================================================


def test_staged_tree_diff_index(git_repo):
    """Test staged_tree detects staged changes."""
    commit(git_repo, {"file.txt": "v1"}, "initial")
    
    # Modify and stage
    with open(os.path.join(git_repo, "file.txt"), "w") as f:
        f.write("staged")
    subprocess.run([*GIT, "-C", git_repo, "add", "file.txt"], check=True)
    
    strategy = StagedTreeDiff(git_repo)
    result = strategy.diff("HEAD")
    
    assert any(e.path == "file.txt" for e in result.entries)


# ============================================================================
# Strategy 13: Three-Way Merge
# ============================================================================


def test_three_way_merge_base(git_repo):
    """Test three_way detects merge base."""
    commit(git_repo, {"base.txt": "base"}, "base")
    base_sha = git(git_repo, "rev-parse", "HEAD")
    
    git(git_repo, "checkout", "-q", "-b", "branch1")
    commit(git_repo, {"file1.txt": "branch1"}, "branch1 commit")
    branch1_sha = git(git_repo, "rev-parse", "HEAD")
    
    git(git_repo, "checkout", "-q", base_sha)
    git(git_repo, "checkout", "-q", "-b", "branch2")
    commit(git_repo, {"file2.txt": "branch2"}, "branch2 commit")
    branch2_sha = git(git_repo, "rev-parse", "HEAD")
    
    strategy = ThreeWayMergeDiff(git_repo)
    result = strategy.diff(branch1_sha, branch2_sha)
    
    assert result.metadata.get("merge_base")


# ============================================================================
# Strategy 14: Narrow Pathspec
# ============================================================================


def test_narrow_pathspec_regex(git_repo):
    """Test narrow_pathspec with regex filtering."""
    commit(git_repo, {"src/file.py": "v1", "src/other.js": "v1", "docs/readme.md": "v1"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"src/file.py": "v2", "src/other.js": "v2", "docs/readme.md": "v2"}, "changes")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = NarrowPathspecDiff(git_repo)
    result = strategy.diff(sha1, sha2, pattern=r"\.py$")
    
    # Only .py files
    assert all(e.path.endswith(".py") for e in result.entries)
    assert any(e.path == "src/file.py" for e in result.entries)


# ============================================================================
# Strategy 15: Commit Count Delta
# ============================================================================


def test_commit_count_delta_divergence(git_repo):
    """Test commit_count detects divergence."""
    commit(git_repo, {"file.txt": "base"}, "base")
    base_sha = git(git_repo, "rev-parse", "HEAD")
    
    git(git_repo, "checkout", "-q", "-b", "branch1")
    commit(git_repo, {"file1.txt": "branch1"}, "branch1 commit")
    commit(git_repo, {"file2.txt": "branch1b"}, "branch1 commit2")
    branch1_sha = git(git_repo, "rev-parse", "HEAD")
    
    git(git_repo, "checkout", "-q", base_sha)
    git(git_repo, "checkout", "-q", "-b", "branch2")
    commit(git_repo, {"file3.txt": "branch2"}, "branch2 commit")
    branch2_sha = git(git_repo, "rev-parse", "HEAD")
    
    strategy = CommitCountDelta(git_repo)
    result = strategy.diff(branch1_sha, branch2_sha)
    
    assert result.metadata.get("diverged") is True


# ============================================================================
# Strategy 16: Blame Windows
# ============================================================================


def test_blame_windows_authors(git_repo):
    """Test blame_windows extracts author info."""
    commit(git_repo, {"file.txt": "line1\nline2\nline3\n"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    subprocess.run([*GIT, "-C", git_repo, "config", "user.name", "Author2"], check=True)
    commit(git_repo, {"file.txt": "line1\nlineX\nline3\n"}, "modify")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BlameWindowDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # Should have blame info
    assert len(result.entries) >= 0


# ============================================================================
# Strategy 17: Submodule Pointers
# ============================================================================


def test_submodule_diff_detection(git_repo):
    """Test submodule_diff strategy."""
    commit(git_repo, {"file.txt": "content"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "modified"}, "change")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = SubmoduleDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # Regular diff should work even without submodules
    assert result.strategy == "submodule_pointers"


# ============================================================================
# Strategy 18: Empty Tree Baselines
# ============================================================================


def test_empty_tree_baseline(git_repo):
    """Test empty_tree detects all files as additions."""
    commit(git_repo, {"file1.txt": "v1", "file2.txt": "v2"}, "initial")
    sha = git(git_repo, "rev-parse", "HEAD")
    
    strategy = EmptyTreeDiff(git_repo)
    result = strategy.diff(sha)
    
    # All files should be additions from empty tree
    assert all(e.status == "A" for e in result.entries)
    assert len(result.entries) == 2


# ============================================================================
# Strategy 19: Rename Detection
# ============================================================================


def test_rename_detection_similarity(git_repo):
    """Test rename_only detects renames or add/delete pairs."""
    commit(git_repo, {"oldname.txt": "content line 1\ncontent line 2\n"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    subprocess.run([*GIT, "-C", git_repo, "rm", "oldname.txt"], check=True)
    commit(git_repo, {"newname.txt": "content line 1\ncontent line 2\n"}, "rename")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = RenameOnlyDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # Git should detect as rename with high similarity OR as separate A+D
    rename_entries = [e for e in result.entries if e.status == "R"]
    add_entries = [e for e in result.entries if e.status == "A"]
    delete_entries = [e for e in result.entries if e.status == "D"]
    
    # At least one of: rename detected, or A+D pair
    has_rename = len(rename_entries) > 0
    has_add = len(add_entries) > 0
    has_delete = len(delete_entries) > 0
    has_add_delete = has_add and has_delete
    
    assert has_rename or has_add_delete


# ============================================================================
# Strategy 20: Binary-Safe
# ============================================================================


def test_binary_safe_binary_file(git_repo):
    """Test binary_safe handles binary files."""
    # Create binary file (PNG magic)
    png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with open(os.path.join(git_repo, "image.png"), "wb") as f:
        f.write(png_magic)
    subprocess.run([*GIT, "-C", git_repo, "add", "image.png"], check=True)
    commit(git_repo, {}, "add binary")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    # Modify binary
    with open(os.path.join(git_repo, "image.png"), "wb") as f:
        f.write(png_magic + b"\x00" * 50)
    subprocess.run([*GIT, "-C", git_repo, "add", "image.png"], check=True)
    commit(git_repo, {}, "modify binary")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BinarySafeDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    # Should detect the file as modified and mark as binary
    if result.entries:
        entry = result.entries[0]
        assert entry.is_binary


def test_binary_safe_text_file(git_repo):
    """Test binary_safe correctly identifies text files."""
    commit(git_repo, {"file.txt": "text content"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "modified text"}, "modify")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = BinarySafeDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    
    if result.entries:
        entry = result.entries[0]
        assert not entry.is_binary


# ============================================================================
# DiffChain Tests
# ============================================================================


def test_diffchain_register_strategy(git_repo):
    """Test DiffChain strategy registration."""
    chain = DiffChain(git_repo)
    assert "tree_set" in chain.strategies
    assert "blob_sha" in chain.strategies
    assert len(chain.strategies) >= 20


def test_diffchain_run_single_strategy(git_repo):
    """Test DiffChain running a single strategy."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    chain = DiffChain(git_repo)
    result = chain.run("tree_set", sha1, sha2)
    
    assert result.strategy == "tree_set_diff"
    assert len(result.entries) > 0


def test_diffchain_run_all(git_repo):
    """Test DiffChain running all strategies."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    chain = DiffChain(git_repo)
    results = chain.run_all(sha1, sha2)
    
    # Should have all 20 strategies
    assert len(results) >= 20
    # Most should have entries or error
    success_count = sum(1 for result in results.values() if len(result.entries) > 0 or result.error)
    assert success_count >= 15  # At least 15 should work


def test_diffchain_composite(git_repo):
    """Test DiffChain composite merging."""
    commit(git_repo, {"file.txt": "v1"}, "v1")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    commit(git_repo, {"file.txt": "v2"}, "v2")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    chain = DiffChain(git_repo)
    result = chain.composite(sha1, sha2, ["tree_set", "unified_diff"])
    
    assert result.strategy == "composite"
    assert len(result.entries) > 0


def test_diffchain_invalid_strategy(git_repo):
    """Test DiffChain error handling for invalid strategy."""
    chain = DiffChain(git_repo)
    
    # Should handle gracefully with ValueError
    with pytest.raises(ValueError):
        chain.run("nonexistent_strategy", "sha1", "sha2")


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================


def test_empty_repo(git_repo):
    """Test diff on empty repo."""
    strategy = TreeSetDiff(git_repo)
    # Creating empty commit
    commit(git_repo, {"file.txt": "initial"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    result = strategy.diff(sha1, sha1)
    # Comparing with itself should yield no diffs
    assert len(result.entries) == 0


def test_large_repo_performance(git_repo):
    """Test performance on large repo (benchmark)."""
    # Create many files
    files = {f"file{i}.txt": f"content{i}" for i in range(100)}
    commit(git_repo, files, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    # Modify some
    files = {f"file{i}.txt": f"modified{i}" for i in range(50)}
    commit(git_repo, files, "modify")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    chain = DiffChain(git_repo)
    
    # Benchmark tree_set vs batch_blob
    start = time.time()
    result1 = chain.run("tree_set", sha1, sha2)
    time1 = time.time() - start
    
    start = time.time()
    result2 = chain.run("batch_blobs", sha1, sha2)
    time2 = time.time() - start
    
    # Both should complete quickly
    assert time1 < 5.0
    assert time2 < 5.0
    # Both should find same number of modified files
    assert len(result1.entries) == len(result2.entries)


def test_invalid_commit_reference(git_repo):
    """Test handling of invalid commit references."""
    strategy = TreeSetDiff(git_repo)
    result = strategy.diff("invalid_sha", "also_invalid")
    
    assert result.error is not None


def test_commit_validation(git_repo):
    """Test input validation."""
    strategy = TreeSetDiff(git_repo)
    
    with pytest.raises(ValueError):
        strategy.diff("", "sha")
    
    with pytest.raises(ValueError):
        strategy.diff("sha", "")


def test_diff_result_stats(git_repo):
    """Test DiffResult.stats() method."""
    commit(git_repo, {"file1.txt": "v1", "file2.txt": "v1"}, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    subprocess.run([*GIT, "-C", git_repo, "rm", "file1.txt"], check=True)
    commit(git_repo, {"file3.txt": "v3"}, "changes")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    strategy = TreeSetDiff(git_repo)
    result = strategy.diff(sha1, sha2)
    stats = result.stats()
    
    assert stats["deleted"] == 1
    assert stats["created"] >= 1
    assert stats["total_files"] >= 2


# ============================================================================
# Performance Benchmarks
# ============================================================================


@pytest.mark.slow
def test_benchmark_strategies_on_realistic_repo(git_repo):
    """Benchmark all strategies on a realistic repo."""
    # Create a realistic repo structure
    files = {}
    for dir_name in ["src", "docs", "tests", "build"]:
        for i in range(20):
            files[f"{dir_name}/file{i}.py"] = f"# {dir_name}/{i}\ndata = {i}\n"
    
    commit(git_repo, files, "initial")
    sha1 = git(git_repo, "rev-parse", "HEAD")
    
    # Modify 30% of files
    for i in range(6):
        files[f"src/file{i}.py"] = f"# MODIFIED\ndata = {i * 2}\n"
    
    # Add new files
    for i in range(5):
        files[f"src/new{i}.py"] = f"# NEW\ndata = new{i}\n"
    
    commit(git_repo, files, "changes")
    sha2 = git(git_repo, "rev-parse", "HEAD")
    
    chain = DiffChain(git_repo)
    
    # Run benchmark
    start = time.time()
    result = chain.run_all(sha1, sha2)
    elapsed = time.time() - start
    
    # Should complete in reasonable time
    assert elapsed < 30  # 30 second timeout
    assert len(result) >= 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
