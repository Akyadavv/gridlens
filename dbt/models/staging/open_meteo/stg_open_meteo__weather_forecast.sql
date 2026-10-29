-- Every daily file re-forecasts overlapping hours; keep the most recent issue per hour.
-- The issue date is in the file name (weather_forecast_2024-05-01.ndjson.gz), which holds for
-- both the S3 key layout (.../date=2024-05-01/...) and the flat internal-stage layout.

with source as (
    select * from {{ source('open_meteo', 'weather_forecast') }}
),

renamed as (
    select
        record:region_code::varchar as region_code,
        {{ open_meteo_time_to_utc('record:time_utc') }} as period_utc,
        to_date(regexp_substr(_file, '_([0-9]{4}-[0-9]{2}-[0-9]{2})[.]ndjson', 1, 1, 'e', 1)) as issue_date,
        record:temperature_2m::float as temperature_c,
        record:apparent_temperature::float as apparent_temperature_c,
        record:dew_point_2m::float as dew_point_c,
        record:relative_humidity_2m::float as relative_humidity_pct,
        record:precipitation::float as precipitation_mm,
        record:cloud_cover::float as cloud_cover_pct,
        {{ kmh_to_ms('record:wind_speed_10m::float') }} as wind_speed_ms,
        record:shortwave_radiation::float as shortwave_radiation_wm2,
        _file as source_file,
        _loaded_at as loaded_at
    from source
)

select * from renamed
qualify row_number() over (
        partition by region_code, period_utc
        order by issue_date desc, loaded_at desc
    ) = 1
