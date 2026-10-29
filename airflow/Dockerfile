FROM astrocrpublic.azurecr.io/runtime:3.1-5

# dbt lives in its own virtualenv so its pins never fight Airflow's (the Cosmos-recommended
# layout). Cosmos calls it through ExecutionConfig(dbt_executable_path=...).
RUN python -m venv dbt_venv && \
    dbt_venv/bin/pip install --no-cache-dir "dbt-core>=1.10,<2" "dbt-snowflake>=1.10,<2"

# include/ is populated by `python scripts/sync_airflow_include.py` before `astro dev start`
# or `astro deploy`: the gridlens Python package and the dbt project.
USER root
RUN pip install --no-cache-dir "/usr/local/airflow/include/gridlens[ingest,forecast]" && \
    cd /usr/local/airflow/include/dbt && /usr/local/airflow/dbt_venv/bin/dbt deps && \
    chown -R astro:0 /usr/local/airflow/include
USER astro
