"""Tests for the git diff collector.

These tests validate the collector's ability to extract changed files,
handle errors gracefully, and work with real git repositories.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import git
import pytest

from app.collectors.git_diff_collector import (
    BadRefError,
    GitCommandError,
    InvalidRepoError,
    RepoNotCleanError,
    collect_changed_files,
    collect_changed_file_stats,
)


def _init_repo(repo_path: str) -> git.Repo:
    """Initialize a git repository with a predictable default branch."""
    try:
        repo = git.Repo.init(repo_path, initial_branch="main")
    except TypeError:
        repo = git.Repo.init(repo_path)
        repo.git.checkout("-b", "main")

    return repo


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository with initial commit and two branches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _init_repo(tmpdir)

        # Configure user for commits
        with repo.config_writer() as git_config:
            git_config.set_value("user", "name", "Test User")
            git_config.set_value("user", "email", "test@example.com")

        # Create initial commit on main
        main_file = Path(tmpdir) / "main.py"
        main_file.write_text("# Main file\n")
        repo.index.add([str(main_file)])
        repo.index.commit("Initial commit")

        default_branch = repo.active_branch.name

        # Create feature branch with changes
        feature_branch = repo.create_head("feature/test")
        feature_branch.checkout()

        # Add new file
        feature_file = Path(tmpdir) / "feature.py"
        feature_file.write_text("# Feature file\n")
        repo.index.add([str(feature_file)])

        # Modify existing file
        main_file.write_text("# Main file modified\n")
        repo.index.add([str(main_file)])

        repo.index.commit("Add feature changes")

        # Switch back to default branch for testing
        repo.git.checkout(default_branch)

        try:
            yield tmpdir, default_branch
        finally:
            repo.close()


def test_collect_changed_files_success(temp_git_repo):
    """Test successful collection of changed files between two refs."""
    repo_path, base_branch = temp_git_repo
    changed_files = collect_changed_files(repo_path, base_branch, "feature/test")

    assert isinstance(changed_files, list)
    assert "feature.py" in changed_files
    assert "main.py" in changed_files
    assert len(changed_files) == 2
    # Verify sorted
    assert changed_files == sorted(changed_files)


def test_collect_changed_files_no_changes(temp_git_repo):
    """Test collection when comparing a branch to itself."""
    repo_path, base_branch = temp_git_repo
    changed_files = collect_changed_files(repo_path, base_branch, base_branch)
    assert changed_files == []


def test_collect_changed_file_stats_counts(temp_git_repo):
    """Test per-file line counts between two refs."""
    repo_path, base_branch = temp_git_repo
    stats = collect_changed_file_stats(repo_path, base_branch, "feature/test")
    stats_by_path = {stat.path: stat for stat in stats}

    assert stats_by_path["feature.py"].added == 1
    assert stats_by_path["feature.py"].removed == 0
    assert stats_by_path["feature.py"].change_type == "A"

    assert stats_by_path["main.py"].added == 1
    assert stats_by_path["main.py"].removed == 1
    assert stats_by_path["main.py"].change_type == "M"


def test_collect_changed_file_stats_rename():
    """Test that rename metadata is captured for file moves."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _init_repo(tmpdir)

        with repo.config_writer() as git_config:
            git_config.set_value("user", "name", "Test User")
            git_config.set_value("user", "email", "test@example.com")

        old_file = Path(tmpdir) / "old.py"
        old_file.write_text("# Old file\n")
        repo.index.add([str(old_file)])
        repo.index.commit("Add old file")

        repo.git.mv(str(old_file), str(Path(tmpdir) / "new.py"))
        repo.index.commit("Rename old file")

        try:
            stats = collect_changed_file_stats(tmpdir, "HEAD~1", "HEAD")
        finally:
            repo.close()

        assert len(stats) == 1
        assert stats[0].path == "new.py"
        assert stats[0].old_path == "old.py"
        assert stats[0].change_type == "R"


def test_invalid_repo_path():
    """Test that InvalidRepoError is raised for non-existent path."""
    with pytest.raises(InvalidRepoError):
        collect_changed_files("/nonexistent/path", "main", "head")


def test_invalid_repo_not_git():
    """Test that InvalidRepoError is raised for non-git directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(InvalidRepoError):
            collect_changed_files(tmpdir, "main", "head")


def test_bad_base_ref(temp_git_repo):
    """Test that BadRefError is raised for non-existent base ref."""
    repo_path, _ = temp_git_repo
    with pytest.raises(BadRefError):
        collect_changed_files(repo_path, "nonexistent-ref", "feature/test")


def test_bad_head_ref(temp_git_repo):
    """Test that BadRefError is raised for non-existent head ref."""
    repo_path, base_branch = temp_git_repo
    with pytest.raises(BadRefError):
        collect_changed_files(repo_path, base_branch, "nonexistent-ref")


def test_repo_with_uncommitted_changes():
    """Test that RepoNotCleanError is raised when repo has uncommitted changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = git.Repo.init(tmpdir)

        with repo.config_writer() as git_config:
            git_config.set_value("user", "name", "Test User")
            git_config.set_value("user", "email", "test@example.com")

        # Create initial commit
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("# Test\n")
        repo.index.add([str(test_file)])
        repo.index.commit("Initial commit")

        # Modify file but don't commit
        test_file.write_text("# Test modified\n")

        try:
            # Should raise RepoNotCleanError
            with pytest.raises(RepoNotCleanError):
                collect_changed_files(tmpdir, "HEAD~0", "HEAD")
        finally:
            repo.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
