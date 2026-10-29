"""Rolling-origin backtest: re-forecast each of the last N days using only data before it,
then score every model (and EIA's own day-ahead forecast) on the same hours."""

from __future__ import annotations

import pandas as pd

from gridlens.common.logging import get_logger, kv
from gridlens.forecast.features import TARGET, mape, rmse
from gridlens.forecast.models import MODEL_NAMES, forecast_day

log = get_logger(__name__)

EIA_MODEL = "eia_day_ahead"


def last_complete_day(feat: pd.DataFrame) -> pd.Timestamp:
    """Latest UTC day with all 24 demand values in every region that reports at all.
    This is the issue point: forecasts target the day after it."""
    have = feat.dropna(subset=[TARGET]).assign(day=lambda d: d["period_utc"].dt.normalize())
    counts = have.groupby(["region_code", "day"], observed=True).size()
    complete = counts[counts == 24].reset_index()
    if complete.empty:
        raise ValueError("no complete day of demand data")
    return complete.groupby("region_code", observed=True)["day"].max().min()


def run_backtest(
    feat: pd.DataFrame,
    last_day: pd.Timestamp,
    days: int,
    models: tuple[str, ...] = MODEL_NAMES,
    sarima_train_days: int = 28,
) -> pd.DataFrame:
    """Forecasts for each origin day in (last_day - days, last_day]."""
    frames = []
    for i in range(days - 1, -1, -1):
        day = pd.Timestamp(last_day) - pd.Timedelta(days=i)
        fc = forecast_day(feat, day, models=models, sarima_train_days=sarima_train_days)
        frames.append(fc.assign(run_id=day.date().isoformat()))
        log.info("backtest day done", extra=kv(day=day.date(), rows=len(fc)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def score(forecasts: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
    """MAPE / RMSE per model and region, plus a pooled 'ALL' row per model.
    EIA's day-ahead forecast is scored on exactly the hours the models forecast."""
    actuals = feat[["region_code", "period_utc", TARGET, "eia_day_ahead_forecast_mwh"]].astype(
        {"region_code": str}
    )
    joined = forecasts.merge(actuals, on=["region_code", "period_utc"], how="inner")
    joined = joined[joined[TARGET].notna()]

    eia_hours = joined.drop_duplicates(["region_code", "period_utc"]).assign(
        model_name=EIA_MODEL, forecast_mwh=lambda d: d["eia_day_ahead_forecast_mwh"]
    )
    joined = pd.concat([joined, eia_hours], ignore_index=True)

    rows = []
    for (model, region), g in joined.groupby(["model_name", "region_code"]):
        rows.append(_metric_row(model, region, g))
    for model, g in joined.groupby("model_name"):
        rows.append(_metric_row(model, "ALL", g))
    return pd.DataFrame(rows)


def _metric_row(model: str, region: str, g: pd.DataFrame) -> dict:
    return {
        "model_name": model,
        "region_code": region,
        "window_start": g["period_utc"].min().date(),
        "window_end": g["period_utc"].max().date(),
        "n_hours": int(g["forecast_mwh"].notna().sum()),
        "mape": mape(g[TARGET], g["forecast_mwh"]),
        "rmse_mwh": rmse(g[TARGET], g["forecast_mwh"]),
    }
