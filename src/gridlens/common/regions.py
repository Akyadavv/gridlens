"""Region reference data.

The same CSV is the dbt seed `dbt/seeds/regions.csv`; `tests/test_regions.py` fails if
they ever drift apart, so ingestion and the warehouse agree on what a region is.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    iso_type: str
    timezone: str
    weather_city: str
    latitude: float
    longitude: float


@lru_cache(maxsize=1)
def load_regions() -> tuple[Region, ...]:
    text = resources.files("gridlens.common").joinpath("regions.csv").read_text(encoding="utf-8")
    rows = csv.DictReader(text.splitlines())
    return tuple(
        Region(
            code=r["region_code"],
            name=r["region_name"],
            iso_type=r["iso_type"],
            timezone=r["timezone"],
            weather_city=r["weather_city"],
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
        )
        for r in rows
    )


def region_codes() -> list[str]:
    return [r.code for r in load_regions()]
