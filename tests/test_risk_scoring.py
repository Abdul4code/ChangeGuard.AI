"""Tests for deterministic risk scoring."""

from __future__ import annotations

from app.analyzers.test_gap_detector import GapAnalysis
from app.collectors.git_diff_collector import ChangedFileStat
from app.risk.risk_scoring import calculate_risk_score


def _make_change(path: str, added: int, removed: int) -> ChangedFileStat:
    return ChangedFileStat(
        path=path,
        added=added,
        removed=removed,
        change_type="M",
        old_path=None,
    )


def test_low_risk_small_change():
    changes = [_make_change("src/app.py", 3, 0)]
    categories = {"api": ["src/app.py"]}
    test_gap = GapAnalysis(
        missing_tests=False,
        changed_test_files=[],
        changed_prod_files=["src/app.py"],
        related_tests={},
    )

    result = calculate_risk_score(changes, categories, test_gap)

    assert result.level == "Low"
    assert result.score == 15


def test_high_risk_with_missing_tests_and_large_change():
    changes = [
        _make_change("infra/main.tf", 300, 40),
        _make_change("db/schema.sql", 50, 10),
    ]
    categories = {
        "infrastructure": ["infra/main.tf"],
        "database": ["db/schema.sql"],
    }
    test_gap = GapAnalysis(
        missing_tests=True,
        changed_test_files=[],
        changed_prod_files=["infra/main.tf", "db/schema.sql"],
        related_tests={},
    )

    result = calculate_risk_score(changes, categories, test_gap)

    assert result.level == "High"
    assert result.score == 100
