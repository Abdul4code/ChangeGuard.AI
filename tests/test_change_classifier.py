"""Tests for the change classifier.

These tests verify deterministic category inference and file matching.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.analyzers.change_classifier import classify_changed_files, get_enabled_categories


def _write_file(root: Path, relative_path: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test\n")


def test_enabled_categories_use_repo_evidence():
    """Categories with repo evidence should be enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "auth/login.py")
        _write_file(root, "config/settings.yaml")
        _write_file(root, "src/app.py")

        enabled = get_enabled_categories(root)

    assert "auth" in enabled
    assert "config" in enabled
    assert "payments" not in enabled


def test_classify_changed_files_matches_enabled_categories():
    """Changed files should map to enabled categories only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "auth/login.py")
        _write_file(root, "config/settings.yaml")

        changes = ["auth/login.py", "config/settings.yaml", "src/app.py"]
        classified = classify_changed_files(root, changes)

    assert classified["auth"] == ["auth/login.py"]
    assert classified["config"] == ["config/settings.yaml"]
    assert "payments" not in classified


def test_config_can_enable_category_without_evidence():
    """Config can force-enable categories without repo evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "src/app.py")
        (root / "changeguard.categories.toml").write_text(
            """
    [categories.payments]
    enabled = true
    patterns = ["**/billing/**"]
    """.strip()
        )

        enabled = get_enabled_categories(root)

    assert "payments" in enabled
