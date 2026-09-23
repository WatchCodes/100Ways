"""DIFF category: 20 comprehensive strategies for detecting and analyzing git diffs.

This module implements the DiffChain pattern - a pluggable, composable system for
diffing git repositories using diverse strategies:

  1. git_plumbing - low-level git diff-tree/ls-tree
  2. tree_set_diff - set-based tree comparison
  3. unified_diff_parsing - parse unified diff format
  4. worktree_diffs - working tree changes vs index
  5. range_diff - commit-by-commit diff analysis
  6. blob_sha_compare - direct blob SHA256 comparison
  7. sequence_matcher - difflib.SequenceMatcher for line diffs
  8. pathspec_limited - limit diffs to pathspec patterns
  9. first_parent_walks - first-parent-only traversal
  10. batch_blob_reads - efficient multi-blob batch reading
  11. mirror_ref_compare - compare refs from mirrored repos
  12. staged_tree_diffs - index vs working tree
  13. three_way_merge - base/ours/theirs merge analysis
  14. narrow_pathspecs - precise pathspec filtering
  15. commit_count_deltas - commit count analysis
  16. blame_windows - blame-based diff windows
  17. submodule_pointers - detect submodule changes
  18. empty_tree_baselines - use empty tree (4b825...) as base
  19. rename_only - detect and track renames
  20. binary_safe - handle binary files safely

Each strategy is pluggable and can be chained via DiffChain for composite analysis.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

logger = logging.getLogger(__name__)

# Empty tree object SHA (used as baseline for initial commits)
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class DiffEntry:
    """Represents a single file change in a diff."""
    path: str
    status: str  # M, A, D, R, C, T, U, X
    old_mode: str = "000000"
    new_mode: str = "000000"
    old_sha: str = ""
    new_sha: str = ""
    similarity: int = 0  # 0-100 for renames/copies
    old_path: str = ""  # for renames
    added_lines: int = 0
    deleted_lines: int = 0
    is_binary: bool = False
    blame_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffResult:
    """Result of a diff operation."""
    strategy: str
    commit_a: str
    commit_b: str
    entries: list[DiffEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timing_ms: float = 0.0

    def stats(self) -> dict[str, int]:
        """Return diff statistics."""
        added = deleted = modified = renamed = deleted_f = created = 0
        for e in self.entries:
            if e.status == "A":
                created += 1
            elif e.status == "D":
                deleted_f += 1
            elif e.status == "M":
                modified += 1
            elif e.status == "R":
                renamed += 1
        return {
            "created": created,
            "deleted": deleted_f,
            "modified": modified,
            "renamed": renamed,
            "total_files": len(self.entries),
            "total_added_lines": sum(e.added_lines for e in self.entries),
            "total_deleted_lines": sum(e.deleted_lines for e in self.entries),
        }


# ============================================================================
# Strategy Base Classes
# ============================================================================


class DiffStrategy(ABC):
    """Abstract base for a diff strategy."""

    def __init__(self, repo: str):
        self.repo = repo
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Compute diff between two commits."""
        pass

    def _validate_inputs(self, commit_a: str, commit_b: str) -> None:
        """Validate commit references."""
        if not commit_a or not commit_b:
            raise ValueError("commit_a and commit_b must not be empty")
        if not isinstance(commit_a, str) or not isinstance(commit_b, str):
            raise TypeError("commits must be strings")
        if len(commit_a) > 128 or len(commit_b) > 128:
            raise ValueError("invalid commit reference length")

    def _git(self, *args: str) -> str:
        """Run git command, raise on error."""
        try:
            proc = subprocess.run(
                ["git", "-C", self.repo, *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()}")
            return proc.stdout
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git {args[0]} timed out")

    def _git_bytes(self, *args: str) -> bytes:
        """Run git command returning raw bytes."""
        try:
            proc = subprocess.run(
                ["git", "-C", self.repo, *args],
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {proc.stderr.decode()}")
            return proc.stdout
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git {args[0]} timed out")

    def _looks_binary(self, data: bytes) -> bool:
        """Check if data looks binary."""
        return b"\x00" in data[:8192]


# ============================================================================
# Strategy 1: Git Plumbing (diff-tree)
# ============================================================================


class GitPlumbingDiff(DiffStrategy):
    """Use git diff-tree for low-level diffing."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Diff using git plumbing (diff-tree raw format)."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="git_plumbing", commit_a=commit_a, commit_b=commit_b)

        try:
            # Use git diff-tree with null separator for reliable parsing
            output = self._git("diff-tree", "-r", "-z", "--raw", commit_a, commit_b)
            
            # Split on null bytes - format is: metadata\0path\0metadata\0path\0...
            parts = output.rstrip("\0").split("\0")
            
            # Process pairs of (metadata, path)
            for i in range(0, len(parts) - 1, 2):
                meta = parts[i].strip()
                path = parts[i + 1] if i + 1 < len(parts) else ""
                
                if not meta:
                    continue
                
                entry = self._parse_raw_line(meta)
                if entry:
                    # Override path with the null-separated path value
                    entry.path = path
                    result.entries.append(entry)
            
            result.metadata["format"] = "raw"
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"git_plumbing failed: {e}")

        return result
    
    def _parse_raw_line(self, line: str) -> Optional[DiffEntry]:
        """Parse git diff-tree raw format line."""
        if not line.strip():
            return None
        
        # Format: :oldmode newmode oldhash newhash status\tpath
        # Split on tab to separate metadata from path
        if "\t" in line:
            meta, path = line.split("\t", 1)
            parts = meta.split()
        else:
            parts = line.split()
            path = ""
        
        if len(parts) < 5:
            return None
        
        status = parts[4][0] if len(parts[4]) > 0 else "M"
        old_mode = parts[0].lstrip(":")  # Remove leading colon
        new_mode = parts[1]
        old_sha = parts[2]
        new_sha = parts[3]
        
        return DiffEntry(
            path=path,
            status=status,
            old_mode=old_mode,
            new_mode=new_mode,
            old_sha=old_sha,
            new_sha=new_sha,
        )


# ============================================================================
# Strategy 2: Tree Set Diff
# ============================================================================


class TreeSetDiff(DiffStrategy):
    """Set-based tree comparison."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Diff by comparing file sets."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="tree_set_diff", commit_a=commit_a, commit_b=commit_b)

        try:
            files_a = self._tree_files(commit_a)
            files_b = self._tree_files(commit_b)
            
            set_a = set(files_a)
            set_b = set(files_b)
            
            # Files deleted, added, or potentially modified
            for path in set_a - set_b:
                result.entries.append(DiffEntry(path=path, status="D"))
            
            for path in set_b - set_a:
                result.entries.append(DiffEntry(path=path, status="A"))
            
            # Check common files for modifications
            for path in set_a & set_b:
                sha_a = self._get_file_sha(commit_a, path)
                sha_b = self._get_file_sha(commit_b, path)
                if sha_a != sha_b:
                    result.entries.append(DiffEntry(path=path, status="M", old_sha=sha_a, new_sha=sha_b))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"tree_set_diff failed: {e}")

        return result

    def _tree_files(self, commit: str) -> list[str]:
        """List all files in a commit's tree."""
        output = self._git("ls-tree", "-r", "--name-only", commit)
        return [p for p in output.splitlines() if p.strip()]

    def _get_file_sha(self, commit: str, path: str) -> str:
        """Get the SHA of a file in a commit."""
        try:
            output = self._git("ls-tree", commit, "--", path)
            parts = output.split()
            return parts[2] if len(parts) > 2 else ""
        except Exception:
            return ""


