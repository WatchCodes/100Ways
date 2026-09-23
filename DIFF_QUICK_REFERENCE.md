# DIFF Category - Quick Reference Guide

## Installation & Import

```python
from hundredways.diff import DiffChain, GitPlumbingDiff, TreeSetDiff

# Initialize DiffChain for a repository
chain = DiffChain("/path/to/git/repo")
```

## Quick Start (5 minutes)

### 1. Get all diffs from all 20 strategies

```python
chain = DiffChain(repo_path)
results = chain.run_all("HEAD~1", "HEAD")

for strategy_name, result in results.items():
    print(f"{strategy_name}: {len(result.entries)} changes")
    if result.error:
        print(f"  Error: {result.error}")
```

### 2. Use a specific strategy

```python
from hundredways.diff import GitPlumbingDiff

strategy = GitPlumbingDiff(repo_path)
result = strategy.diff("commit_a", "commit_b")

for entry in result.entries:
    print(f"{entry.status} {entry.path}")
```

### 3. Filter by file patterns

```python
from hundredways.diff import PathspecLimitedDiff

strategy = PathspecLimitedDiff(repo_path)
strategy.add_pathspec("*.py")
strategy.add_pathspec("src/")

result = strategy.diff("main", "feature")
```

### 4. Detect renames

```python
from hundredways.diff import RenameOnlyDiff

strategy = RenameOnlyDiff(repo_path)
result = strategy.diff("v1.0", "v2.0", threshold=80)  # 80% similarity

for entry in result.entries:
    if entry.status == "R":
        print(f"{entry.old_path} -> {entry.path}")
```

## Common Patterns

### Pattern 1: Analyze Merge Conflicts

```python
from hundredways.diff import ThreeWayMergeDiff

strategy = ThreeWayMergeDiff(repo_path)
result = strategy.diff("feature_branch", "main")

print(f"Merge base: {result.metadata['merge_base']}")
for entry in result.entries:
    if entry.status == "C":  # Conflict
        print(f"Conflict: {entry.path}")
```

### Pattern 2: Monitor Large Changes

```python
strategy = GitPlumbingDiff(repo_path)
result = strategy.diff("old_release", "new_release")

additions = sum(e.added_lines for e in result.entries)
deletions = sum(e.deleted_lines for e in result.entries)
print(f"Total: +{additions} -{deletions} lines")
```

### Pattern 3: Find File Moves

```python
strategy = SequenceMatcherDiff(repo_path)
result = strategy.diff("v1", "v2")

for entry in result.entries:
    if 0 < entry.similarity < 100:
        print(f"Moved: {entry.old_path} -> {entry.path} ({entry.similarity}%)")
```

### Pattern 4: Identify Code Owners

```python
from hundredways.diff import BlameWindowDiff

strategy = BlameWindowDiff(repo_path)
result = strategy.diff("main", "feature")

for entry in result.entries:
    authors = set(entry.blame_info.get("authors", []))
    print(f"{entry.path}: modified by {', '.join(authors)}")
```

## Strategy Selection Guide

### I want to...

**Get basic diff information**
→ Use `GitPlumbingDiff` (most reliable)

**Compare very quickly**
→ Use `TreeSetDiff` (fastest)

**See line-by-line changes**
→ Use `UnifiedDiffParsing`

**Check unstaged work**
→ Use `WorktreeDiff`

**Find renamed files**
→ Use `RenameOnlyDiff` or `SequenceMatcherDiff`

**Analyze branches**
→ Use `MirrorRefCompare` or `CommitCountDelta`

**Detect merge issues**
→ Use `ThreeWayMergeDiff`

**Filter by path patterns**
→ Use `PathspecLimitedDiff` or `NarrowPathspecDiff`

**Track code ownership**
→ Use `BlameWindowDiff`

**Analyze submodules**
→ Use `SubmoduleDiff`

**Check staged changes**
→ Use `StagedTreeDiff`

**Safely handle binary files**
→ Use `BinarySafeDiff`

**Compare against empty state**
→ Use `EmptyTreeDiff`

## API Reference

### DiffChain

```python
chain = DiffChain(repo_path: str)

# Run single strategy
result = chain.run("git_plumbing", commit_a, commit_b)

# Run all strategies
results = chain.run_all(commit_a, commit_b)

# Register custom strategy
chain.register(MyCustomDiff(repo_path))

# List registered strategies
strategies = chain.strategies  # dict
```

### DiffResult

```python
result = strategy.diff(commit_a, commit_b)

result.strategy: str                    # Strategy name
result.commit_a: str                    # First commit
result.commit_b: str                    # Second commit
result.entries: list[DiffEntry]         # File changes
result.metadata: dict                   # Strategy-specific data
result.error: Optional[str]             # Error message if failed
result.timing_ms: float                 # Execution time
```

### DiffEntry

