with source as (
    select * from {{ source('open_meteo', 'weather_archive') }}
),

renamed as (
    select
        record:region_code::varchar as region_code,
        {{ open_meteo_time_to_utc('record:time_utc') }} as period_utc,
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
        order by loaded_at desc, source_file desc
    ) = 1