# ============================================================================
# Strategy 3: Unified Diff Parsing
# ============================================================================


class UnifiedDiffParsing(DiffStrategy):
    """Parse unified diff format for line-level diffs."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Parse unified diff output."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="unified_diff_parsing", commit_a=commit_a, commit_b=commit_b)

        try:
            output = self._git("diff", "-U0", commit_a, commit_b)
            result.entries = self._parse_unified_diff(output)
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"unified_diff_parsing failed: {e}")

        return result

    def _parse_unified_diff(self, output: str) -> list[DiffEntry]:
        """Parse unified diff output into entries with line counts."""
        entries: dict[str, DiffEntry] = {}
        current_path = None
        current_entry: Optional[DiffEntry] = None

        for line in output.splitlines():
            if line.startswith("diff --git"):
                # Extract path: diff --git a/path b/path
                match = re.search(r"b/(.+)$", line)
                if match:
                    current_path = match.group(1)
                    if current_path not in entries:
                        current_entry = DiffEntry(path=current_path, status="M")
                        entries[current_path] = current_entry

            elif line.startswith("new file"):
                if current_path and current_path in entries:
                    entries[current_path].status = "A"

            elif line.startswith("deleted file"):
                if current_path and current_path in entries:
                    entries[current_path].status = "D"

            elif line.startswith("@@"):
                # Extract hunk header: @@ -a,b +c,d @@
                match = re.match(r"@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@", line)
                if match and current_entry:
                    old_count = int(match.group(2) or 1) if match.group(2) else 1
                    new_count = int(match.group(4) or 1) if match.group(4) else 1
                    # Approximate line changes
                    current_entry.deleted_lines += max(0, old_count)
                    current_entry.added_lines += max(0, new_count)

        return list(entries.values())


# ============================================================================
# Strategy 4: Worktree Diffs
# ============================================================================


class WorktreeDiff(DiffStrategy):
    """Detect working tree changes vs a commit."""

    def diff(self, commit_a: str, commit_b: str = "HEAD") -> DiffResult:
        """Diff working tree against a commit (b is typically HEAD)."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="worktree_diff", commit_a=commit_a, commit_b=commit_b)

        try:
            # Get diff of working tree vs HEAD (or specified commit)
            output = self._git("diff", "--name-status", commit_a)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"worktree_diff failed: {e}")

        return result


