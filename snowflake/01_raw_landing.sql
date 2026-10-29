-- RAW landing layer: schemas, file format, internal stage, one VARIANT table per dataset.
-- Prereq: terraform apply (roles, warehouse, RAW database).
--
--   snow sql -f snowflake/01_raw_landing.sql --role LOADER
--
-- This is enough for local mode (scripts/load_local_to_snowflake.py). For S3 + Snowpipe
-- auto-ingest, run 01b_s3_snowpipe.sql afterwards.

use role LOADER;
use warehouse GRIDLENS_WH;

create schema if not exists RAW.LANDING comment = 'Stages and file formats';
create schema if not exists RAW.EIA comment = 'EIA API v2';
create schema if not exists RAW.OPEN_METEO comment = 'Open-Meteo archive + forecast';

create file format if not exists RAW.LANDING.NDJSON_GZ
    type = json
    compression = gzip
    strip_outer_array = false
    comment = 'One JSON object per line, gzip. Written by gridlens.ingest.storage.to_ndjson_gz';

-- Local mode: scripts/load_local_to_snowflake.py PUTs files here with the S3 key layout.
create stage if not exists RAW.LANDING.INTERNAL_RAW
    file_format = RAW.LANDING.NDJSON_GZ;

-- ---- Raw tables ----------------------------------------------------------------------
-- Schema-on-read: the whole record lands as VARIANT plus load metadata. Typing and
-- de-duplication (latest _loaded_at wins per natural key) happen in dbt staging.

create table if not exists RAW.EIA.REGION_DATA (
    record variant,
    _file varchar,
    _file_row_number number,
    _file_last_modified timestamp_ntz,
    _loaded_at timestamp_ltz default current_timestamp()
);
create table if not exists RAW.EIA.FUEL_TYPE_DATA like RAW.EIA.REGION_DATA;
create table if not exists RAW.EIA.GENERATOR_CAPACITY like RAW.EIA.REGION_DATA;
create table if not exists RAW.OPEN_METEO.WEATHER_ARCHIVE like RAW.EIA.REGION_DATA;
create table if not exists RAW.OPEN_METEO.WEATHER_FORECAST like RAW.EIA.REGION_DATA;

-- Needed so TRANSFORMER can put a stream on it (02_stream_task.sql). Only the owner can set it.
alter table RAW.EIA.REGION_DATA set change_tracking = true;
