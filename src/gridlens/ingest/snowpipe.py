"""Wait for Snowpipe to drain, so dbt never builds on half-loaded raw tables.

Auto-ingest is asynchronous (S3 event -> SQS -> pipe), typically under a minute. The
orchestrator calls `wait_for_pipes` between ingestion and `dbt build`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence

from gridlens.common.logging import get_logger, kv

log = get_logger(__name__)

PIPES = (
    "RAW.EIA.REGION_DATA_PIPE",
    "RAW.EIA.FUEL_TYPE_DATA_PIPE",
    "RAW.EIA.GENERATOR_CAPACITY_PIPE",
    "RAW.OPEN_METEO.WEATHER_ARCHIVE_PIPE",
    "RAW.OPEN_METEO.WEATHER_FORECAST_PIPE",
)


def pipe_status(conn, pipe: str) -> dict:
    cur = conn.cursor()
    cur.execute("select system$pipe_status(%s)", (pipe,))
    return json.loads(cur.fetchone()[0])


def wait_for_pipes(
    conn,
    pipes: Sequence[str] = PIPES,
    timeout_s: float = 900,
    poll_s: float = 15,
    settle_s: float = 30,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Block until every pipe is RUNNING with no pending files.

    `settle_s` gives S3 event notifications time to reach the pipes first: right after an
    upload, pendingFileCount can still be 0 because the event has not arrived yet.
    """
    sleep(settle_s)
    deadline = clock() + timeout_s
    while True:
        pending = {}
        for pipe in pipes:
            status = pipe_status(conn, pipe)
            state = status.get("executionState")
            if state != "RUNNING":
                raise RuntimeError(f"{pipe} is {state}: {status.get('error') or status}")
            if int(status.get("pendingFileCount", 0)):
                pending[pipe] = int(status["pendingFileCount"])
        if not pending:
            log.info("snowpipe drained", extra=kv(pipes=len(pipes)))
            return
        if clock() >= deadline:
            raise TimeoutError(f"Snowpipe still has pending files after {timeout_s}s: {pending}")
        log.info("waiting for snowpipe", extra=kv(**{p.split(".")[-1]: n for p, n in pending.items()}))
        sleep(poll_s)