# ============================================================================
# Strategy 5: Range Diff
# ============================================================================


class RangeDiff(DiffStrategy):
    """Analyze diffs across a range of commits."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Show diff of diffs (commits in a..b)."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="range_diff", commit_a=commit_a, commit_b=commit_b)

        try:
            # Get commits in range a..b
            output = self._git("log", "--format=%H", f"{commit_a}..{commit_b}")
            commits = [c.strip() for c in output.splitlines() if c.strip()]
            
            result.metadata["commit_count"] = len(commits)
            
            # For each commit, get its diff
            all_files: dict[str, DiffEntry] = {}
            for commit in commits:
                parent = f"{commit}^" if commit != commits[0] else commit_a
                try:
                    diff_output = self._git("diff", "--name-status", parent, commit)
                    for line in diff_output.splitlines():
                        if not line.strip():
                            continue
                        parts = line.split("\t")
                        status = parts[0][0] if parts else "M"
                        path = parts[1] if len(parts) > 1 else ""
                        if path:
                            if path not in all_files:
                                all_files[path] = DiffEntry(path=path, status=status)
                            else:
                                # Aggregate status
                                all_files[path].status = self._aggregate_status(all_files[path].status, status)
                except Exception:
                    pass
            
            result.entries = list(all_files.values())
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"range_diff failed: {e}")

        return result

    def _aggregate_status(self, a: str, b: str) -> str:
        """Aggregate two status codes."""
        if a == "D" or b == "D":
            return "D"
        if a == "A" or b == "A":
            return "A"
        return "M"


# ============================================================================
# Strategy 6: Blob SHA Compare
# ============================================================================


class BlobSHACompare(DiffStrategy):
    """Direct blob SHA256 comparison."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Compare blobs by SHA."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="blob_sha_compare", commit_a=commit_a, commit_b=commit_b)

        try:
            files_a = self._get_tree_shas(commit_a)
            files_b = self._get_tree_shas(commit_b)
            
            all_paths = set(files_a.keys()) | set(files_b.keys())
            for path in all_paths:
                sha_a = files_a.get(path)
                sha_b = files_b.get(path)
                
                if sha_a is None:
                    result.entries.append(DiffEntry(path=path, status="A", new_sha=sha_b))
                elif sha_b is None:
                    result.entries.append(DiffEntry(path=path, status="D", old_sha=sha_a))
                elif sha_a != sha_b:
                    result.entries.append(DiffEntry(path=path, status="M", old_sha=sha_a, new_sha=sha_b))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"blob_sha_compare failed: {e}")

        return result

    def _get_tree_shas(self, commit: str) -> dict[str, str]:
        """Get {path: sha} map for a tree."""
        output = self._git("ls-tree", "-r", commit)
        shas = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                path = " ".join(parts[3:])
                sha = parts[2]
                shas[path] = sha
        return shas


# ============================================================================
# Strategy 7: SequenceMatcher (difflib)
# ============================================================================


