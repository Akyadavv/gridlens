"""Snowflake I/O for the forecast job: read the dbt feature table, write forecasts + metrics.

Writes are idempotent per run: rows for the same run_id (target day) and live/backtest flag
are deleted before the new ones are inserted, so re-running a day replaces it.
"""

from __future__ import annotations

import os

import pandas as pd

from gridlens.common.logging import get_logger, kv

log = get_logger(__name__)

FEATURES_TABLE = os.getenv("GRIDLENS_FEATURES_TABLE", "ANALYTICS.MARTS.ML_DEMAND_FEATURES")
ML_DATABASE = os.getenv("GRIDLENS_ML_DATABASE", "ANALYTICS")
ML_SCHEMA = os.getenv("GRIDLENS_ML_SCHEMA", "ML")

# Mirrors snowflake/02_analytics_objects.sql so the job also works on a fresh account.
DDL = (
    f"create schema if not exists {ML_DATABASE}.{ML_SCHEMA}",
    f"""create table if not exists {ML_DATABASE}.{ML_SCHEMA}.DEMAND_FORECAST (
        run_id varchar not null, model_name varchar not null, region_code varchar not null,
        period_utc timestamp_ntz not null, forecast_mwh float, is_backtest boolean not null,
        issued_at timestamp_ntz not null)""",
    f"""create table if not exists {ML_DATABASE}.{ML_SCHEMA}.FORECAST_METRICS (
        run_id varchar not null, model_name varchar not null, region_code varchar not null,
        window_start date, window_end date, n_hours number, mape float, rmse_mwh float,
        issued_at timestamp_ntz not null)""",
)


def load_features(conn, history_days: int) -> pd.DataFrame:
    sql = (
        f"select * from {FEATURES_TABLE} "
        "where period_utc >= dateadd(day, -%(days)s, current_date()) order by region_code, period_utc"
    )
    cur = conn.cursor()
    cur.execute(sql, {"days": history_days})
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df["period_utc"] = pd.to_datetime(df["period_utc"])
    log.info("features loaded", extra=kv(rows=len(df), table=FEATURES_TABLE))
    return df


def ensure_tables(conn) -> None:
    cur = conn.cursor()
    for stmt in DDL:
        cur.execute(stmt)


def _write(conn, table: str, df: pd.DataFrame, delete_sql: str, params: dict) -> None:
    from snowflake.connector.pandas_tools import write_pandas

    conn.cursor().execute(f"delete from {ML_DATABASE}.{ML_SCHEMA}.{table} where {delete_sql}", params)
    if df.empty:
        return
    frame = df.copy()
    frame.columns = [c.upper() for c in frame.columns]
    ok, _, nrows, _ = write_pandas(
        conn, frame, table, database=ML_DATABASE, schema=ML_SCHEMA,
        quote_identifiers=False, use_logical_type=True,
    )
    if not ok:
        raise RuntimeError(f"write_pandas failed for {table}")
    log.info("rows written", extra=kv(table=table, rows=nrows))


def write_outputs(
    conn, live: pd.DataFrame, backtest: pd.DataFrame, metrics: pd.DataFrame, run_id: str
) -> None:
    ensure_tables(conn)
    _write(
        conn, "DEMAND_FORECAST", live,
        "run_id = %(run_id)s and not is_backtest", {"run_id": run_id},
    )
    if not backtest.empty:
        _write(
            conn, "DEMAND_FORECAST", backtest,
            "is_backtest and run_id between %(lo)s and %(hi)s",
            {"lo": backtest["run_id"].min(), "hi": backtest["run_id"].max()},
        )
    _write(conn, "FORECAST_METRICS", metrics, "run_id = %(run_id)s", {"run_id": run_id})
