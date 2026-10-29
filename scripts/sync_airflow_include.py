"""Copy the gridlens package and the dbt project into airflow/include/ for the Astro image.

    python scripts/sync_airflow_include.py && cd airflow && astro dev start

The repo stays the single source of truth; airflow/include/* is gitignored.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INCLUDE = REPO / "airflow" / "include"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info", "target", "logs", ".user.yml")


def _replace(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)


def _copy_manifest() -> None:
    """`dbt parse` (no warehouse connection) -> manifest.json, which Cosmos renders the DAG from."""
    dbt = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    # Profile values are only rendered, never used to connect, during parse.
    env = {"SNOWFLAKE_ACCOUNT": "parse", "SNOWFLAKE_USER": "parse",
           "SNOWFLAKE_PRIVATE_KEY_PATH": "parse", **os.environ, "DBT_TARGET": "prod"}
    subprocess.run(
        [str(dbt), "parse", "--profiles-dir", ".", "--quiet"], cwd=REPO / "dbt", env=env, check=True
    )
    target = INCLUDE / "dbt" / "target"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "dbt" / "target" / "manifest.json", target / "manifest.json")


def main() -> None:
    pkg = INCLUDE / "gridlens"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    _replace(REPO / "src", pkg / "src")
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(REPO / name, pkg / name)

    # `astro dev` bind-mounts include/ over the image's copy, so the installed dbt packages
    # must be synced too (Cosmos runs `dbt ls` at parse time and needs dbt_utils).
    if not (REPO / "dbt" / "dbt_packages").exists():
        raise SystemExit("Run `dbt deps` in dbt/ first.")
    _replace(REPO / "dbt", INCLUDE / "dbt")
    _copy_manifest()
    print(f"synced package and dbt project into {INCLUDE}")


if __name__ == "__main__":
    main()
