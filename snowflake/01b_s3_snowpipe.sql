-- S3 external stage + one auto-ingest Snowpipe per raw table.
-- Prereq: 01_raw_landing.sql, and terraform with the S3 bucket + GRIDLENS_S3_INT integration.
--
--   snow sql -f snowflake/01b_s3_snowpipe.sql -D "bucket=gridlens-raw-<suffix>" --role LOADER
--
-- Afterwards: SHOW PIPES IN DATABASE RAW -> copy `notification_channel` into the
-- terraform variable snowpipe_sqs_arn and apply again to wire S3 -> SQS -> Snowpipe.

use role LOADER;
use warehouse GRIDLENS_WH;

create stage if not exists RAW.LANDING.S3_RAW
    url = 's3://<% bucket %>/'
    storage_integration = GRIDLENS_S3_INT
    file_format = RAW.LANDING.NDJSON_GZ;

-- ---- Snowpipes -----------------------------------------------------------------------
-- Snowpipe remembers (file name, ETag) for 14 days, so an identical re-upload from a
-- re-run is skipped and a revised file (new bytes) is loaded again.

create pipe if not exists RAW.EIA.REGION_DATA_PIPE auto_ingest = true as
copy into RAW.EIA.REGION_DATA (record, _file, _file_row_number, _file_last_modified, _loaded_at)
from (
    select $1, metadata$filename, metadata$file_row_number, metadata$file_last_modified, current_timestamp()
    from @RAW.LANDING.S3_RAW/eia/region_data/
);

create pipe if not exists RAW.EIA.FUEL_TYPE_DATA_PIPE auto_ingest = true as
copy into RAW.EIA.FUEL_TYPE_DATA (record, _file, _file_row_number, _file_last_modified, _loaded_at)
from (
    select $1, metadata$filename, metadata$file_row_number, metadata$file_last_modified, current_timestamp()
    from @RAW.LANDING.S3_RAW/eia/fuel_type_data/
);

create pipe if not exists RAW.EIA.GENERATOR_CAPACITY_PIPE auto_ingest = true as
copy into RAW.EIA.GENERATOR_CAPACITY (record, _file, _file_row_number, _file_last_modified, _loaded_at)
from (
    select $1, metadata$filename, metadata$file_row_number, metadata$file_last_modified, current_timestamp()
    from @RAW.LANDING.S3_RAW/eia/generator_capacity/
);

create pipe if not exists RAW.OPEN_METEO.WEATHER_ARCHIVE_PIPE auto_ingest = true as
copy into RAW.OPEN_METEO.WEATHER_ARCHIVE (record, _file, _file_row_number, _file_last_modified, _loaded_at)
from (
    select $1, metadata$filename, metadata$file_row_number, metadata$file_last_modified, current_timestamp()
    from @RAW.LANDING.S3_RAW/open_meteo/weather_archive/
);

create pipe if not exists RAW.OPEN_METEO.WEATHER_FORECAST_PIPE auto_ingest = true as
copy into RAW.OPEN_METEO.WEATHER_FORECAST (record, _file, _file_row_number, _file_last_modified, _loaded_at)
from (
    select $1, metadata$filename, metadata$file_row_number, metadata$file_last_modified, current_timestamp()
    from @RAW.LANDING.S3_RAW/open_meteo/weather_forecast/
);

-- Load files that were uploaded before the pipes existed (backfill). Covers the last 7 days
-- of uploads; for older files run a one-off COPY INTO with the same SELECT.
alter pipe RAW.EIA.REGION_DATA_PIPE refresh;
alter pipe RAW.EIA.FUEL_TYPE_DATA_PIPE refresh;
alter pipe RAW.EIA.GENERATOR_CAPACITY_PIPE refresh;
alter pipe RAW.OPEN_METEO.WEATHER_ARCHIVE_PIPE refresh;
alter pipe RAW.OPEN_METEO.WEATHER_FORECAST_PIPE refresh;

show pipes in database RAW;
