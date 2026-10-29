import json

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("lightgbm")

from gridlens.forecast import run  # noqa: E402
from gridlens.forecast.backtest import last_complete_day, run_backtest, score  # noqa: E402
from gridlens.forecast.features import add_features, mape  # noqa: E402
from gridlens.forecast.models import forecast_day, sarima  # noqa: E402


def synthetic_features(days=70, regions=(("AAA", 20000.0), ("BBB", 5000.0)), seed=0):
    """Hourly demand with daily + weekly shape and a cooling-load response to temperature,
    shaped like ml_demand_features. The last day has weather but no demand (target day)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-05-01", periods=days * 24, freq="h")
    frames = []
    for code, base in regions:
        hour = idx.hour.to_numpy()
        dow = idx.day_of_week.to_numpy() + 1
        temp = 22 + 8 * np.sin((hour - 9) / 24 * 2 * np.pi) + rng.normal(0, 2, len(idx))
        demand = base * (
            1
            + 0.15 * np.sin((hour - 6) / 24 * 2 * np.pi)
            - 0.08 * (dow >= 6)
            + 0.01 * np.maximum(temp - 18, 0)
        ) * (1 + rng.normal(0, 0.01, len(idx)))
        df = pd.DataFrame(
            {
                "region_code": code,
                "period_utc": idx,
                "hour_local": hour,
                "day_of_week_iso": dow,
                "month_number": idx.month,
                "day_of_year": idx.day_of_year,
                "is_weekend": dow >= 6,
                "is_holiday": False,
                "demand_mwh": demand,
                "eia_day_ahead_forecast_mwh": demand * (1 + rng.normal(0, 0.03, len(idx))),
                "temperature_c": temp,
                "apparent_temperature_c": temp,
                "dew_point_c": temp - 8,
                "relative_humidity_pct": 60.0,
                "cloud_cover_pct": 30.0,
                "wind_speed_ms": 3.0,
                "shortwave_radiation_wm2": 200.0,
                "cooling_degree_hours": np.maximum(temp - 18, 0),
                "heating_degree_hours": np.maximum(18 - temp, 0),
            }
        )
        df.loc[df.index[-24:], ["demand_mwh", "eia_day_ahead_forecast_mwh"]] = np.nan
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_lags_are_hour_exact_even_with_gaps():
    raw = synthetic_features(days=15)
    dropped = raw.drop(index=raw.index[100])  # a missing hour must not shift the lags
    feat = add_features(dropped)
    a = feat[feat["region_code"] == "AAA"].set_index("period_utc")
    t = a.index[300]
    assert a.loc[t, "lag_24h"] == a.loc[t - pd.Timedelta(hours=24), "demand_mwh"]
    assert a.loc[t, "lag_168h"] == a.loc[t - pd.Timedelta(hours=168), "demand_mwh"]
    assert len(a) == 15 * 24  # the gap was re-inserted


def test_no_feature_uses_the_target_day():
    feat = add_features(synthetic_features(days=20))
    a = feat[feat["region_code"] == "AAA"].set_index("period_utc")
    last_hour = a.index.max()
    # The last target hour's freshest lag is the last hour of the previous day.
    assert a.loc[last_hour, "lag_24h"] == a.loc[last_hour - pd.Timedelta(hours=24), "demand_mwh"]
    assert np.isfinite(a.loc[last_hour, "lag_24h_rolling_mean_24h"])


def test_mape_ignores_zero_and_missing_actuals():
    assert mape([100, 200, 0, np.nan], [110, 180, 5, 5]) == pytest.approx(10.0)
    assert np.isnan(mape([0, np.nan], [1, 1]))


def test_last_complete_day_is_the_day_before_target():
    feat = add_features(synthetic_features(days=20))
    assert last_complete_day(feat) == pd.Timestamp("2024-05-19")


def test_lightgbm_beats_seasonal_naive():
    feat = add_features(synthetic_features(days=70))
    last = last_complete_day(feat)
    fc = run_backtest(feat, last, days=3, models=("lightgbm", "seasonal_naive"))
    assert len(fc) == 3 * 24 * 2 * 2  # days * hours * regions * models
    metrics = score(fc, feat).set_index(["model_name", "region_code"])["mape"]
    assert metrics[("lightgbm", "ALL")] < metrics[("seasonal_naive", "ALL")]
    assert metrics[("lightgbm", "ALL")] < 5
    assert ("eia_day_ahead", "ALL") in metrics.index


def test_live_forecast_covers_target_day():
    feat = add_features(synthetic_features(days=40))
    target = last_complete_day(feat) + pd.Timedelta(days=1)
    fc = forecast_day(feat, target, models=("lightgbm",))
    assert len(fc) == 48
    assert fc["forecast_mwh"].notna().all()
    assert fc["period_utc"].min() == target


def test_sarima_forecasts_24_positive_values():
    raw = synthetic_features(days=12, regions=(("AAA", 20000.0),))
    series = raw.set_index("period_utc")["demand_mwh"].iloc[:-24]
    values = sarima(series, steps=24, train_days=10)
    assert values.shape == (24,)
    assert (values > 0).all()
    assert mape(raw["demand_mwh"].iloc[-48:-24], values) < 15  # vs the last known day


def test_cli_offline_dry_run(tmp_path, capsys):
    path = tmp_path / "features.csv"
    synthetic_features(days=40).to_csv(path, index=False)
    assert run.main([
        "--input-csv", str(path), "--dry-run", "--backtest-days", "2",
        "--models", "lightgbm,seasonal_naive",
    ]) == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["run_id"] == "2024-06-09"
    assert summary["live_rows"] == 2 * 24 * 2
    assert set(summary["backtest_mape"]) == {"lightgbm", "seasonal_naive", "eia_day_ahead"}
