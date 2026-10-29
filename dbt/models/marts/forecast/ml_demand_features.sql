-- Feature table read by the Python forecast job (gridlens.forecast).
-- Grain: region x UTC hour, covering every hour that has demand OR weather, so the
-- next-day target hours exist (with forecast weather, null demand) before demand does.
-- Lag/rolling features are built in Python, where the backtest controls the cut-off.

with demand as (
    select
        region_code,
        period_utc,
        demand_mwh,
        eia_day_ahead_forecast_mwh
    from {{ ref('fct_hourly_demand') }}
),

weather as (
    select
        region_code,
        period_utc,
        is_observed,
        temperature_c,
        apparent_temperature_c,
        dew_point_c,
        relative_humidity_pct,
        cloud_cover_pct,
        wind_speed_ms,
        shortwave_radiation_wm2,
        cooling_degree_hours,
        heating_degree_hours
    from {{ ref('fct_weather_hourly') }}
),

spine as (
    select
        region_code,
        period_utc
    from demand
    union distinct
    select
        region_code,
        period_utc
    from weather
),

regions as (
    select
        region_code,
        timezone
    from {{ ref('dim_region') }}
),

calendar as (
    select
        date_key,
        day_of_week_iso,
        month_number,
        day_of_year,
        is_weekend,
        is_holiday
    from {{ ref('dim_date') }}
),

localized as (
    select
        s.region_code,
        s.period_utc,
        {{ utc_to_local('s.period_utc', 'r.timezone') }} as period_local
    from spine as s
    inner join regions as r
        on s.region_code = r.region_code
)

select
    l.region_code,
    l.period_utc,
    l.period_local,
    hour(l.period_local) as hour_local,
    c.day_of_week_iso,
    c.month_number,
    c.day_of_year,
    c.is_weekend,
    c.is_holiday,
    d.demand_mwh,
    d.eia_day_ahead_forecast_mwh,
    w.is_observed as weather_is_observed,
    w.temperature_c,
    w.apparent_temperature_c,
    w.dew_point_c,
    w.relative_humidity_pct,
    w.cloud_cover_pct,
    w.wind_speed_ms,
    w.shortwave_radiation_wm2,
    w.cooling_degree_hours,
    w.heating_degree_hours
from localized as l
inner join calendar as c
    on {{ date_key('l.period_local') }} = c.date_key
left join demand as d
    on l.region_code = d.region_code and l.period_utc = d.period_utc
left join weather as w
    on l.region_code = w.region_code and l.period_utc = w.period_utc
