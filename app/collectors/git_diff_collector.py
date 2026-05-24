"""Git diff collector for ChangeGuard local PR analysis.

This module extracts the list of changed files between two git references.
It intentionally returns file names only, not full diffs. Classification
and detailed analysis happen in downstream analyzer modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import git


class GitDiffCollectorError(Exception):
    """Base exception for git diff collection errors."""

    pass


class InvalidRepoError(GitDiffCollectorError):
    """Raised when the repository path is invalid or not a git repository."""

    pass


class BadRefError(GitDiffCollectorError):
    """Raised when a git reference does not exist."""

    pass


class GitCommandError(GitDiffCollectorError):
    """Raised when a git command fails."""

    pass


class RepoNotCleanError(GitDiffCollectorError):
    """Raised when the repository is not in a clean state."""

    pass


@dataclass(frozen=True)
class ChangedFileStat:
    """Represents per-file change statistics between two git references.

    Attributes:
        path: The primary file path for the change. For renames, this is the
            new path.
        added: The number of added lines, or None for binary changes.
        removed: The number of removed lines, or None for binary changes.
        change_type: The git change type (A, M, D, R, C, T, U).
        old_path: The original path for renames or copies, when available.
    """

    path: str
    added: Optional[int]
    removed: Optional[int]
    change_type: str
    old_path: Optional[str] = None


def _resolve_repo(repo_path: str | Path) -> git.Repo:
    repo_path = Path(repo_path).expanduser().resolve()

    if not repo_path.exists():
        raise InvalidRepoError(f"Repository path does not exist: {repo_path}")

    try:
        return git.Repo(repo_path)
    except git.InvalidGitRepositoryError as e:
        raise InvalidRepoError(
            f"Path is not a valid git repository: {repo_path}"
        ) from e
    except git.NoSuchPathError as e:
        raise InvalidRepoError(f"Repository path error: {repo_path}") from e


def _ensure_repo_clean(repo: git.Repo, repo_path: Path) -> None:
    try:
        if repo.is_dirty():
            raise RepoNotCleanError(
                f"Repository has uncommitted changes: {repo_path}"
            )
        if repo.head.is_detached:
            return
    except Exception as e:
        if isinstance(e, RepoNotCleanError):
            raise
        raise GitCommandError(f"Failed to check repo status: {e}") from e


def _resolve_commits(
    repo: git.Repo, base_ref: str, head_ref: str
) -> tuple[git.Commit, git.Commit]:
    try:
        return repo.commit(base_ref), repo.commit(head_ref)
    except git.BadName as e:
        raise BadRefError(
            "Git reference not found. "
            f"Check base_ref='{base_ref}' and head_ref='{head_ref}'"
        ) from e
    except Exception as e:
        raise GitCommandError(f"Failed to resolve git references: {e}") from e


def _parse_name_status(output: str) -> dict[str, ChangedFileStat]:
    stats_by_path: dict[str, ChangedFileStat] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        change_type = status[0]
        if change_type in {"R", "C"}:
            if len(parts) < 3:
                continue
            old_path, new_path = parts[1], parts[2]
            stats_by_path[new_path] = ChangedFileStat(
                path=new_path,
                added=None,
                removed=None,
                change_type=change_type,
                old_path=old_path,
            )
        else:
            if len(parts) < 2:
                continue
            path = parts[1]
            stats_by_path[path] = ChangedFileStat(
                path=path,
                added=None,
                removed=None,
                change_type=change_type,
                old_path=None,
            )

    return stats_by_path


def _extract_rename_path(path_raw: str) -> str:
    arrow = "=>" if "=>" in path_raw else "->"
    if "{" in path_raw and "}" in path_raw:
        prefix = path_raw[: path_raw.index("{")]
        suffix = path_raw[path_raw.rindex("}") + 1 :]
        inner = path_raw[path_raw.index("{") + 1 : path_raw.rindex("}")]
        before, after = [part.strip() for part in inner.split(arrow, 1)]
        return f"{prefix}{after}{suffix}"

    return path_raw.split(arrow, 1)[1].strip()


def _parse_numstat(output: str) -> dict[str, tuple[Optional[int], Optional[int]]]:
    stats: dict[str, tuple[Optional[int], Optional[int]]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, removed_raw = parts[0], parts[1]
        path_raw = "\t".join(parts[2:])
        added = None if added_raw == "-" else int(added_raw)
        removed = None if removed_raw == "-" else int(removed_raw)
        path = (
            _extract_rename_path(path_raw)
            if "=>" in path_raw or "->" in path_raw
            else path_raw
        )
        stats[path] = (added, removed)

    return stats


def collect_changed_files(
    repo_path: str | Path, base_ref: str, head_ref: str
) -> List[str]:
    """Collect the list of changed files between two git references.

    Validates the repository and references, then returns a sorted list of
    file paths that differ between base_ref and head_ref. Paths are relative
    to the repository root.

    Args:
        repo_path: Absolute or relative path to the git repository.
        base_ref: Base git reference (e.g., "main", "develop", commit SHA).
        head_ref: Head git reference (e.g., "feature/xyz", commit SHA).

    Returns:
        List[str]: Sorted list of changed file paths relative to repo root.

    Raises:
        InvalidRepoError: If repo_path does not exist or is not a git repo.
        BadRefError: If base_ref or head_ref do not exist.
        GitCommandError: If a git operation fails.
        RepoNotCleanError: If the repo has uncommitted changes or merge conflicts.
    """
    repo_path = Path(repo_path).expanduser().resolve()
    repo = _resolve_repo(repo_path)
    _ensure_repo_clean(repo, repo_path)
    base_commit, head_commit = _resolve_commits(repo, base_ref, head_ref)

    # Collect changed files between base and head
    try:
        diffs = base_commit.diff(head_commit)
        changed_files = sorted([diff.b_path or diff.a_path for diff in diffs if diff.a_path or diff.b_path])
    except Exception as e:
        raise GitCommandError(
            f"Failed to compute diff between {base_ref} and {head_ref}: {e}"
        ) from e

    return changed_files


def collect_changed_file_stats(
    repo_path: str | Path, base_ref: str, head_ref: str
) -> List[ChangedFileStat]:
    """Collect per-file change statistics between two git references.

    Returns a sorted list of ChangedFileStat entries, including added/removed
    line counts and rename metadata when available.

    Args:
        repo_path: Absolute or relative path to the git repository.
        base_ref: Base git reference (e.g., "main", "develop", commit SHA).
        head_ref: Head git reference (e.g., "feature/xyz", commit SHA).

    Returns:
        List[ChangedFileStat]: Sorted list of per-file change stats.

    Raises:
        InvalidRepoError: If repo_path does not exist or is not a git repo.
        BadRefError: If base_ref or head_ref do not exist.
        GitCommandError: If a git operation fails.
        RepoNotCleanError: If the repo has uncommitted changes or merge conflicts.
    """
    repo_path = Path(repo_path).expanduser().resolve()
    repo = _resolve_repo(repo_path)
    _ensure_repo_clean(repo, repo_path)
    _resolve_commits(repo, base_ref, head_ref)

    try:
        name_status_output = repo.git.diff(
            base_ref, head_ref, name_status=True, find_renames=True
        )
        numstat_output = repo.git.diff(
            base_ref, head_ref, numstat=True, find_renames=True
        )
    except Exception as e:
        raise GitCommandError(
            f"Failed to compute diff stats between {base_ref} and {head_ref}: {e}"
        ) from e

    stats_by_path = _parse_name_status(name_status_output)
    numstat = _parse_numstat(numstat_output)

    for path, (added, removed) in numstat.items():
        if path in stats_by_path:
            entry = stats_by_path[path]
            stats_by_path[path] = ChangedFileStat(
                path=entry.path,
                added=added,
                removed=removed,
                change_type=entry.change_type,
                old_path=entry.old_path,
            )
        else:
            stats_by_path[path] = ChangedFileStat(
                path=path,
                added=added,
                removed=removed,
                change_type="M",
                old_path=None,
            )

    return sorted(stats_by_path.values(), key=lambda stat: stat.path)
