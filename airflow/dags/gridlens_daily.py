"""
### gridlens_daily

ingest (EIA + Open-Meteo -> S3 or local) -> load RAW (Snowpipe, or internal stage) -> freshness
-> dbt build (core) -> forecast -> dbt build (forecast marts)

* Ingestion is incremental and idempotent: safe to clear and re-run any task.
* dbt runs through Astronomer Cosmos, so every model and its tests are separate tasks and a
  failure points at one model rather than "dbt build failed".
* Any task failure posts to Slack (SLACK_WEBHOOK_URL) via `gridlens.common.alerts`.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode, TestBehavior

from gridlens.common.alerts import notify_failure
from gridlens.ingest.pipelines import DATASETS

AIRFLOW_HOME = Path(os.getenv("AIRFLOW_HOME", "/usr/local/airflow"))
DBT_PROJECT = AIRFLOW_HOME / "include" / "dbt"
DBT_BIN = AIRFLOW_HOME / "dbt_venv" / "bin" / "dbt"

# Render from a precompiled manifest (scripts/sync_airflow_include.py runs `dbt parse`):
# parsing the DAG then takes milliseconds instead of a `dbt ls` per task group.
project_config = ProjectConfig(
    dbt_project_path=DBT_PROJECT,
    manifest_path=DBT_PROJECT / "target" / "manifest.json",
    install_dbt_deps=False,
)
profile_config = ProfileConfig(
    profile_name="gridlens",
    target_name="prod",
    profiles_yml_filepath=DBT_PROJECT / "profiles.yml",
)
execution_config = ExecutionConfig(dbt_executable_path=str(DBT_BIN))

default_args = {
    "owner": "gridlens",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": notify_failure,
}

with DAG(
    dag_id="gridlens_daily",
    # 06:30 UTC: yesterday is complete in every US time zone and EIA has published it.
    schedule="30 6 * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    dagrun_timeout=timedelta(hours=3),
    tags=["gridlens", "dbt", "forecast"],
    doc_md=__doc__,
):

    @task(retries=3, retry_exponential_backoff=True)
    def ingest(dataset: str) -> dict:
        from gridlens.common.config import IngestSettings
        from gridlens.ingest.pipelines import run
        from gridlens.ingest.storage import make_storage

        settings = IngestSettings.from_env()
        storage = make_storage(settings.storage, settings.s3_bucket, settings.local_root)
        result = run(dataset, settings, storage).as_dict()
        result.pop("keys")  # keep XCom small; counts are what matter downstream
        return result

    @task(retries=1)
    def load_raw() -> None:
        """S3 mode: Snowpipe loads on its own, so wait until it has drained.
        Local mode: push new files through the internal stage and COPY them."""
        from gridlens.common.config import IngestSettings
        from gridlens.common.snowflake import get_connection

        settings = IngestSettings.from_env()
        conn = get_connection(role="LOADER")
        try:
            if settings.storage == "s3":
                from gridlens.ingest.snowpipe import wait_for_pipes

                wait_for_pipes(conn)
            else:
                from gridlens.ingest.internal_stage import load

                load(conn, settings.local_root)
        finally:
            conn.close()

    source_freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=(
            f"cd {DBT_PROJECT} && {DBT_BIN} source freshness --profiles-dir . --target prod "
            "--select source:eia source:open_meteo "
            "--target-path /tmp/dbt_target --log-path /tmp/dbt_logs"
        ),
        append_env=True,
    )

    dbt_core = DbtTaskGroup(
        group_id="dbt_core",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        render_config=RenderConfig(
            load_method=LoadMode.DBT_MANIFEST,
            exclude=["tag:forecast_output"],
            test_behavior=TestBehavior.AFTER_EACH,
        ),
    )

    @task(execution_timeout=timedelta(hours=1), retries=1)
    def forecast() -> None:
        from gridlens.forecast.run import main

        if main(["--backtest-days", os.getenv("GRIDLENS_BACKTEST_DAYS", "14")]) != 0:
            raise RuntimeError("gridlens-forecast failed")

    dbt_forecast = DbtTaskGroup(
        group_id="dbt_forecast",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        render_config=RenderConfig(
            load_method=LoadMode.DBT_MANIFEST,
            select=["tag:forecast_output"],
            test_behavior=TestBehavior.AFTER_EACH,
        ),
    )

    ingested = ingest.expand(dataset=list(DATASETS))
    ingested >> load_raw() >> source_freshness >> dbt_core >> forecast() >> dbt_forecast