class SequenceMatcherDiff(DiffStrategy):
    """Use difflib.SequenceMatcher for similarity-based diffs."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Use sequence matching for file similarity."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="sequence_matcher", commit_a=commit_a, commit_b=commit_b)

        try:
            files_a = self._tree_files(commit_a)
            files_b = self._tree_files(commit_b)
            
            set_a = set(files_a)
            set_b = set(files_b)
            
            # Deletions
            for path in set_a - set_b:
                result.entries.append(DiffEntry(path=path, status="D"))
            
            # Additions
            for path in set_b - set_a:
                result.entries.append(DiffEntry(path=path, status="A"))
            
            # Check for renames/similarity
            deleted_files = set_a - set_b
            added_files = set_b - set_a
            
            for add_path in list(added_files):
                best_similarity = 0.0
                best_del_path = None
                
                for del_path in deleted_files:
                    similarity = self._compute_similarity(commit_a, del_path, commit_b, add_path)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_del_path = del_path
                
                if best_similarity > 0.8 and best_del_path:
                    # Likely a rename
                    result.entries.append(DiffEntry(
                        path=add_path,
                        status="R",
                        old_path=best_del_path,
                        similarity=int(best_similarity * 100),
                    ))
                    deleted_files.discard(best_del_path)
                    added_files.discard(add_path)
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"sequence_matcher failed: {e}")

        return result

    def _tree_files(self, commit: str) -> list[str]:
        """List files in tree."""
        output = self._git("ls-tree", "-r", "--name-only", commit)
        return [p.strip() for p in output.splitlines() if p.strip()]

    def _compute_similarity(self, commit_a: str, path_a: str, commit_b: str, path_b: str) -> float:
        """Compute similarity between two file versions."""
        try:
            blob_a = self._git_bytes("show", f"{commit_a}:{path_a}")
            blob_b = self._git_bytes("show", f"{commit_b}:{path_b}")
            
            if self._looks_binary(blob_a) or self._looks_binary(blob_b):
                # Binary: only check if identical
                return 1.0 if blob_a == blob_b else 0.0
            
            # Text: use SequenceMatcher
            text_a = blob_a.decode("utf-8", "replace")
            text_b = blob_b.decode("utf-8", "replace")
            matcher = difflib.SequenceMatcher(None, text_a, text_b)
            return matcher.ratio()
        except Exception:
            return 0.0


# ============================================================================
# Strategy 8: Pathspec-Limited
# ============================================================================


class PathspecLimitedDiff(DiffStrategy):
    """Limit diffs to specific pathspecs."""

    def diff(self, commit_a: str, commit_b: str, pathspecs: Optional[list[str]] = None) -> DiffResult:
        """Diff with pathspec filtering."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="pathspec_limited", commit_a=commit_a, commit_b=commit_b)

        try:
            if pathspecs is None:
                pathspecs = []
            
            # Build git diff command with pathspecs
            cmd = ["diff", "--name-status", commit_a, commit_b]
            cmd.extend(["--"] + pathspecs if pathspecs else [])
            
            output = self._git(*cmd)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
            
            result.metadata["pathspecs"] = pathspecs
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"pathspec_limited failed: {e}")

        return result


# ============================================================================
# Strategy 9: First-Parent Walks
# ============================================================================


class FirstParentWalk(DiffStrategy):
    """Diff only first-parent commits."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Diff using first-parent traversal."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="first_parent_walk", commit_a=commit_a, commit_b=commit_b)

        try:
            # Get first-parent ancestry
            output = self._git("rev-list", "--first-parent", f"{commit_a}..{commit_b}")
            commits = [c.strip() for c in output.splitlines() if c.strip()]
            
            result.metadata["first_parent_commits"] = len(commits)
            
            # Aggregate diffs across first-parent commits
            all_files: dict[str, DiffEntry] = {}
            for commit in commits:
                parent = f"{commit}^"
                try:
                    diff_output = self._git("diff", "--name-status", parent, commit)
                    for line in diff_output.splitlines():
                        if not line.strip():
                            continue
                        parts = line.split("\t")
                        status = parts[0][0] if parts else "M"
                        path = parts[1] if len(parts) > 1 else ""
                        if path:
                            all_files[path] = DiffEntry(path=path, status=status)
                except Exception:
                    pass
            
            result.entries = list(all_files.values())
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"first_parent_walk failed: {e}")

        return result


# ============================================================================
# Strategy 10: Batch Blob Reads
# ============================================================================


class BatchBlobReader:
    """Efficient batch reading of blobs via git cat-file."""

    def __init__(self, repo: str):
        self.repo = repo
        self.proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def read(self, commit: str, path: str) -> bytes:
        """Read blob content."""
        if not self.proc.stdin or not self.proc.stdout:
            return b""
        try:
            self.proc.stdin.write(f"{commit}:{path}\n".encode())
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().decode()
            parts = header.split()
            if not parts or parts[0] == "missing" or len(parts) < 3:
                return b""
            size = int(parts[2])
            data = self.proc.stdout.read(size)
            self.proc.stdout.read(1)  # trailing newline
            return data
        except Exception:
            return b""

    def close(self) -> None:
        """Close the batch process."""
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class BatchBlobDiff(DiffStrategy):
    """Use batch blob reads for efficient diffing."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Diff using batch blob reads."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="batch_blob_reads", commit_a=commit_a, commit_b=commit_b)

        reader = BatchBlobReader(self.repo)
        try:
            files_a = self._tree_files(commit_a)
            files_b = self._tree_files(commit_b)
            
            set_a = set(files_a)
            set_b = set(files_b)
            
            # Deletions
            for path in set_a - set_b:
                result.entries.append(DiffEntry(path=path, status="D"))
            
            # Additions
            for path in set_b - set_a:
                result.entries.append(DiffEntry(path=path, status="A"))
            
            # Modifications (using batch reads)
            for path in set_a & set_b:
                blob_a = reader.read(commit_a, path)
                blob_b = reader.read(commit_b, path)
                if blob_a != blob_b:
                    result.entries.append(DiffEntry(path=path, status="M"))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"batch_blob_diff failed: {e}")
        finally:
            reader.close()

        return result

    def _tree_files(self, commit: str) -> list[str]:
        """List files in tree."""
        output = self._git("ls-tree", "-r", "--name-only", commit)
        return [p.strip() for p in output.splitlines() if p.strip()]


