"""CLI entry point: python -m uvo_pipeline {run,health}"""

import argparse
import asyncio
import logging
import sys

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.health import run_health
from uvo_pipeline.orchestrator import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UVO Search ETL pipeline")
    sub = parser.add_subparsers(dest="command")

    # `run` subcommand (default — also accessible by legacy bare invocation)
    run_p = sub.add_parser("run", help="Run the ETL pipeline")
    run_p.add_argument("--mode", choices=["recent", "historical"], default="recent")
    run_p.add_argument("--dry-run", action="store_true")

    # `health` subcommand
    health_p = sub.add_parser("health", help="Show per-source ingestion health report")
    health_p.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    # Backwards-compat: allow bare `--mode=...` without subcommand
    parser.add_argument("--mode", choices=["recent", "historical"], help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    return parser


def _cmd_run(mode: str, dry_run: bool) -> None:
    settings = PipelineSettings()
    settings.pipeline_mode = mode
    try:
        report = asyncio.run(run(mode=mode, settings=settings, dry_run=dry_run))
        logger.info(
            "Pipeline complete: %d inserted, %d updated, %d errors",
            report.notices_inserted,
            report.notices_updated,
            len(report.errors),
        )
        if report.errors:
            for err in report.errors:
                logger.error("  %s", err)
            sys.exit(1)
    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


def _cmd_health(as_json: bool) -> None:
    settings = PipelineSettings()
    try:
        output = asyncio.run(run_health(settings, as_json=as_json))
        print(output)
    except Exception:
        logger.exception("Health check failed")
        sys.exit(1)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "health":
        _cmd_health(args.json)
        return

    # `run` subcommand, or legacy bare invocation
    if args.command == "run":
        _cmd_run(args.mode, args.dry_run)
    else:
        _cmd_run(args.mode or "recent", args.dry_run)


if __name__ == "__main__":
    main()
