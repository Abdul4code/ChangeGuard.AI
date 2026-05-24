"""Human-readable Markdown report generation for ChangeGuard AI.

This module builds and writes a Markdown report summarizing change analysis.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.analyzers.test_gap_detector import GapAnalysis
from app.collectors.git_diff_collector import ChangedFileStat
from app.risk.risk_scoring import RiskScore

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


def build_markdown_report_path(
    repo_root: str | Path, base_ref: str, head_ref: str
) -> Path:
    """Build the default Markdown report path using base and head refs.

    Args:
        repo_root: Root path of the repository.
        base_ref: Base git ref.
        head_ref: Head git ref.

    Returns:
        Path: Report path under the reports directory.
    """
    base_safe = _sanitize_ref(base_ref)
    head_safe = _sanitize_ref(head_ref)
    filename = f"{DEFAULT_REPORT_PREFIX}{base_safe}..{head_safe}.md"
    return Path(repo_root) / DEFAULT_REPORTS_DIR / filename


def _total_lines(changes: list[ChangedFileStat]) -> int:
    total = 0
    for change in changes:
        if change.added is None or change.removed is None:
            continue
        total += change.added + change.removed
    return total


def _render_table(rows: list[list[str]], headers: list[str]) -> list[str]:
    if not rows:
        return []
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend(["| " + " | ".join(row) + " |" for row in rows])
    return lines


def _render_categories(categories: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for category, paths in sorted(categories.items()):
        lines.append(f"- {category}: {len(paths)} file(s)")
    return lines


def _render_missing_tests(test_gap: GapAnalysis) -> list[str]:
    lines: list[str] = []
    if not test_gap.missing_tests:
        lines.append("- Tests updated for this change set.")
        return lines

    lines.append("- Missing test updates detected.")
    for prod_path, suggestions in test_gap.related_tests.items():
        if not suggestions:
            continue
        joined = ", ".join(suggestions)
        lines.append(f"  - {prod_path}: {joined}")
    return lines


def _render_factors(factors: list[str]) -> list[str]:
    return [f"- {factor}" for factor in factors] if factors else ["- None"]


def build_markdown_report(
    repo_root: str | Path,
    base_ref: str,
    head_ref: str,
    changes: list[ChangedFileStat],
    categories: dict[str, list[str]],
    test_gap: GapAnalysis,
    risk: RiskScore,
) -> str:
    """Build the Markdown report.

    Args:
        repo_root: Root path of the repository.
        base_ref: Base git ref.
        head_ref: Head git ref.
        changes: List of per-file change statistics.
        categories: Mapping of category name to matching file paths.
        test_gap: Missing-test analysis results.
        risk: Risk scoring results.

    Returns:
        str: Markdown report content.
    """
    repo_root_path = Path(repo_root).expanduser().resolve().as_posix()
    changed_files = sorted({change.path for change in changes})
    total_lines = _total_lines(changes)

    lines: list[str] = []
    lines.append("# ChangeGuard Report")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Repository: {repo_root_path}")
    lines.append(f"- Base ref: {base_ref}")
    lines.append(f"- Head ref: {head_ref}")
    lines.append("")

    lines.append("## Risk")
    lines.append(f"- Score: {risk.score} ({risk.level})")
    lines.extend(_render_factors(risk.factors))
    lines.append("")

    lines.append("## Change Summary")
    lines.append(f"- Files changed: {len(changed_files)}")
    lines.append(f"- Lines changed: {total_lines}")
    lines.append("")

    lines.append("## Categories")
    lines.extend(_render_categories(categories) or ["- None"])
    lines.append("")

    lines.append("## Missing Tests")
    lines.extend(_render_missing_tests(test_gap))
    lines.append("")

    lines.append("## Changed Files")
    for path in changed_files:
        lines.append(f"- {path}")
    lines.append("")

    file_rows: list[list[str]] = []
    for change in changes:
        file_rows.append(
            [
                change.path,
                str(change.added) if change.added is not None else "-",
                str(change.removed) if change.removed is not None else "-",
                change.change_type,
            ]
        )

    table_lines = _render_table(file_rows, ["File", "Added", "Removed", "Type"])
    if table_lines:
        lines.append("## File Stats")
        lines.extend(table_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report: str, output_path: str | Path) -> Path:
    """Write the Markdown report to disk.

    Args:
        report: Markdown report content.
        output_path: Path for the Markdown report file.

    Returns:
        Path: Resolved path to the written report.
    """
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path
