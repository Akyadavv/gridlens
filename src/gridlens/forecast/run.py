"""Daily forecast job.

  gridlens-forecast                               # read Snowflake, forecast, backtest, write back
  gridlens-forecast --dry-run                     # same, but only print the metrics
  gridlens-forecast --input-csv features.csv --dry-run --backtest-days 7   # offline

1. Load ANALYTICS.MARTS.ML_DEMAND_FEATURES (built by dbt) and add lag features.
2. Issue point = end of the last complete UTC day D-1; forecast all 24 hours of day D.
3. Re-forecast the last N complete days (rolling origin) and score every model and EIA.
4. Write ANALYTICS.ML.DEMAND_FORECAST and FORECAST_METRICS; dbt builds the marts on top.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone

import pandas as pd

from gridlens.common.logging import get_logger, kv
from gridlens.forecast.backtest import last_complete_day, run_backtest, score
from gridlens.forecast.features import add_features
from gridlens.forecast.models import MODEL_NAMES, forecast_day

log = get_logger("gridlens.forecast")


def _models(value: str) -> tuple[str, ...]:
    names = tuple(v.strip() for v in value.split(",") if v.strip())
    unknown = set(names) - set(MODEL_NAMES)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown models {sorted(unknown)}; choose from {MODEL_NAMES}")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gridlens-forecast")
    parser.add_argument("--backtest-days", type=int, default=14)
    parser.add_argument("--history-days", type=int, default=730)
    parser.add_argument("--sarima-train-days", type=int, default=28)
    parser.add_argument("--models", type=_models, default=MODEL_NAMES)
    parser.add_argument("--target-day", type=date.fromisoformat, help="override (YYYY-MM-DD)")
    parser.add_argument("--input-csv", help="read features from a CSV export instead of Snowflake")
    parser.add_argument("--dry-run", action="store_true", help="do not write to Snowflake")
    args = parser.parse_args(argv)

    from_snowflake = not args.input_csv
    if args.input_csv:
        raw = pd.read_csv(args.input_csv, parse_dates=["period_utc"])
        raw.columns = [c.lower() for c in raw.columns]
    else:
        from gridlens.common.snowflake import get_connection
        from gridlens.forecast import io

        # Short-lived connections: model fitting can run long (or the host can sleep), and a
        # session held open across it may have expired by the time we write.
        conn = get_connection(role="TRANSFORMER")
        try:
            raw = io.load_features(conn, args.history_days)
        finally:
            conn.close()

    feat = add_features(raw)
    last_day = last_complete_day(feat)
    target_day = pd.Timestamp(args.target_day) if args.target_day else last_day + pd.Timedelta(days=1)
    issued_at = datetime.now(timezone.utc).replace(tzinfo=None)
    run_id = target_day.date().isoformat()
    log.info("forecast run", extra=kv(run_id=run_id, last_complete_day=last_day.date()))

    live = forecast_day(feat, target_day, args.models, args.sarima_train_days)
    live = live.assign(run_id=run_id, is_backtest=False, issued_at=issued_at)

    backtest = run_backtest(feat, last_day, args.backtest_days, args.models, args.sarima_train_days)
    metrics = pd.DataFrame()
    if not backtest.empty:
        metrics = score(backtest, feat).assign(run_id=run_id, issued_at=issued_at)
        backtest = backtest.assign(is_backtest=True, issued_at=issued_at)

    if from_snowflake and not args.dry_run:
        from gridlens.common.snowflake import get_connection
        from gridlens.forecast import io

        conn = get_connection(role="TRANSFORMER")
        try:
            io.write_outputs(conn, live, backtest, metrics, run_id)
        finally:
            conn.close()

    pooled = metrics[metrics["region_code"] == "ALL"] if not metrics.empty else metrics
    summary = {
        "run_id": run_id,
        "live_rows": len(live),
        "backtest_rows": len(backtest),
        "backtest_mape": {r.model_name: round(r.mape, 2) for r in pooled.itertuples()},
    }
    # Last line of stdout is machine-readable, like gridlens-ingest.
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
