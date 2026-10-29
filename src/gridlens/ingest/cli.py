"""Command line entry point.

Examples:
  gridlens-ingest region_data                      # incremental (watermark - lookback .. today)
  gridlens-ingest region_data --start 2024-01-01 --end 2024-03-31   # backfill
  gridlens-ingest all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from gridlens.common.config import IngestSettings
from gridlens.common.logging import get_logger
from gridlens.ingest.pipelines import DATASETS, run
from gridlens.ingest.storage import make_storage

log = get_logger("gridlens.ingest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gridlens-ingest")
    parser.add_argument("dataset", choices=[*DATASETS, "all"])
    parser.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (inclusive)")
    args = parser.parse_args(argv)
    if args.start and args.end and args.start > args.end:
        parser.error("--start must be on or before --end")

    settings = IngestSettings.from_env()
    storage = make_storage(settings.storage, settings.s3_bucket, settings.local_root)

    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    results = [run(ds, settings, storage, start=args.start, end=args.end).as_dict() for ds in datasets]
    # Last line of stdout is machine-readable so Airflow can push it to XCom.
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
