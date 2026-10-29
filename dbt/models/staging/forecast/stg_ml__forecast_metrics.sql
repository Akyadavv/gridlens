{{ config(tags=["forecast_output"]) }}

select
    run_id,
    lower(model_name) as model_name,
    region_code,
    window_start,
    window_end,
    n_hours,
    mape,
    rmse_mwh,
    issued_at
from {{ source('ml', 'forecast_metrics') }}
qualify row_number() over (
        partition by run_id, model_name, region_code
        order by issued_at desc
    ) = 1
