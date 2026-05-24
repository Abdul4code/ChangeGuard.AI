"""Test gap detector for deterministic missing-test analysis.

This module flags changes without accompanying tests and suggests related test
files using deterministic path and name heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from app.collectors.git_diff_collector import ChangedFileStat

DEFAULT_TEST_CONFIG_NAME = "changeguard.tests.toml"
DEFAULT_SOURCE_ROOTS = ("src", "app", "lib", "service", "services")
DEFAULT_TEST_DIR_NAMES = ("tests", "test")
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
}


@dataclass(frozen=True)
class GapAnalysis:
    """Represents missing-test analysis for a set of changes.

    Attributes:
        missing_tests: True when production changes have no test changes.
        changed_test_files: Sorted list of changed test files.
        changed_prod_files: Sorted list of changed non-test files.
        related_tests: Mapping from changed non-test file to suggested tests.
    """

    missing_tests: bool
    changed_test_files: list[str]
    changed_prod_files: list[str]
    related_tests: dict[str, list[str]]


def _normalize_path(path: str | Path) -> str:
    return Path(path).as_posix().lstrip("./")


def _iter_repo_files(repo_root: Path) -> list[str]:
    files: list[str] = []
    for path in repo_root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path.relative_to(repo_root).as_posix())

    return files


def _path_in_root(path: str, root: str) -> bool:
    if not root:
        return False
    if path == root:
        return True
    return path.startswith(f"{root}/")


def _is_test_name(path: str) -> bool:
    filename = Path(path).name.lower()
    if filename.startswith("test_"):
        return True
    if filename.startswith("spec_"):
        return True
    if "_test." in filename or "_spec." in filename:
        return True
    return False


def _is_test_file(path: str, test_roots: Iterable[str]) -> bool:
    normalized = _normalize_path(path).lower()
    for root in test_roots:
        if _path_in_root(normalized, root):
            return True
    return _is_test_name(normalized)


def _strip_source_root(path: str, source_roots: Iterable[str]) -> str:
    normalized = _normalize_path(path)
    roots = sorted((root for root in source_roots if root), key=len, reverse=True)
    for root in roots:
        if _path_in_root(normalized, root):
            return normalized[len(root) + 1 :]
    return normalized


def _candidate_test_paths(
    relative_path: str,
    source_roots: Iterable[str],
    test_roots: Iterable[str],
) -> list[str]:
    normalized = _strip_source_root(relative_path, source_roots)
    parts = normalized.split("/")
    if not parts:
        return []
    filename = parts[-1]
    stem = Path(filename).stem
    extension = Path(filename).suffix or ".py"
    parent = "/".join(parts[:-1])

    candidates: list[str] = []
    for test_root in sorted(test_roots):
        prefix = f"{test_root}/{parent}" if parent else test_root
        candidates.extend(
            [
                f"{prefix}/test_{stem}{extension}",
                f"{prefix}/{stem}_test{extension}",
                f"{prefix}/{stem}_spec{extension}",
            ]
        )

    return candidates


def _core_test_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    for prefix in ("test_", "spec_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
    for suffix in ("_test", "_spec"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def _find_related_tests(
    repo_files: Iterable[str],
    prod_path: str,
    source_roots: Iterable[str],
    test_roots: Iterable[str],
) -> list[str]:
    repo_files_set = {file for file in repo_files}
    suggestions: set[str] = set()

    for candidate in _candidate_test_paths(prod_path, source_roots, test_roots):
        if candidate in repo_files_set:
            suggestions.add(candidate)

    prod_stem = Path(prod_path).stem.lower()
    for test_file in repo_files:
        if not _is_test_file(test_file, test_roots):
            continue
        if _core_test_name(test_file) == prod_stem:
            suggestions.add(test_file)
    return sorted(suggestions)
def _load_test_config(repo_root: Path) -> Mapping[str, object]:
    config_path = repo_root / DEFAULT_TEST_CONFIG_NAME
    if not config_path.exists():
        return {}

    import tomllib

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    config = raw.get("tests", {})
    if not isinstance(config, dict):
        return {}

    return config


def _infer_test_roots(repo_files: Iterable[str]) -> list[str]:
    roots: set[str] = set()
    for file in repo_files:
        normalized = _normalize_path(file)
        parts = normalized.split("/")
        for index, part in enumerate(parts):
            if part in DEFAULT_TEST_DIR_NAMES:
                roots.add("/".join(parts[: index + 1]))
        if _is_test_name(normalized):
            parent = "/".join(parts[:-1])
            if parent:
                roots.add(parent)

    if not roots:
        return list(DEFAULT_TEST_DIR_NAMES)

    return sorted(roots)


def _infer_source_roots(
    repo_files: Iterable[str], test_roots: Iterable[str]
) -> list[str]:
    roots: set[str] = set()
    for file in repo_files:
        normalized = _normalize_path(file)
        if _is_test_file(normalized, test_roots):
            continue
        parts = normalized.split("/")
        if parts:
            roots.add(parts[0])

    roots = {root for root in roots if root and root not in IGNORED_DIRS}
    if not roots:
        return list(DEFAULT_SOURCE_ROOTS)

    return sorted(roots)


def _resolve_roots(repo_root: Path, repo_files: Iterable[str]) -> tuple[list[str], list[str]]:
    config = _load_test_config(repo_root)
    configured_test_roots = config.get("test_roots") if config else None
    configured_source_roots = config.get("source_roots") if config else None

    if isinstance(configured_test_roots, list) and configured_test_roots:
        test_roots = [str(root).strip().strip("/") for root in configured_test_roots]
    else:
        test_roots = _infer_test_roots(repo_files)

    if isinstance(configured_source_roots, list) and configured_source_roots:
        source_roots = [
            str(root).strip().strip("/") for root in configured_source_roots
        ]
    else:
        source_roots = _infer_source_roots(repo_files, test_roots)

    test_roots = [root for root in test_roots if root]
    source_roots = [root for root in source_roots if root]

    return source_roots, test_roots


def detect_missing_or_related_tests(
    repo_root: str | Path, changes: Iterable[str | ChangedFileStat]
) -> GapAnalysis:
    """Detect missing tests and suggest related test files.

    Args:
        repo_root: Root path of the repository.
        changes: Iterable of repo-relative paths or ChangedFileStat entries.

    Returns:
        GapAnalysis: Structured missing-test analysis and suggestions.
    """
    root = Path(repo_root).expanduser().resolve()
    repo_files = _iter_repo_files(root)
    source_roots, test_roots = _resolve_roots(root, repo_files)

    normalized_changes: list[str] = []
    for change in changes:
        path = change.path if isinstance(change, ChangedFileStat) else str(change)
        normalized_changes.append(_normalize_path(path))

    changed_test_files = sorted(
        {path for path in normalized_changes if _is_test_file(path, test_roots)}
    )
    changed_prod_files = sorted(
        {path for path in normalized_changes if not _is_test_file(path, test_roots)}
    )

    related_tests = {
        prod_path: _find_related_tests(
            repo_files, prod_path, source_roots, test_roots
        )
        for prod_path in changed_prod_files
    }

    missing_tests = bool(changed_prod_files) and not changed_test_files

    return GapAnalysis(
        missing_tests=missing_tests,
        changed_test_files=changed_test_files,
        changed_prod_files=changed_prod_files,
        related_tests=related_tests,
    )