```python
entry.path: str                         # File path
entry.status: str                       # A/M/D/R/C/T/U
entry.old_mode: str                     # Old file mode
entry.new_mode: str                     # New file mode
entry.old_sha: str                      # Old blob SHA
entry.new_sha: str                      # New blob SHA
entry.similarity: int                   # Rename similarity %
entry.old_path: str                     # Old path (renames)
entry.added_lines: int                  # Added line count
entry.deleted_lines: int                # Deleted line count
entry.is_binary: bool                   # Binary file flag
entry.blame_info: dict                  # Author/blame info
```

## Error Handling

```python
result = strategy.diff(commit_a, commit_b)

if result.error:
    print(f"Strategy failed: {result.error}")
    print(f"Partial results: {len(result.entries)} entries")
else:
    # Process entries
    for entry in result.entries:
        print(entry.path)
```

## Performance Tips

**For large repositories:**
- Use `TreeSetDiff` (fastest)
- Use `BatchBlobDiff` (bulk operations)
- Avoid `BlameWindowDiff` (slowest, one per line)

**For many comparisons:**
- Reuse `DiffChain` instance
- Cache strategy objects
- Run strategies in parallel (20 strategies run independently in `run_all()`)

**For filtering:**
- Use `PathspecLimitedDiff` (simple patterns)
- Use `NarrowPathspecDiff` (complex regex)

## Logging

Enable debug logging to see strategy execution:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
# Now run strategies - execution details will be logged
```

## Common Issues & Solutions

**Issue: Empty diff results**
- Verify commit references exist: `git rev-parse commit_a`
- For same commit, result is usually empty (as expected)
- Check if files actually changed between commits

**Issue: Binary files causing problems**
- Use `BinarySafeDiff` strategy
- Or use `git_plumbing` with `is_binary` flag

**Issue: Renames not detected**
- Use `RenameOnlyDiff` with appropriate threshold
- Try `SequenceMatcherDiff` for line-level matching
- Check file similarity: `git diff --find-renames=80%`

**Issue: Slow performance**
- Avoid `BlameWindowDiff` on large diffs
- Use `TreeSetDiff` instead of `UnifiedDiffParsing`
- Cache DiffChain instance across calls

**Issue: Special characters in paths**
- All strategies use null-byte safe parsing
- Should handle correctly
- If issues, file a bug report with example path

## Examples

### Example 1: Daily Report

```python
chain = DiffChain(repo_path)
results = chain.run_all("HEAD~24", "HEAD")

total_additions = 0
total_deletions = 0
files_changed = 0

for name, result in results.items():
    if result.error:
        continue
    files_changed = len(result.entries)
    total_additions = sum(e.added_lines for e in result.entries)
    total_deletions = sum(e.deleted_lines for e in result.entries)

print(f"24-hour summary:")
print(f"  Files: {files_changed}")
print(f"  Added: {total_additions} lines")
print(f"  Deleted: {total_deletions} lines")
```

### Example 2: Merge Safety Check

```python
from hundredways.diff import ThreeWayMergeDiff, BlameWindowDiff

merge_strategy = ThreeWayMergeDiff(repo_path)
merge_result = merge_strategy.diff("feature", "main")

blame_strategy = BlameWindowDiff(repo_path)
blame_result = blame_strategy.diff("main", "feature")

print("Potential conflicts:")
for entry in merge_result.entries:
    if entry.status == "C":
        # Get blame info
        blame_info = [e for e in blame_result.entries if e.path == entry.path]
        if blame_info:
            authors = blame_info[0].blame_info.get("authors", [])
            print(f"  {entry.path}: authors {authors}")
```

### Example 3: Release Checklist

```python
strategy = RenameOnlyDiff(repo_path)
result = strategy.diff("v1.0.0", "v2.0.0")

breaking_changes = []
for entry in result.entries:
    if entry.status == "D":
        breaking_changes.append(("deleted", entry.path))
    elif entry.status == "R" and entry.similarity < 90:
        breaking_changes.append(("renamed", f"{entry.old_path} -> {entry.path}"))

if breaking_changes:
    print("⚠️ Potential breaking changes:")
    for change_type, detail in breaking_changes:
        print(f"  [{change_type}] {detail}")
else:
    print("✅ No breaking changes detected")
```

## Testing Your Integration

```python
import pytest
from hundredways.diff import DiffChain

def test_my_integration():
    chain = DiffChain(test_repo_path)
    result = chain.run("git_plumbing", "commit_a", "commit_b")
    
    assert result.error is None
    assert len(result.entries) > 0
    assert result.timing_ms > 0
    assert all(e.path for e in result.entries)
```

---

**For more details, see:**
- `docs/DIFF.md` - Comprehensive documentation
- `DIFF_IMPLEMENTATION.md` - Implementation details
- `tests/test_diff.py` - Test examples