# ============================================================================
# Strategy 11: Mirror Ref Compare
# ============================================================================


class MirrorRefCompare(DiffStrategy):
    """Compare refs from mirrored repositories."""

    def diff(self, ref_a: str, ref_b: str) -> DiffResult:
        """Diff two refs (may be from different remotes)."""
        self._validate_inputs(ref_a, ref_b)
        result = DiffResult(strategy="mirror_ref_compare", commit_a=ref_a, commit_b=ref_b)

        try:
            # Resolve refs to SHAs
            sha_a = self._git("rev-parse", ref_a).strip()
            sha_b = self._git("rev-parse", ref_b).strip()
            
            # Then diff the SHAs
            output = self._git("diff", "--name-status", sha_a, sha_b)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
            
            result.metadata["ref_a"] = ref_a
            result.metadata["ref_b"] = ref_b
            result.metadata["sha_a"] = sha_a
            result.metadata["sha_b"] = sha_b
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"mirror_ref_compare failed: {e}")

        return result


# ============================================================================
# Strategy 12: Staged Tree Diffs
# ============================================================================


class StagedTreeDiff(DiffStrategy):
    """Index vs working tree diffs."""

    def diff(self, commit_a: str = "HEAD", commit_b: str = "") -> DiffResult:
        """Diff staged changes (index vs commit)."""
        self._validate_inputs(commit_a, "HEAD")  # validate commit_a only
        result = DiffResult(strategy="staged_tree_diff", commit_a=commit_a, commit_b="INDEX")

        try:
            # Diff between commit and index
            output = self._git("diff", "--name-status", "--cached", commit_a)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"staged_tree_diff failed: {e}")

        return result


# ============================================================================
# Strategy 13: Three-Way Merge
# ============================================================================


class ThreeWayMergeDiff(DiffStrategy):
    """Base/ours/theirs merge analysis."""

    def diff(self, commit_a: str, commit_b: str, base: Optional[str] = None) -> DiffResult:
        """Analyze three-way diff."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="three_way_merge", commit_a=commit_a, commit_b=commit_b)

        try:
            if base is None:
                # Use merge-base
                base = self._git("merge-base", commit_a, commit_b).strip()
            
            result.metadata["merge_base"] = base
            
            # Get diffs: base->a and base->b
            diff_a = self._get_diff_map(base, commit_a)
            diff_b = self._get_diff_map(base, commit_b)
            
            all_paths = set(diff_a.keys()) | set(diff_b.keys())
            for path in all_paths:
                a_status = diff_a.get(path, "")
                b_status = diff_b.get(path, "")
                
                # Determine conflict type
                if a_status == "D" and b_status == "D":
                    status = "D"  # Both deleted
                elif a_status == "D" or b_status == "D":
                    status = "U"  # Conflict: one deleted
                elif a_status == "A" and b_status == "A":
                    status = "C"  # Conflict: both added
                elif a_status or b_status:
                    status = "M"  # Modified on one side
                else:
                    status = "U"  # Unknown
                
                entry = DiffEntry(path=path, status=status)
                result.entries.append(entry)
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"three_way_merge failed: {e}")

        return result

    def _get_diff_map(self, base: str, commit: str) -> dict[str, str]:
        """Get {path: status} map for a diff."""
        output = self._git("diff", "--name-status", base, commit)
        diff_map = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0][0] if parts else "M"
            path = parts[1] if len(parts) > 1 else ""
            if path:
                diff_map[path] = status
        return diff_map


# ============================================================================
# Strategy 14: Narrow Pathspecs
# ============================================================================


class NarrowPathspecDiff(DiffStrategy):
    """Precise pathspec filtering with regex."""

    def diff(self, commit_a: str, commit_b: str, pattern: Optional[str] = None) -> DiffResult:
        """Diff with regex pathspec filtering."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="narrow_pathspec", commit_a=commit_a, commit_b=commit_b)

        try:
            output = self._git("diff", "--name-status", commit_a, commit_b)
            
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                
                if not path:
                    continue
                
                # Filter by pattern if provided
                if pattern and not re.search(pattern, path):
                    continue
                
                result.entries.append(DiffEntry(path=path, status=status))
            
            result.metadata["pattern"] = pattern
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"narrow_pathspec failed: {e}")

        return result


