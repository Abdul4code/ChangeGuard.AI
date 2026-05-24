"""Structured JSON report generation for ChangeGuard AI.

This module builds and writes deterministic JSON reports for local PR analysis.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.analyzers.test_gap_detector import GapAnalysis
from app.collectors.git_diff_collector import ChangedFileStat
from app.risk.risk_scoring import RiskScore

SCHEMA_VERSION = "1.0"
DEFAULT_REPORTS_DIR = "reports"
DEFAULT_REPORT_PREFIX = "changeguard_report_"


def _sanitize_ref(ref: str) -> str:
    safe = []
    for char in ref.strip():
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe) or "unknown"


def build_report_path(repo_root: str | Path, base_ref: str, head_ref: str) -> Path:
    """Build the default report path using base and head refs.

    Args:
        repo_root: Root path of the repository.
        base_ref: Base git ref.
        head_ref: Head git ref.

    Returns:
        Path: Report path under the reports directory.
    """
    base_safe = _sanitize_ref(base_ref)
    head_safe = _sanitize_ref(head_ref)
    filename = f"{DEFAULT_REPORT_PREFIX}{base_safe}..{head_safe}.json"
    return Path(repo_root) / DEFAULT_REPORTS_DIR / filename


def _serialize_change_stats(changes: list[ChangedFileStat]) -> list[dict[str, object]]:
    return [
        {
            "path": change.path,
            "added": change.added,
            "removed": change.removed,
            "change_type": change.change_type,
            "old_path": change.old_path,
        }
        for change in changes
    ]


def _total_lines(changes: list[ChangedFileStat]) -> int:
    total = 0
    for change in changes:
        if change.added is None or change.removed is None:
            continue
        total += change.added + change.removed
    return total


def build_json_report(
    repo_root: str | Path,
    base_ref: str,
    head_ref: str,
    changes: list[ChangedFileStat],
    categories: dict[str, list[str]],
    test_gap: GapAnalysis,
    risk: RiskScore,
) -> dict[str, object]:
    """Build the structured JSON report payload.

    Args:
        repo_root: Root path of the repository.
        base_ref: Base git ref.
        head_ref: Head git ref.
        changes: List of per-file change statistics.
        categories: Mapping of category name to matching file paths.
        test_gap: Missing-test analysis results.
        risk: Risk scoring results.

    Returns:
        dict[str, object]: JSON-serializable report payload.
    """
    repo_root_path = Path(repo_root).expanduser().resolve()
    changed_files = sorted({change.path for change in changes})
    totals = {
        "files_changed": len(changed_files),
        "lines_changed": _total_lines(changes),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo_root": repo_root_path.as_posix(),
            "base_ref": base_ref,
            "head_ref": head_ref,
        },
        "signals": {
            "changed_files": changed_files,
            "file_stats": _serialize_change_stats(changes),
            "categories": categories,
            "test_gap": asdict(test_gap),
            "totals": totals,
        },
        "risk": asdict(risk),
    }


def write_json_report(report: dict[str, object], output_path: str | Path) -> Path:
    """Write the JSON report to disk.

    Args:
        report: JSON-serializable report payload.
        output_path: Path for the JSON report file.

    Returns:
        Path: Resolved path to the written report.
    """
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path
