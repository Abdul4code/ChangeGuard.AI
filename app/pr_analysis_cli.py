"""CLI construction and execution for local PR analysis.

This module owns command-line concerns, including parser construction,
input validation, and dispatch to analysis flow. Analysis implementation
is kept separate from CLI concerns.
"""

from __future__ import annotations

import argparse
from pathlib import Path


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

    print("ChangeGuard AI CLI Input")
    print(f"repo: {repo_path}")
    print(f"base: {args.base}")
    print(f"head: {args.head}")
    return 0
