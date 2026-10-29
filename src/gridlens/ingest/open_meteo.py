"""Open-Meteo client (no API key). Historical archive + short-range forecast.

The archive (reanalysis) lags real time by a few days, so recent and next-day hours come
from the forecast endpoint. dbt prefers archive rows over forecast rows for the same hour.
"""

from __future__ import annotations

from datetime import date

import requests

from gridlens.common.regions import Region
from gridlens.ingest.http import get_json

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
)


def _flatten(payload: dict, region: Region, source: str) -> list[dict]:
    """Turn Open-Meteo's column-oriented `hourly` block into one dict per hour."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    rows = []
    for i, ts in enumerate(times):
        row = {
            "region_code": region.code,
            "latitude": region.latitude,
            "longitude": region.longitude,
            "source": source,
            "time_utc": ts,
        }
        for var in HOURLY_VARS:
            values = hourly.get(var)
            row[var] = values[i] if values is not None else None
        rows.append(row)
    return rows


def fetch_archive(
    session: requests.Session, region: Region, start: date, end: date, **http_kwargs
) -> list[dict]:
    params = {
        "latitude": region.latitude,
        "longitude": region.longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }
    return _flatten(get_json(session, ARCHIVE_URL, params=params, **http_kwargs), region, "archive")


def fetch_forecast(
    session: requests.Session, region: Region, past_days: int = 3, forecast_days: int = 3,
    **http_kwargs,
) -> list[dict]:
    params = {
        "latitude": region.latitude,
        "longitude": region.longitude,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    return _flatten(
        get_json(session, FORECAST_URL, params=params, **http_kwargs), region, "forecast"
    )
