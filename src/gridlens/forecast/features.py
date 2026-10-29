"""Feature engineering on top of the dbt table ANALYTICS.MARTS.ML_DEMAND_FEATURES.

The target is next-day hourly demand. Forecasts are issued after the last complete UTC day
D-1 and cover all 24 hours of day D, so every lag must be at least 24 hours: the value at
t-24h for the last target hour (D 23:00) is D-1 23:00, the newest observation available.
Using only lags >= 24h gives a "direct" model that needs no recursive forecasting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "demand_mwh"
LAGS_HOURS = (24, 48, 168, 336)

CALENDAR_FEATURES = [
    "hour_local",
    "day_of_week_iso",
    "month_number",
    "day_of_year",
    "is_weekend",
    "is_holiday",
]
WEATHER_FEATURES = [
    "temperature_c",
    "apparent_temperature_c",
    "dew_point_c",
    "relative_humidity_pct",
    "cloud_cover_pct",
    "wind_speed_ms",
    "shortwave_radiation_wm2",
    "cooling_degree_hours",
    "heating_degree_hours",
]
LAG_FEATURES = [f"lag_{h}h" for h in LAGS_HOURS] + [
    "lag_24h_rolling_mean_24h",
    "lag_24h_rolling_mean_168h",
    "temp_rolling_mean_24h",
]
FEATURES = ["region_code", *CALENDAR_FEATURES, *WEATHER_FEATURES, *LAG_FEATURES]


def complete_hourly_index(df: pd.DataFrame) -> pd.DataFrame:
    """One row per region and UTC hour with no gaps, so shift(24) really means 24 hours."""
    frames = []
    for region, g in df.groupby("region_code", sort=True):
        g = g.set_index("period_utc").sort_index()
        g = g[~g.index.duplicated(keep="last")]
        full = pd.date_range(g.index.min(), g.index.max(), freq="h", name="period_utc")
        g = g.reindex(full)
        g["region_code"] = region
        frames.append(g.reset_index())
    return pd.concat(frames, ignore_index=True)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag, rolling and calendar-gap-filled features. Input: ml_demand_features rows."""
    out = complete_hourly_index(df)
    out = out.sort_values(["region_code", "period_utc"]).reset_index(drop=True)
    by_region = out.groupby("region_code", sort=False)

    for h in LAGS_HOURS:
        out[f"lag_{h}h"] = by_region[TARGET].shift(h)
    lag24 = by_region[TARGET].shift(24)
    out["lag_24h_rolling_mean_24h"] = lag24.groupby(out["region_code"]).transform(
        lambda s: s.rolling(24, min_periods=12).mean()
    )
    out["lag_24h_rolling_mean_168h"] = lag24.groupby(out["region_code"]).transform(
        lambda s: s.rolling(168, min_periods=84).mean()
    )
    # Weather for the target hour itself is known (forecast) at issue time; smooth it to
    # capture heat build-up over the day.
    out["temp_rolling_mean_24h"] = by_region["temperature_c"].transform(
        lambda s: s.rolling(24, min_periods=12).mean()
    )

    # Gap rows added by the reindex have NaN flags; LightGBM treats NaN as missing.
    for col in ("is_weekend", "is_holiday"):
        out[col] = out[col].astype("float")
    out["region_code"] = out["region_code"].astype("category")
    return out


def mape(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    """Mean absolute percentage error in percent, ignoring hours with no/zero actual."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    mask = np.isfinite(a) & np.isfinite(f) & (a > 0)
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(f[mask] - a[mask]) / a[mask]) * 100)


def rmse(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    mask = np.isfinite(a) & np.isfinite(f)
    if not mask.any():
        return float("nan")
    return float(np.sqrt(np.mean((f[mask] - a[mask]) ** 2)))
