{{ config(tags=["forecast_output"]) }}

-- Grain: one row per model, region and local day. Daily MAPE for every gridlens model,
-- plus EIA's published day-ahead forecast scored on exactly the same hours (model_name =
-- 'eia_day_ahead'), which makes "did we beat EIA?" a simple filter.

-- An hour can have both a live forecast and a (later) backtest forecast; score the live one.
with scored as (
    select
        model_name,
        region_key,
        region_code,
        date_key,
        abs_pct_error,
        eia_abs_pct_error,
        error_mwh
    from {{ ref('fct_demand_forecast') }}
    where abs_pct_error is not null
    qualify row_number() over (
            partition by model_name, region_code, period_utc order by is_backtest
        ) = 1
),

gridlens_models as (
    select
        model_name,
        region_key,
        region_code,
        date_key,
        count(*) as n_hours,
        avg(abs_pct_error) as mape_pct,
        sqrt(avg(square(error_mwh))) as rmse_mwh
    from scored
    group by 1, 2, 3, 4
),

-- Score EIA on the hours the LightGBM model forecast, so the comparison is fair.
eia as (
    select
        'eia_day_ahead' as model_name,
        region_key,
        region_code,
        date_key,
        count(*) as n_hours,
        avg(eia_abs_pct_error) as mape_pct,
        null::float as rmse_mwh
    from scored
    where model_name = 'lightgbm' and eia_abs_pct_error is not null
    group by 1, 2, 3, 4
)

select * from gridlens_models
union all
select * from eia