# ============================================================================
# Strategy 15: Commit Count Deltas
# ============================================================================


class CommitCountDelta(DiffStrategy):
    """Commit count analysis across ranges."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Analyze commit counts and deltas."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="commit_count_deltas", commit_a=commit_a, commit_b=commit_b)

        try:
            # Count commits in a..b and b..a
            count_a_to_b = len(
                self._git("rev-list", f"{commit_a}..{commit_b}").strip().split("\n")
            )
            count_b_to_a = len(
                self._git("rev-list", f"{commit_b}..{commit_a}").strip().split("\n")
            )
            
            result.metadata["commits_a_to_b"] = count_a_to_b
            result.metadata["commits_b_to_a"] = count_b_to_a
            result.metadata["diverged"] = count_a_to_b > 0 and count_b_to_a > 0
            
            # Get the actual files changed
            output = self._git("diff", "--name-status", commit_a, commit_b)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"commit_count_deltas failed: {e}")

        return result


# ============================================================================
# Strategy 16: Blame Windows
# ============================================================================


class BlameWindowDiff(DiffStrategy):
    """Blame-based diff analysis with context windows."""

    def diff(self, commit_a: str, commit_b: str, window_size: int = 5) -> DiffResult:
        """Diff with blame context windows."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="blame_windows", commit_a=commit_a, commit_b=commit_b)

        try:
            files_a = self._tree_files(commit_a)
            files_b = self._tree_files(commit_b)
            
            set_a = set(files_a)
            set_b = set(files_b)
            
            # Process changed files
            for path in set_a & set_b:
                blob_a = self._git_bytes("show", f"{commit_a}:{path}")
                blob_b = self._git_bytes("show", f"{commit_b}:{path}")
                
                if blob_a != blob_b and not self._looks_binary(blob_a):
                    # Get blame info for old and new
                    blame_old = self._get_blame_info(commit_a, path)
                    blame_new = self._get_blame_info(commit_b, path)
                    
                    entry = DiffEntry(path=path, status="M")
                    entry.blame_info = {
                        "old_authors": blame_old,
                        "new_authors": blame_new,
                    }
                    result.entries.append(entry)
            
            # Additions/deletions
            for path in set_a - set_b:
                result.entries.append(DiffEntry(path=path, status="D"))
            for path in set_b - set_a:
                result.entries.append(DiffEntry(path=path, status="A"))
            
            result.metadata["window_size"] = window_size
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"blame_windows failed: {e}")

        return result

    def _tree_files(self, commit: str) -> list[str]:
        """List files in tree."""
        output = self._git("ls-tree", "-r", "--name-only", commit)
        return [p.strip() for p in output.splitlines() if p.strip()]

    def _get_blame_info(self, commit: str, path: str) -> dict[str, int]:
        """Get blame info (author counts) for a file."""
        try:
            output = self._git("blame", commit, "--", path)
            authors: dict[str, int] = {}
            for line in output.splitlines():
                # Parse blame output: (author ...
                match = re.match(r"^[a-f0-9]+\s+\(([^0-9]+)\s+", line)
                if match:
                    author = match.group(1).strip()
                    authors[author] = authors.get(author, 0) + 1
            return authors
        except Exception:
            return {}


# ============================================================================
# Strategy 17: Submodule Pointers
# ============================================================================


