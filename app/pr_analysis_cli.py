"""CLI construction and execution for local PR analysis.

This module owns command-line concerns, including parser construction,
input validation, and dispatch to analysis flow. Analysis implementation
is kept separate from CLI concerns.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.analyzers.change_classifier import classify_changed_files
from app.analyzers.test_gap_detector import detect_missing_or_related_tests
from app.collectors.git_diff_collector import collect_changed_file_stats
from app.reports.json_report import build_json_report, build_report_path, write_json_report
from app.reports.markdown_report import (
    build_markdown_report,
    build_markdown_report_path,
    write_markdown_report,
)
from app.risk.risk_scoring import calculate_risk_score


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for local PR analysis.

    Returns:
        argparse.ArgumentParser: Configured parser for local PR analysis.
    """
    parser = argparse.ArgumentParser(
        prog="analyze_pr.py",
        description="Analyze repository changes between two refs.",
    )
    parser.add_argument("--repo", required=True, help="Path to the target repository")
    parser.add_argument("--base", required=True, help="Base git ref (e.g., main)")
    parser.add_argument("--head", required=True, help="Head git ref (e.g., feature/xyz)")
    return parser


def run(args: argparse.Namespace) -> int:
    """Validate arguments and execute the CLI flow.

    Args:
        args: Parsed command-line arguments from `build_parser`.

    Returns:
        int: Process exit code where 0 indicates success.

    Raises:
        SystemExit: Raised by `argparse` when the repo path is invalid.
    """
    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        parser = build_parser()
        parser.error(f"--repo must point to an existing directory: {repo_path}")

    changes = collect_changed_file_stats(repo_path, args.base, args.head)
    categories = classify_changed_files(repo_path, changes)
    test_gap = detect_missing_or_related_tests(repo_path, changes)
    risk = calculate_risk_score(changes, categories, test_gap)

    report = build_json_report(
        repo_root=repo_path,
        base_ref=args.base,
        head_ref=args.head,
        changes=changes,
        categories=categories,
        test_gap=test_gap,
        risk=risk,
    )

    report_path = build_report_path(repo_path, args.base, args.head)
    written_path = write_json_report(report, report_path)

    markdown_report = build_markdown_report(
        repo_root=repo_path,
        base_ref=args.base,
        head_ref=args.head,
        changes=changes,
        categories=categories,
        test_gap=test_gap,
        risk=risk,
    )
    markdown_path = build_markdown_report_path(repo_path, args.base, args.head)
    written_markdown_path = write_markdown_report(markdown_report, markdown_path)

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Report written to: {written_path}")
    print(f"Markdown report written to: {written_markdown_path}")
    return 0
