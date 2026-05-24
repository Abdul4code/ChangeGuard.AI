"""Change classifier for deterministic domain labeling.

This module maps changed file paths to domain categories using deterministic
rules. It supports optional per-repository overrides via a TOML config file
while suppressing categories with no evidence in the repo by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

import tomllib

from app.collectors.git_diff_collector import ChangedFileStat

DEFAULT_CATEGORY_CONFIG_NAME = "changeguard.categories.toml"

DEFAULT_RULES: Mapping[str, tuple[str, ...]] = {
    "api": (
        "api/**",
        "**/api/**",
        "apis/**",
        "**/apis/**",
        "routes/**",
        "**/routes/**",
        "router/**",
        "**/router/**",
        "controllers/**",
        "**/controllers/**",
        "handlers/**",
        "**/handlers/**",
        "**/*openapi*.*",
        "**/*swagger*.*",
    ),
    "auth": (
        "auth/**",
        "**/auth/**",
        "**/*auth*.*",
        "login/**",
        "**/login/**",
        "logout/**",
        "**/logout/**",
        "oauth/**",
        "**/oauth/**",
        "sso/**",
        "**/sso/**",
        "saml/**",
        "**/saml/**",
        "**/*jwt*.*",
        "**/*session*.*",
        "**/*identity*.*",
    ),
    "config": (
        "config/**",
        "**/config/**",
        "configs/**",
        "**/configs/**",
        "settings/**",
        "**/settings/**",
        "**/*config*.*",
        "**/*.env",
        "**/*.env.*",
        "**/*.toml",
        "**/*.yaml",
        "**/*.yml",
        "**/*.json",
    ),
    "database": (
        "db/**",
        "**/db/**",
        "database/**",
        "**/database/**",
        "migrations/**",
        "**/migrations/**",
        "schema/**",
        "**/schema/**",
        "**/*schema*.*",
        "**/*migration*.*",
        "**/*model*.*",
        "**/*.sql",
    ),
    "infrastructure": (
        ".github/**",
        "**/.github/**",
        ".circleci/**",
        "**/.circleci/**",
        ".gitlab/**",
        "**/.gitlab/**",
        "ci/**",
        "**/ci/**",
        "pipelines/**",
        "**/pipelines/**",
        "infra/**",
        "**/infra/**",
        "infrastructure/**",
        "**/infrastructure/**",
        "terraform/**",
        "**/terraform/**",
        "helm/**",
        "**/helm/**",
        "k8s/**",
        "**/k8s/**",
        "kubernetes/**",
        "**/kubernetes/**",
        "docker/**",
        "**/docker/**",
        "dockerfile",
        "**/dockerfile",
        "docker-compose.*",
        "**/docker-compose.*",
    ),
    "payments": (
        "payment/**",
        "**/payment/**",
        "payments/**",
        "**/payments/**",
        "billing/**",
        "**/billing/**",
        "invoice/**",
        "**/invoice/**",
        "invoices/**",
        "**/invoices/**",
        "**/*stripe*.*",
        "**/*paypal*.*",
    ),
    "tests": (
        "tests/**",
        "**/tests/**",
        "test/**",
        "**/test/**",
        "**/*test*.*",
        "**/*spec*.*",
    ),
}

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
class CategoryRule:
    """Represents a deterministic classification rule for a category.

    Attributes:
        name: The category name.
        patterns: Glob-style patterns evaluated against repo-relative paths.
        enabled: Whether the category is enabled after evidence and config.
    """

    name: str
    patterns: tuple[str, ...]
    enabled: bool


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


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in patterns)


def _load_category_config(repo_root: Path) -> Mapping[str, dict[str, object]]:
    config_path = repo_root / DEFAULT_CATEGORY_CONFIG_NAME
    if not config_path.exists():
        return {}

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    categories = raw.get("categories", {})
    if not isinstance(categories, dict):
        return {}

    return categories


def _build_rules(repo_root: Path) -> list[CategoryRule]:
    repo_files = _iter_repo_files(repo_root)
    config = _load_category_config(repo_root)

    rules: list[CategoryRule] = []

    for name, patterns in DEFAULT_RULES.items():
        settings = config.get(name, {})
        enabled_setting = settings.get("enabled") if isinstance(settings, dict) else None
        pattern_override = settings.get("patterns") if isinstance(settings, dict) else None

        if isinstance(pattern_override, list) and pattern_override:
            patterns = tuple(str(pattern) for pattern in pattern_override)

        has_evidence = any(_matches_any(path, patterns) for path in repo_files)

        if enabled_setting is True:
            enabled = True
        elif enabled_setting is False:
            enabled = False
        else:
            enabled = has_evidence

        rules.append(CategoryRule(name=name, patterns=patterns, enabled=enabled))

    for name, settings in config.items():
        if name in DEFAULT_RULES or not isinstance(settings, dict):
            continue
        patterns = settings.get("patterns", [])
        if not patterns:
            continue
        enabled_setting = settings.get("enabled")
        has_evidence = any(
            _matches_any(path, patterns) for path in repo_files
        )
        if enabled_setting is True:
            enabled = True
        elif enabled_setting is False:
            enabled = False
        else:
            enabled = has_evidence

        rules.append(
            CategoryRule(
                name=name,
                patterns=tuple(str(pattern) for pattern in patterns),
                enabled=enabled,
            )
        )

    return rules


def get_enabled_categories(repo_root: str | Path) -> list[str]:
    """Return categories enabled for a repository based on evidence and config.

    Args:
        repo_root: Root path of the repository.

    Returns:
        List[str]: Category names that are enabled.
    """
    root = Path(repo_root).expanduser().resolve()
    return sorted([rule.name for rule in _build_rules(root) if rule.enabled])


def classify_changed_files(
    repo_root: str | Path, changes: Iterable[str | ChangedFileStat]
) -> dict[str, list[str]]:
    """Classify changed files into enabled categories.

    Args:
        repo_root: Root path of the repository.
        changes: Iterable of repo-relative paths or ChangedFileStat entries.

    Returns:
        dict[str, list[str]]: Mapping of category name to sorted file paths.
    """
    root = Path(repo_root).expanduser().resolve()
    rules = [rule for rule in _build_rules(root) if rule.enabled]

    results: dict[str, set[str]] = {rule.name: set() for rule in rules}
    for change in changes:
        path = change.path if isinstance(change, ChangedFileStat) else str(change)
        normalized = _normalize_path(path)
        for rule in rules:
            if _matches_any(normalized, rule.patterns):
                results[rule.name].add(normalized)

    return {
        name: sorted(paths)
        for name, paths in results.items()
        if paths
    }
