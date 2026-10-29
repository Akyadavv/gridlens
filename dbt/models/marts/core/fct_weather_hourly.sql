{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['region_code', 'period_utc'],
        on_schema_change='append_new_columns',
        cluster_by=['to_date(period_utc)']
    )
}}

-- Grain: one row per region and UTC hour. A row starts life as a forecast and is replaced
-- by reanalysis once the archive catches up; both arrive with a newer loaded_at, so the
-- merge picks the change up without a full refresh.

with weather as (
    select * from {{ ref('int_weather_hourly') }}
    {% if is_incremental() %}
        where loaded_at >= (select coalesce(max(t.loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }} as t)
    {% endif %}
),

regions as (
    select
        region_key,
        region_code,
        timezone
    from {{ ref('dim_region') }}
)

select
    r.region_key,
    w.region_code,
    w.period_utc,
    {{ utc_to_local('w.period_utc', 'r.timezone') }} as period_local,
    {{ date_key(utc_to_local('w.period_utc', 'r.timezone')) }} as date_key,
    hour({{ utc_to_local('w.period_utc', 'r.timezone') }}) as hour_key,
    w.weather_source,
    w.is_observed,
    w.temperature_c,
    {{ celsius_to_fahrenheit('w.temperature_c') }} as temperature_f,
    w.apparent_temperature_c,
    w.dew_point_c,
    w.relative_humidity_pct,
    w.precipitation_mm,
    w.cloud_cover_pct,
    w.wind_speed_ms,
    w.shortwave_radiation_wm2,
    {{ cooling_degree_hours('w.temperature_c') }} as cooling_degree_hours,
    {{ heating_degree_hours('w.temperature_c') }} as heating_degree_hours,
    w.loaded_at
from weather as w
inner join regions as r
    on w.region_code = r.region_code
