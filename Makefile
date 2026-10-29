# Convenience targets. On Windows use Git Bash / WSL, or run the commands directly.
.PHONY: install test lint ingest dbt-build forecast airflow-sync docs

install:
	pip install -e ".[dev,ingest,forecast,dashboard]"

test:
	pytest

lint:
	ruff check src tests scripts airflow dashboard
	cd dbt && sqlfluff lint models tests analyses

ingest:
	gridlens-ingest all

dbt-build:
	cd dbt && dbt deps && dbt build

forecast:
	gridlens-forecast

airflow-sync:
	python scripts/sync_airflow_include.py

docs:
	cd dbt && dbt docs generate && dbt docs serve
