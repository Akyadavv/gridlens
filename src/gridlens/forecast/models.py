"""Forecast models: seasonal naive (sanity floor), SARIMA (classical baseline), LightGBM.

All functions forecast the 24 UTC hours of one target day from data strictly before it.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from gridlens.common.logging import get_logger, kv
from gridlens.forecast.features import FEATURES, TARGET

log = get_logger(__name__)

MODEL_NAMES = ("lightgbm", "sarima", "seasonal_naive")

LGBM_PARAMS = {
    "objective": "l2",
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 40,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1,
}


def seasonal_naive(target_rows: pd.DataFrame) -> np.ndarray:
    """Same hour one week earlier. Any model that cannot beat this is not worth running."""
    return target_rows["lag_168h"].to_numpy(dtype=float)


def sarima(history: pd.Series, steps: int = 24, train_days: int = 28) -> np.ndarray:
    """SARIMA(2,0,1)(1,1,1)[24] on log demand.

    Daily seasonality only: a weekly season (s=168) is far too slow to fit hourly. The
    training window is kept short for the same reason; this is a baseline, not the product.
    `history` must be hourly and end at the hour right before the first target hour.
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y = history.iloc[-train_days * 24 :].astype(float)
    y = y.interpolate(limit=6).ffill().bfill()
    if y.isna().any() or (y <= 0).any() or len(y) < 7 * 24:
        raise ValueError("not enough clean history for SARIMA")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence chatter; accuracy is what we track
        fit = SARIMAX(
            np.log(y.to_numpy()),
            order=(2, 0, 1),
            seasonal_order=(1, 1, 1, 24),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, maxiter=50)
    return np.exp(fit.forecast(steps))


def train_lightgbm(train: pd.DataFrame):
    """One global model across regions (region is a categorical feature). The target is
    log demand so a 1% miss costs the same in PJM (~90 GW peak) as in NYISO (~25 GW)."""
    import lightgbm as lgb

    rows = train[train[TARGET].notna() & (train[TARGET] > 0) & train["lag_168h"].notna()]
    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    model.fit(rows[FEATURES], np.log(rows[TARGET]), categorical_feature=["region_code"])
    return model


def predict_lightgbm(model, rows: pd.DataFrame) -> np.ndarray:
    return np.exp(model.predict(rows[FEATURES]))


def forecast_day(
    feat: pd.DataFrame,
    target_day: pd.Timestamp,
    models: tuple[str, ...] = MODEL_NAMES,
    sarima_train_days: int = 28,
    lgbm_model=None,
) -> pd.DataFrame:
    """Forecast all regions for one UTC day. Returns long rows:
    model_name, region_code, period_utc, forecast_mwh."""
    start = pd.Timestamp(target_day).normalize()
    end = start + pd.Timedelta(hours=23)
    target = feat[(feat["period_utc"] >= start) & (feat["period_utc"] <= end)]
    history = feat[feat["period_utc"] < start]
    keys = target[["region_code", "period_utc"]].astype({"region_code": str})
    out = []

    if "seasonal_naive" in models:
        out.append(keys.assign(model_name="seasonal_naive", forecast_mwh=seasonal_naive(target)))

    if "lightgbm" in models:
        model = lgbm_model or train_lightgbm(history)
        out.append(keys.assign(model_name="lightgbm", forecast_mwh=predict_lightgbm(model, target)))

    if "sarima" in models:
        for region, rows in target.groupby("region_code", observed=True):
            series = history.loc[history["region_code"] == region].set_index("period_utc")[TARGET]
            try:
                values = sarima(series, steps=len(rows), train_days=sarima_train_days)
            except Exception as exc:  # one bad region must not sink the whole run
                log.warning("sarima failed", extra=kv(region=region, day=start.date(), error=exc))
                values = np.full(len(rows), np.nan)
            out.append(
                rows[["region_code", "period_utc"]]
                .astype({"region_code": str})
                .assign(model_name="sarima", forecast_mwh=values)
            )

    if not out:
        return pd.DataFrame(columns=["model_name", "region_code", "period_utc", "forecast_mwh"])
    result = pd.concat(out, ignore_index=True)
    return result[["model_name", "region_code", "period_utc", "forecast_mwh"]]
