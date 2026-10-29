"""Load raw files from local mode (GRIDLENS_STORAGE=local) into RAW, without S3 or Snowpipe.

    python scripts/load_local_to_snowflake.py [--root ./data/raw]

Thin wrapper around gridlens.ingest.internal_stage (also used by the Airflow DAG).
"""

from __future__ import annotations

import argparse

from gridlens.common.config import IngestSettings
from gridlens.common.snowflake import get_connection
from gridlens.ingest.internal_stage import load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=IngestSettings.from_env().local_root)
    args = parser.parse_args(argv)

    conn = get_connection(role="LOADER")
    try:
        load(conn, args.root)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
