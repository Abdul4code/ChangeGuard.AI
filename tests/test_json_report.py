"""Tests for JSON report generation."""

from __future__ import annotations

from pathlib import Path

from app.analyzers.test_gap_detector import GapAnalysis
from app.collectors.git_diff_collector import ChangedFileStat
from app.reports.json_report import build_json_report, build_report_path
from app.risk.risk_scoring import RiskScore


def _make_change(path: str, added: int, removed: int) -> ChangedFileStat:
    return ChangedFileStat(
        path=path,
        added=added,
        removed=removed,
        change_type="M",
        old_path=None,
    )


def test_build_report_path_sanitizes_refs(tmp_path: Path):
    report_path = build_report_path(tmp_path, "feature/one", "bugfix:two")

    assert report_path.name == "changeguard_report_feature-one..bugfix-two.json"
    assert report_path.parent == tmp_path / "reports"


def test_build_json_report_has_expected_sections(tmp_path: Path):
    changes = [_make_change("src/app.py", 2, 1)]
    categories = {"api": ["src/app.py"]}
    test_gap = GapAnalysis(
        missing_tests=False,
        changed_test_files=[],
        changed_prod_files=["src/app.py"],
        related_tests={},
    )
    risk = RiskScore(
        score=20,
        level="Low",
        factors=["Lines changed (3) (+10)"],
        breakdown={"size": 10},
    )

    report = build_json_report(
        repo_root=tmp_path,
        base_ref="main",
        head_ref="feature",
        changes=changes,
        categories=categories,
        test_gap=test_gap,
        risk=risk,
    )

    assert report["schema_version"] == "1.0"
    assert report["metadata"]["base_ref"] == "main"
    assert report["metadata"]["head_ref"] == "feature"
    assert report["signals"]["changed_files"] == ["src/app.py"]
    assert report["signals"]["categories"]["api"] == ["src/app.py"]
    assert report["risk"]["score"] == 20
