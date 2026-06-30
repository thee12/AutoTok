"""Command-line interface for AutoTok."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from autotok import __version__
from autotok.config import AppConfig, ConfigError
from autotok.errors import AutoTokError
from autotok.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="autotok",
        description="AutoTok local-first video pipeline tooling.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subcommands = parser.add_subparsers(dest="command", required=True)
    doctor = subcommands.add_parser(
        "doctor",
        help="Run a harmless local diagnostic.",
        description="Validate local configuration and print a diagnostic summary.",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Print the diagnostic summary as JSON.",
    )
    doctor.set_defaults(handler=run_doctor)
    return parser


def run_doctor(args: argparse.Namespace) -> int:
    """Run the harmless Phase 0 diagnostic command."""
    config = AppConfig.from_environment()
    configure_logging(config.log_level)

    diagnostic = {
        "application": "autotok",
        "version": __version__,
        "environment": config.environment,
        "log_level": config.log_level,
        "data_dir": str(config.data_dir),
        "status": "ok",
    }
    if args.json:
        print(json.dumps(diagnostic, indent=2, sort_keys=True))
    else:
        print("AutoTok diagnostic: ok")
        print(f"Version: {diagnostic['version']}")
        print(f"Environment: {diagnostic['environment']}")
        print(f"Log level: {diagnostic['log_level']}")
        print(f"Data directory: {diagnostic['data_dir']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.handler(args))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except AutoTokError as exc:
        print(f"AutoTok error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
