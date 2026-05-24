"""Tests for the test gap detector.

These tests validate missing-test detection and related test suggestions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.analyzers.test_gap_detector import detect_missing_or_related_tests


def _write_file(root: Path, relative_path: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test\n")


def test_missing_tests_when_no_tests_changed():
    """Production changes without tests should flag missing tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "src/foo.py")
        _write_file(root, "tests/test_foo.py")

        analysis = detect_missing_or_related_tests(root, ["src/foo.py"])

    assert analysis.missing_tests is True
    assert analysis.changed_test_files == []
    assert analysis.changed_prod_files == ["src/foo.py"]
    assert analysis.related_tests["src/foo.py"] == ["tests/test_foo.py"]


def test_no_missing_when_tests_changed():
    """Production changes with test updates should not flag missing tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "src/foo.py")
        _write_file(root, "tests/test_foo.py")

        analysis = detect_missing_or_related_tests(
            root, ["src/foo.py", "tests/test_foo.py"]
        )

    assert analysis.missing_tests is False
    assert analysis.changed_test_files == ["tests/test_foo.py"]
    assert analysis.changed_prod_files == ["src/foo.py"]


def test_related_tests_from_name_match():
    """Related tests should be suggested by name heuristics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "app/payments/charge.py")
        _write_file(root, "tests/payments/test_charge.py")

        analysis = detect_missing_or_related_tests(root, ["app/payments/charge.py"])

    assert analysis.related_tests["app/payments/charge.py"] == [
        "tests/payments/test_charge.py"
    ]


def test_infers_nonstandard_test_root_from_name():
    """Inference should detect nonstandard test roots by filename pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "lib/widget.py")
        _write_file(root, "specs/unit/test_widget.py")

        analysis = detect_missing_or_related_tests(root, ["lib/widget.py"])

    assert analysis.related_tests["lib/widget.py"] == [
        "specs/unit/test_widget.py"
    ]


def test_config_overrides_test_and_source_roots():
    """Config should override inferred source and test roots."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_file(root, "backend/core/task.py")
        _write_file(root, "qa/specs/test_task.py")
        (root / "changeguard.tests.toml").write_text(
            """
[tests]
source_roots = ["backend"]
test_roots = ["qa/specs"]
""".strip()
        )

        analysis = detect_missing_or_related_tests(root, ["backend/core/task.py"])

    assert analysis.related_tests["backend/core/task.py"] == [
        "qa/specs/test_task.py"
    ]
