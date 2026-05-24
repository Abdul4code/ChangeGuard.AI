"""Git diff collector for ChangeGuard local PR analysis.

This module extracts the list of changed files between two git references.
It intentionally returns file names only, not full diffs. Classification
and detailed analysis happen in downstream analyzer modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

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

    # Validate repo exists and is a git repository
    if not repo_path.exists():
        raise InvalidRepoError(f"Repository path does not exist: {repo_path}")

    try:
        repo = git.Repo(repo_path)
    except git.InvalidGitRepositoryError as e:
        raise InvalidRepoError(
            f"Path is not a valid git repository: {repo_path}"
        ) from e
    except git.NoSuchPathError as e:
        raise InvalidRepoError(f"Repository path error: {repo_path}") from e

    # Validate repo is clean (no uncommitted changes, no merge conflicts)
    try:
        if repo.is_dirty():
            raise RepoNotCleanError(
                f"Repository has uncommitted changes: {repo_path}"
            )
        if repo.head.is_detached:
            pass  # Detached HEAD is okay for analysis
    except Exception as e:
        if isinstance(e, RepoNotCleanError):
            raise
        raise GitCommandError(f"Failed to check repo status: {e}") from e

    # Validate base_ref and head_ref exist
    try:
        base_commit = repo.commit(base_ref)
        head_commit = repo.commit(head_ref)
    except git.BadName as e:
        raise BadRefError(
            f"Git reference not found. Check base_ref='{base_ref}' and head_ref='{head_ref}'"
        ) from e
    except Exception as e:
        raise GitCommandError(f"Failed to resolve git references: {e}") from e

    # Collect changed files between base and head
    try:
        diffs = base_commit.diff(head_commit)
        changed_files = sorted([diff.b_path or diff.a_path for diff in diffs if diff.a_path or diff.b_path])
    except Exception as e:
        raise GitCommandError(
            f"Failed to compute diff between {base_ref} and {head_ref}: {e}"
        ) from e

    return changed_files
