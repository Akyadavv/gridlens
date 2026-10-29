"""Incremental, idempotent ingestion pipelines.

Each pipeline:
  1. works out a date window: explicit --start/--end, or (watermark - lookback) .. today
  2. fetches one partition at a time (UTC day, or month for EIA-860M)
  3. writes one deterministic file per partition (overwrite = safe re-run)
  4. advances the watermark only past partitions that actually returned data
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

from gridlens.common.config import IngestSettings
from gridlens.common.logging import get_logger, kv
from gridlens.common.regions import Region, load_regions
from gridlens.ingest import eia, open_meteo
from gridlens.ingest.storage import (
    Storage,
    partition_key,
    read_watermark,
    to_ndjson_gz,
    write_watermark,
)

log = get_logger(__name__)

ARCHIVE_LAG_DAYS = 5  # Open-Meteo reanalysis lags real time; the forecast feed covers the gap
GENERATOR_LOOKBACK_MONTHS = 2


@dataclass
class RunResult:
    dataset: str
    keys: list[str] = field(default_factory=list)
    rows: int = 0
    empty_partitions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "files": len(self.keys),
            "rows": self.rows,
            "keys": self.keys,
            "empty_partitions": self.empty_partitions,
        }


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def month_range(start: date, end: date) -> list[str]:
    months, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def plan_window(
    storage: Storage,
    dataset: str,
    settings: IngestSettings,
    today: date,
    start: date | None = None,
    end: date | None = None,
) -> tuple[date, date]:
    """Explicit dates win (backfills). Otherwise re-pull `lookback_days` behind the watermark
    because EIA revises recent hours after first publishing them."""
    if start is None:
        wm = read_watermark(storage, dataset)
        if wm is None:
            start = settings.backfill_start
        else:
            lookback = timedelta(days=settings.lookback_days)
            start = max(settings.backfill_start, date.fromisoformat(wm[:10]) - lookback)
    # start > end yields an empty window (nothing new to pull), not an error.
    return start, end or today


def _advance_watermark(storage: Storage, dataset: str, candidate: str | None) -> None:
    if candidate is None:
        return
    current = read_watermark(storage, dataset)
    # Never move the watermark backwards when backfilling an older range.
    if current is None or candidate > current:
        write_watermark(storage, dataset, candidate)
        log.info("watermark advanced", extra=kv(dataset=dataset, watermark=candidate))


def _write(storage: Storage, result: RunResult, source: str, partition: str, rows: list[dict]):
    key = partition_key(source, result.dataset, partition)
    storage.put_bytes(key, to_ndjson_gz(rows))
    result.keys.append(key)
    result.rows += len(rows)
    log.info("partition written", extra=kv(dataset=result.dataset, partition=partition, rows=len(rows)))


# ---- EIA hourly ------------------------------------------------------------------------

def ingest_eia_hourly(
    dataset: str,
    query_fn: Callable[[Sequence[str], str, str], eia.EiaQuery],
    client: eia.EiaClient,
    storage: Storage,
    regions: Sequence[str],
    start: date,
    end: date,
) -> RunResult:
    result = RunResult(dataset)
    last_with_data: str | None = None
    for day in daterange(start, end):
        d = day.isoformat()
        rows = client.fetch(query_fn(regions, f"{d}T00", f"{d}T23"))
        if not rows:
            result.empty_partitions.append(d)
            log.warning("no rows for partition", extra=kv(dataset=dataset, partition=d))
            continue
        _write(storage, result, "eia", d, rows)
        last_with_data = d
    _advance_watermark(storage, dataset, last_with_data)
    return result


def ingest_generator_capacity(
    client: eia.EiaClient, storage: Storage, regions: Sequence[str], months: Sequence[str]
) -> RunResult:
    result = RunResult("generator_capacity")
    last_with_data = None
    for month in months:
        rows = client.fetch(eia.generator_capacity_query(regions, month))
        if not rows:
            # EIA-860M is published with a ~2 month lag, so recent months are often empty.
            result.empty_partitions.append(month)
            continue
        _write(storage, result, "eia", month, rows)
        last_with_data = month
    _advance_watermark(storage, "generator_capacity", last_with_data)
    return result


# ---- Weather ---------------------------------------------------------------------------

def ingest_weather_archive(
    session: requests.Session,
    storage: Storage,
    regions: Sequence[Region],
    start: date,
    end: date,
    max_days_per_request: int = 366,
) -> RunResult:
    result = RunResult("weather_archive")
    by_day: dict[str, list[dict]] = defaultdict(list)
    for region in regions:
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(end, chunk_start + timedelta(days=max_days_per_request - 1))
            for row in open_meteo.fetch_archive(session, region, chunk_start, chunk_end):
                if row.get("temperature_2m") is not None:  # archive pads unreleased hours with nulls
                    by_day[row["time_utc"][:10]].append(row)
            chunk_start = chunk_end + timedelta(days=1)

    last_with_data = None
    for d in sorted(by_day):
        _write(storage, result, "open_meteo", d, by_day[d])
        last_with_data = d
    _advance_watermark(storage, "weather_archive", last_with_data)
    return result


def ingest_weather_forecast(
    session: requests.Session, storage: Storage, regions: Sequence[Region], issue_date: date
) -> RunResult:
    """One file per issue date: the latest forecast covering recent + next 2 days."""
    result = RunResult("weather_forecast")
    rows = []
    for region in regions:
        rows += open_meteo.fetch_forecast(session, region, past_days=ARCHIVE_LAG_DAYS + 2)
    if rows:
        _write(storage, result, "open_meteo", issue_date.isoformat(), rows)
    return result


# ---- Entry point -----------------------------------------------------------------------

DATASETS = ("region_data", "fuel_type_data", "generator_capacity", "weather_archive", "weather_forecast")


def run(
    dataset: str,
    settings: IngestSettings,
    storage: Storage,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
    session: requests.Session | None = None,
) -> RunResult:
    today = today or utc_today()
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", "gridlens/0.1 (+https://github.com/)")
    regions = load_regions()
    codes = [r.code for r in regions]

    if dataset in ("region_data", "fuel_type_data"):
        client = eia.EiaClient(settings.require_eia_key(), session=session)
        query_fn = eia.region_data_query if dataset == "region_data" else eia.fuel_type_query
        s, e = plan_window(storage, dataset, settings, today, start, end)
        return ingest_eia_hourly(dataset, query_fn, client, storage, codes, s, e)

    if dataset == "generator_capacity":
        client = eia.EiaClient(settings.require_eia_key(), session=session)
        if start is None:
            wm = read_watermark(storage, dataset)
            if wm:
                y, m = map(int, wm.split("-"))
                m -= GENERATOR_LOOKBACK_MONTHS
                while m < 1:
                    y, m = y - 1, m + 12
                start = date(y, m, 1)
            else:
                start = settings.backfill_start
        return ingest_generator_capacity(client, storage, codes, month_range(start, end or today))

    if dataset == "weather_archive":
        archive_end = min(end or today, today - timedelta(days=ARCHIVE_LAG_DAYS))
        s, e = plan_window(storage, dataset, settings, today, start, archive_end)
        return ingest_weather_archive(session, storage, regions, s, e)

    if dataset == "weather_forecast":
        return ingest_weather_forecast(session, storage, regions, today)

    raise ValueError(f"Unknown dataset {dataset!r}. Choose from {DATASETS}")
