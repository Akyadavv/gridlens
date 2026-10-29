"""Load local-mode raw files (GRIDLENS_STORAGE=local) into RAW through an internal stage.

The no-S3 counterpart of Snowpipe. Per dataset: files that are new, or changed locally
since they were staged, are copied to a temp folder and sent in ONE parallel PUT (one PUT
per file costs ~20 s of round trips). Then COPY INTO loads them; COPY's load history skips
files already loaded with the same checksum, so re-running is safe, just like Snowpipe.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from gridlens.common.logging import get_logger, kv

log = get_logger(__name__)

STAGE = "@RAW.LANDING.INTERNAL_RAW"
TABLES = {
    "eia/region_data": "RAW.EIA.REGION_DATA",
    "eia/fuel_type_data": "RAW.EIA.FUEL_TYPE_DATA",
    "eia/generator_capacity": "RAW.EIA.GENERATOR_CAPACITY",
    "open_meteo/weather_archive": "RAW.OPEN_METEO.WEATHER_ARCHIVE",
    "open_meteo/weather_forecast": "RAW.OPEN_METEO.WEATHER_FORECAST",
}


def staged_files(cur, prefix: str) -> dict[str, datetime]:
    """basename -> last_modified for everything already on the stage under `prefix`."""
    cur.execute(f"list {STAGE}/{prefix}/")
    return {Path(name).name: parsedate_to_datetime(modified) for name, _, _, modified in cur.fetchall()}


def to_upload(local: list[Path], staged: dict[str, datetime]) -> list[Path]:
    """New files, plus files rewritten locally after they were staged (EIA revisions)."""
    out = []
    for f in local:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if f.name not in staged or mtime > staged[f.name]:
            out.append(f)
    return out


def load(conn, root: str | Path) -> dict[str, int]:
    """Stage and COPY every dataset under `root`. Returns files loaded per table."""
    root = Path(root).resolve()
    cur = conn.cursor()
    loaded_per_table = {}
    for prefix, table in TABLES.items():
        local = sorted((root / prefix).glob("date=*/*.ndjson.gz"))
        pending = to_upload(local, staged_files(cur, prefix))
        if pending:
            with tempfile.TemporaryDirectory() as tmp:
                for f in pending:
                    shutil.copy2(f, Path(tmp) / f.name)
                pattern = (Path(tmp) / "*.ndjson.gz").as_posix()
                cur.execute(
                    f"put 'file://{pattern}' {STAGE}/{prefix}/ "
                    "auto_compress = false overwrite = true parallel = 16"
                )
        cur.execute(
            f"""copy into {table} (record, _file, _file_row_number, _file_last_modified, _loaded_at)
            from (
                select $1, metadata$filename, metadata$file_row_number,
                       metadata$file_last_modified, current_timestamp()
                from {STAGE}/{prefix}/
            )
            file_format = (format_name = 'RAW.LANDING.NDJSON_GZ')"""
        )
        # Nothing new returns a single "0 files processed" row with one column.
        loaded = [r for r in cur.fetchall() if len(r) > 1 and r[1] == "LOADED"]
        loaded_per_table[table] = len(loaded)
        log.info(
            "copied",
            extra=kv(table=table, local_files=len(local), uploaded=len(pending), files_loaded=len(loaded)),
        )
    return loaded_per_table
