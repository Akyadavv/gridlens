{{ config(tags=["forecast_output"]) }}

with source as (
    select * from {{ source('ml', 'demand_forecast') }}
)

select
    run_id,
    lower(model_name) as model_name,
    region_code,
    period_utc,
    forecast_mwh,
    is_backtest,
    issued_at
from source
qualify row_number() over (
        partition by model_name, region_code, period_utc, is_backtest
        order by issued_at desc
    ) = 1