class SubmoduleDiff(DiffStrategy):
    """Detect and track submodule changes."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Detect submodule pointer changes."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="submodule_pointers", commit_a=commit_a, commit_b=commit_b)

        try:
            # Use git diff with submodule=short to show submodule diffs
            output = self._git("diff", "--submodule=short", commit_a, commit_b)
            
            submodule_diffs = self._parse_submodule_output(output)
            for path, old_sha, new_sha in submodule_diffs:
                entry = DiffEntry(path=path, status="M", old_sha=old_sha, new_sha=new_sha)
                entry.metadata = {"submodule": True}
                result.entries.append(entry)
            
            # Also get regular file diffs
            output = self._git("diff", "--name-status", commit_a, commit_b)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "M"
                path = parts[1] if len(parts) > 1 else ""
                if path and "Subproject commit" not in output:
                    result.entries.append(DiffEntry(path=path, status=status))
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"submodule_diff failed: {e}")

        return result

    def _parse_submodule_output(self, output: str) -> list[tuple[str, str, str]]:
        """Parse submodule diff output."""
        submodules = []
        lines = output.splitlines()
        i = 0
        while i < len(lines):
            if "Subproject commit" in lines[i]:
                # Extract submodule path and SHAs
                # Format: diff --git a/path b/path
                if i > 0:
                    for j in range(i-1, -1, -1):
                        if lines[j].startswith("diff --git"):
                            match = re.search(r"b/(.+)$", lines[j])
                            if match:
                                path = match.group(1)
                                # Get old and new SHA from Subproject lines
                                if i < len(lines):
                                    sha_old = re.search(r"Subproject commit ([a-f0-9]+)", lines[i])
                                    sha_new = ""
                                    if i+1 < len(lines):
                                        sha_new_m = re.search(r"Subproject commit ([a-f0-9]+)", lines[i+1])
                                        sha_new = sha_new_m.group(1) if sha_new_m else ""
                                    if sha_old:
                                        submodules.append((path, sha_old.group(1), sha_new))
                            break
            i += 1
        return submodules


# ============================================================================
# Strategy 18: Empty Tree Baselines
# ============================================================================


class EmptyTreeDiff(DiffStrategy):
    """Use empty tree (4b825...) as baseline."""

    def diff(self, commit_a: str, commit_b: str = "") -> DiffResult:
        """Diff against empty tree baseline."""
        self._validate_inputs(commit_a, "HEAD")
        result = DiffResult(strategy="empty_tree_baselines", commit_a=EMPTY_TREE_SHA, commit_b=commit_a)

        try:
            # Diff empty tree against commit
            output = self._git("diff", "--name-status", EMPTY_TREE_SHA, commit_a)
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0][0] if parts else "A"
                path = parts[1] if len(parts) > 1 else ""
                if path:
                    result.entries.append(DiffEntry(path=path, status=status))
            
            result.metadata["baseline"] = EMPTY_TREE_SHA
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"empty_tree_diff failed: {e}")

        return result


# ============================================================================
# Strategy 19: Rename Detection
# ============================================================================


class RenameOnlyDiff(DiffStrategy):
    """Detect and track renames only."""

    def diff(self, commit_a: str, commit_b: str, threshold: int = 80) -> DiffResult:
        """Detect renames with similarity threshold."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="rename_only", commit_a=commit_a, commit_b=commit_b)

        try:
            # Build git command properly - split -M<threshold> into separate args
            # git diff-tree -M<N> detects renames with N% similarity
            output = self._git("diff-tree", "-r", f"-M{threshold}%", "--name-status", commit_a, commit_b)
            
            for line in output.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0] if parts else "M"
                
                if status.startswith("R"):
                    # Rename with similarity
                    similarity_match = re.search(r"R(\d+)", status)
                    similarity = int(similarity_match.group(1)) if similarity_match else 100
                    
                    old_path = parts[1] if len(parts) > 1 else ""
                    new_path = parts[2] if len(parts) > 2 else ""
                    
                    result.entries.append(DiffEntry(
                        path=new_path,
                        status="R",
                        old_path=old_path,
                        similarity=similarity,
                    ))
                elif len(parts) >= 2:
                    result.entries.append(DiffEntry(
                        path=parts[1],
                        status=status[0] if status else "M",
                    ))
            
            result.metadata["rename_threshold"] = threshold
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"rename_only failed: {e}")

        return result


# ============================================================================
# Strategy 20: Binary-Safe
# ============================================================================


class BinarySafeDiff(DiffStrategy):
    """Handle binary files safely with metadata only."""

    def diff(self, commit_a: str, commit_b: str) -> DiffResult:
        """Diff with binary file handling."""
        self._validate_inputs(commit_a, commit_b)
        result = DiffResult(strategy="binary_safe", commit_a=commit_a, commit_b=commit_b)

        try:
            files_a = self._tree_files(commit_a)
            files_b = self._tree_files(commit_b)
            
            set_a = set(files_a)
            set_b = set(files_b)
            
            # Deletions
            for path in set_a - set_b:
                result.entries.append(DiffEntry(path=path, status="D"))
            
            # Additions
            for path in set_b - set_a:
                result.entries.append(DiffEntry(path=path, status="A"))
            
            # Modifications (check binary-safe)
            for path in set_a & set_b:
                blob_a = self._git_bytes("show", f"{commit_a}:{path}")
                blob_b = self._git_bytes("show", f"{commit_b}:{path}")
                
                is_binary = self._looks_binary(blob_a) or self._looks_binary(blob_b)
                
                if blob_a != blob_b:
                    entry = DiffEntry(path=path, status="M", is_binary=is_binary)
                    
                    # For binary, just report size difference
                    if is_binary:
                        entry.metadata = {
                            "old_size": len(blob_a),
                            "new_size": len(blob_b),
                        }
                    
                    result.entries.append(entry)
            
            result.metadata["binary_safe"] = True
        except Exception as e:
            result.error = str(e)
            self.logger.error(f"binary_safe failed: {e}")

        return result

    def _tree_files(self, commit: str) -> list[str]:
        """List files in tree."""
        output = self._git("ls-tree", "-r", "--name-only", commit)
        return [p.strip() for p in output.splitlines() if p.strip()]


