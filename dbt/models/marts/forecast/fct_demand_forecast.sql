{{ config(tags=["forecast_output"]) }}

-- Grain: one row per model, region, UTC hour and live/backtest flag.
-- Joins each gridlens forecast to what actually happened and to EIA's own day-ahead
-- forecast for the same hour, so accuracy can be compared like for like.

with forecasts as (
    select * from {{ ref('stg_ml__demand_forecast') }}
),

actuals as (
    select
        region_key,
        region_code,
        period_utc,
        period_local,
        date_key,
        hour_key,
        demand_mwh,
        eia_day_ahead_forecast_mwh
    from {{ ref('fct_hourly_demand') }}
),

regions as (
    select
        region_key,
        region_code,
        timezone
    from {{ ref('dim_region') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['f.model_name', 'f.region_code', 'f.period_utc', 'f.is_backtest']) }}
        as forecast_key,
    f.model_name,
    r.region_key,
    f.region_code,
    f.period_utc,
    {{ utc_to_local('f.period_utc', 'r.timezone') }} as period_local,
    {{ date_key(utc_to_local('f.period_utc', 'r.timezone')) }} as date_key,
    hour({{ utc_to_local('f.period_utc', 'r.timezone') }}) as hour_key,
    f.is_backtest,
    f.run_id,
    f.issued_at,
    f.forecast_mwh,
    a.demand_mwh as actual_demand_mwh,
    a.eia_day_ahead_forecast_mwh,
    f.forecast_mwh - a.demand_mwh as error_mwh,
    iff(a.demand_mwh > 0, abs(f.forecast_mwh - a.demand_mwh) / a.demand_mwh * 100, null)
        as abs_pct_error,
    iff(a.demand_mwh > 0, abs(a.eia_day_ahead_forecast_mwh - a.demand_mwh) / a.demand_mwh * 100, null)
        as eia_abs_pct_error
from forecasts as f
inner join regions as r
    on f.region_code = r.region_code
left join actuals as a
    on f.region_code = a.region_code and f.period_utc = a.period_utc
