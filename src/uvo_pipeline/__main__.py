"""CLI entry point: python -m uvo_pipeline --mode=recent|historical"""

import argparse
import asyncio
import logging
import sys

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.orchestrator import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="UVO Search ETL pipeline")
    parser.add_argument(
        "--mode",
        choices=["recent", "historical"],
        default="recent",
        help="recent: last 365 days; historical: full backfill from 2014",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and transform without writing to databases",
    )
    args = parser.parse_args()

    settings = PipelineSettings()
    settings.pipeline_mode = args.mode

    try:
        report = asyncio.run(run(mode=args.mode, settings=settings, dry_run=args.dry_run))
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


if __name__ == "__main__":
    main()