# ============================================================================
# DiffChain: Composable Diff Engine
# ============================================================================


class DiffChain:
    """Pluggable diff chain for composing multiple strategies."""

    def __init__(self, repo: str):
        self.repo = repo
        self.logger = logging.getLogger(f"{__name__}.DiffChain")
        self.strategies: dict[str, DiffStrategy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all 20 strategies."""
        self.register("git_plumbing", GitPlumbingDiff(self.repo))
        self.register("tree_set", TreeSetDiff(self.repo))
        self.register("unified_diff", UnifiedDiffParsing(self.repo))
        self.register("worktree", WorktreeDiff(self.repo))
        self.register("range_diff", RangeDiff(self.repo))
        self.register("blob_sha", BlobSHACompare(self.repo))
        self.register("sequence_matcher", SequenceMatcherDiff(self.repo))
        self.register("pathspec_limited", PathspecLimitedDiff(self.repo))
        self.register("first_parent", FirstParentWalk(self.repo))
        self.register("batch_blobs", BatchBlobDiff(self.repo))
        self.register("mirror_ref", MirrorRefCompare(self.repo))
        self.register("staged_tree", StagedTreeDiff(self.repo))
        self.register("three_way", ThreeWayMergeDiff(self.repo))
        self.register("narrow_pathspec", NarrowPathspecDiff(self.repo))
        self.register("commit_count", CommitCountDelta(self.repo))
        self.register("blame_windows", BlameWindowDiff(self.repo))
        self.register("submodule", SubmoduleDiff(self.repo))
        self.register("empty_tree", EmptyTreeDiff(self.repo))
        self.register("rename_only", RenameOnlyDiff(self.repo))
        self.register("binary_safe", BinarySafeDiff(self.repo))

    def register(self, name: str, strategy: DiffStrategy) -> None:
        """Register a diff strategy."""
        if not isinstance(strategy, DiffStrategy):
            raise TypeError(f"{name} must be a DiffStrategy")
        self.strategies[name] = strategy
        self.logger.debug(f"Registered strategy: {name}")

    def run(self, strategy_name: str, commit_a: str, commit_b: str, **kwargs) -> DiffResult:
        """Run a specific strategy."""
        if strategy_name not in self.strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        strategy = self.strategies[strategy_name]
        try:
            return strategy.diff(commit_a, commit_b, **kwargs)
        except Exception as e:
            self.logger.error(f"Strategy {strategy_name} failed: {e}")
            result = DiffResult(strategy=strategy_name, commit_a=commit_a, commit_b=commit_b)
            result.error = str(e)
            return result

    def run_all(self, commit_a: str, commit_b: str) -> dict[str, DiffResult]:
        """Run all registered strategies."""
        results = {}
        for name in self.strategies:
            results[name] = self.run(name, commit_a, commit_b)
        return results

    def composite(
        self,
        commit_a: str,
        commit_b: str,
        strategies: Optional[list[str]] = None,
        merge_fn: Optional[Callable[[list[DiffResult]], DiffResult]] = None,
    ) -> DiffResult:
        """Run multiple strategies and merge results."""
        if strategies is None:
            strategies = ["tree_set", "unified_diff"]
        
        results = [self.run(s, commit_a, commit_b) for s in strategies]
        
        if merge_fn:
            return merge_fn(results)
        
        return self._default_merge(results)

    def _default_merge(self, results: list[DiffResult]) -> DiffResult:
        """Default merge strategy: union of entries."""
        merged = DiffResult(
            strategy="composite",
            commit_a=results[0].commit_a if results else "",
            commit_b=results[0].commit_b if results else "",
        )
        
        # Deduplicate entries by path+status
        seen = set()
        for result in results:
            if result.error:
                continue
            for entry in result.entries:
                key = (entry.path, entry.status)
                if key not in seen:
                    seen.add(key)
                    merged.entries.append(entry)
        
        merged.metadata = {
            "strategies": [r.strategy for r in results],
            "source_results": len(results),
        }
        
        return merged
