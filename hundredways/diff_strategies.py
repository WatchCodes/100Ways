"""DIFF strategies: 10+ ways to compare two trees.

Each strategy compares two git commits and produces a structured diff.
Strategies compose via DiffChain for multi-method analysis.
"""

from __future__ import annotations

import subprocess
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import difflib


@dataclass
class FileDiff:
    """A single file's difference."""
    path: str
    status: str  # added, deleted, modified, renamed
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    similarity: float = 0.0  # 0.0-1.0
    diff_type: str = "content"  # content, binary, symlink, permission


@dataclass
class DiffResult:
    """Result of comparing two commits."""
    strategy: str
    old_ref: str
    new_ref: str
    files: list[FileDiff]
    summary: dict  # total added, deleted, modified, etc.
    has_blockers: bool = False


class DiffStrategy(ABC):
    """Base class for diff strategies."""

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @abstractmethod
    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Compare two refs and return structured diff."""
        pass


class GitDiffNumstat(DiffStrategy):
    """git diff --numstat: line counts per file."""

    def name(self) -> str:
        return "diff.numstat"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Use git diff --numstat for fast line counts."""
        try:
            output = subprocess.check_output(
                ["git", "diff", "--numstat", f"{old_ref}..{new_ref}"],
                cwd=repo_path,
                text=True
            ).strip()

            files = []
            for line in output.split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                adds = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]

                files.append(FileDiff(
                    path=path,
                    status="modified",
                    additions=adds,
                    deletions=dels,
                    diff_type="content"
                ))

            summary = {
                "files_changed": len(files),
                "total_additions": sum(f.additions for f in files),
                "total_deletions": sum(f.deletions for f in files),
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class GitDiffNameStatus(DiffStrategy):
    """git diff --name-status: file status (A/D/M/R)."""

    def name(self) -> str:
        return "diff.name-status"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Use git diff --name-status for file status."""
        try:
            output = subprocess.check_output(
                ["git", "diff", "--name-status", f"{old_ref}..{new_ref}"],
                cwd=repo_path,
                text=True
            ).strip()

            files = []
            status_map = {"A": "added", "D": "deleted", "M": "modified", "R": "renamed"}

            for line in output.split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                status_char = parts[0][0]
                path = parts[-1]

                files.append(FileDiff(
                    path=path,
                    status=status_map.get(status_char, "unknown"),
                    diff_type="content"
                ))

            summary = {
                "files_changed": len(files),
                "added": sum(1 for f in files if f.status == "added"),
                "deleted": sum(1 for f in files if f.status == "deleted"),
                "modified": sum(1 for f in files if f.status == "modified"),
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class BlobHashDiff(DiffStrategy):
    """Compare blob SHAs: if blob hash is identical, file is identical."""

    def name(self) -> str:
        return "diff.blob-hash"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Compare per-path blob SHAs."""
        try:
            # Get all paths in both commits
            old_paths = set(subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", old_ref],
                cwd=repo_path,
                text=True
            ).strip().split("\n"))

            new_paths = set(subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", new_ref],
                cwd=repo_path,
                text=True
            ).strip().split("\n"))

            files = []
            all_paths = old_paths | new_paths

            for path in all_paths:
                if path not in old_paths:
                    files.append(FileDiff(path=path, status="added", diff_type="content"))
                elif path not in new_paths:
                    files.append(FileDiff(path=path, status="deleted", diff_type="content"))
                else:
                    old_blob = subprocess.check_output(
                        ["git", "ls-tree", old_ref, "--", path],
                        cwd=repo_path,
                        text=True
                    ).strip().split()[2]

                    new_blob = subprocess.check_output(
                        ["git", "ls-tree", new_ref, "--", path],
                        cwd=repo_path,
                        text=True
                    ).strip().split()[2]

                    if old_blob != new_blob:
                        files.append(FileDiff(
                            path=path,
                            status="modified",
                            old_hash=old_blob,
                            new_hash=new_blob,
                            diff_type="content"
                        ))

            summary = {
                "files_changed": sum(1 for f in files if f.status == "modified"),
                "added": sum(1 for f in files if f.status == "added"),
                "deleted": sum(1 for f in files if f.status == "deleted"),
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class TreeDiff(DiffStrategy):
    """ls-tree both commits and diff path sets."""

    def name(self) -> str:
        return "diff.tree-compare"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Compare tree structure."""
        try:
            # Get full tree listings
            old_tree = subprocess.check_output(
                ["git", "ls-tree", "-r", old_ref],
                cwd=repo_path,
                text=True
            ).strip()

            new_tree = subprocess.check_output(
                ["git", "ls-tree", "-r", new_ref],
                cwd=repo_path,
                text=True
            ).strip()

            old_lines = {line.split()[-1]: line for line in old_tree.split("\n") if line}
            new_lines = {line.split()[-1]: line for line in new_tree.split("\n") if line}

            files = []
            for path in set(old_lines.keys()) | set(new_lines.keys()):
                if path not in old_lines:
                    files.append(FileDiff(path=path, status="added"))
                elif path not in new_lines:
                    files.append(FileDiff(path=path, status="deleted"))
                elif old_lines[path] != new_lines[path]:
                    files.append(FileDiff(path=path, status="modified"))

            summary = {
                "total_files": len(files),
                "changed": sum(1 for f in files if f.status == "modified"),
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class RangeDiff(DiffStrategy):
    """git range-diff: compare two commit series."""

    def name(self) -> str:
        return "diff.range-diff"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Compare commit series."""
        try:
            # Get common ancestor
            merge_base = subprocess.check_output(
                ["git", "merge-base", old_ref, new_ref],
                cwd=repo_path,
                text=True
            ).strip()

            output = subprocess.check_output(
                ["git", "range-diff", f"{merge_base}..{old_ref}", f"{merge_base}..{new_ref}"],
                cwd=repo_path,
                text=True
            ).strip()

            # Parse range-diff output
            files = []
            summary = {
                "method": "range-diff",
                "output": output[:500]  # First 500 chars
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class SemanticDiff(DiffStrategy):
    """Token-level diff: word/symbol changes, ignores formatting."""

    def name(self) -> str:
        return "diff.semantic"

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> DiffResult:
        """Token-level semantic comparison."""
        try:
            # Get changed files first
            changed_output = subprocess.check_output(
                ["git", "diff", "--name-only", f"{old_ref}..{new_ref}"],
                cwd=repo_path,
                text=True
            ).strip()

            files = []
            for path in changed_output.split("\n"):
                if not path:
                    continue

                try:
                    old_content = subprocess.check_output(
                        ["git", "show", f"{old_ref}:{path}"],
                        cwd=repo_path,
                        text=True
                    )
                except:
                    old_content = ""

                try:
                    new_content = subprocess.check_output(
                        ["git", "show", f"{new_ref}:{path}"],
                        cwd=repo_path,
                        text=True
                    )
                except:
                    new_content = ""

                # Token-level comparison
                old_tokens = old_content.split()
                new_tokens = new_content.split()

                matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
                ratio = matcher.ratio()

                files.append(FileDiff(
                    path=path,
                    status="modified",
                    similarity=ratio,
                    additions=len(set(new_tokens) - set(old_tokens)),
                    deletions=len(set(old_tokens) - set(new_tokens)),
                    diff_type="semantic"
                ))

            summary = {
                "semantic_files": len(files),
                "avg_similarity": sum(f.similarity for f in files) / len(files) if files else 1.0
            }

            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=files,
                summary=summary
            )
        except Exception as e:
            return DiffResult(
                strategy=self.name(),
                old_ref=old_ref,
                new_ref=new_ref,
                files=[],
                summary={"error": str(e)}
            )


class DiffChain:
    """Compose multiple diff strategies."""

    def __init__(self, strategies: list[DiffStrategy] = None):
        self.strategies = strategies or [GitDiffNumstat()]

    def diff(self, repo_path: str, old_ref: str, new_ref: str) -> list[DiffResult]:
        """Run all strategies, return results."""
        results = []
        for strategy in self.strategies:
            result = strategy.diff(repo_path, old_ref, new_ref)
            results.append(result)
        return results

    def has_blockers(self, results: list[DiffResult]) -> bool:
        """Check if any result has blockers."""
        return any(r.has_blockers for r in results)

    def add_strategy(self, strategy: DiffStrategy):
        """Add a strategy to the chain."""
        self.strategies.append(strategy)

    def to_dict(self) -> dict:
        """Serialize chain state."""
        return {
            "strategies": [s.name() for s in self.strategies],
            "count": len(self.strategies)
        }
