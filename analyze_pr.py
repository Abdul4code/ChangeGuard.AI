"""Executable entry point for ChangeGuard local PR analysis.

This file is intentionally thin. It parses command-line input and
delegates execution to the CLI workflow module in the app package.
"""

from app.pr_analysis_cli import build_parser, run


def main() -> int:
    """Run the command-line workflow.

    Returns:
        int: Process exit code where 0 indicates success.
    """
    parser = build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
