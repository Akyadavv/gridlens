-- One weather row per region and UTC hour. Reanalysis ("archive") is the best estimate of
-- what actually happened, so it wins; the latest forecast fills recent and future hours.

with archive as (
    select
        *,
        'archive' as weather_source,
        true as is_observed
    from {{ ref('stg_open_meteo__weather_archive') }}
),

forecast as (
    select
        f.*,
        'forecast' as weather_source,
        false as is_observed
    from {{ ref('stg_open_meteo__weather_forecast') }} as f
    left join archive as a
        on f.region_code = a.region_code and f.period_utc = a.period_utc
    where a.region_code is null
),

unioned as (
    select
        region_code,
        period_utc,
        weather_source,
        is_observed,
        temperature_c,
        apparent_temperature_c,
        dew_point_c,
        relative_humidity_pct,
        precipitation_mm,
        cloud_cover_pct,
        wind_speed_ms,
        shortwave_radiation_wm2,
        loaded_at
    from archive
    union all
    select
        region_code,
        period_utc,
        weather_source,
        is_observed,
        temperature_c,
        apparent_temperature_c,
        dew_point_c,
        relative_humidity_pct,
        precipitation_mm,
        cloud_cover_pct,
        wind_speed_ms,
        shortwave_radiation_wm2,
        loaded_at
    from forecast
)

select * from unioned
