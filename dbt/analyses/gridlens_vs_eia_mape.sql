-- Headline numbers for the README: 30-day MAPE per model and region, next to EIA.
-- dbt compile, then run the compiled SQL in Snowsight.

select
    region_code,
    model_name,
    round(sum(mape_pct * n_hours) / nullif(sum(n_hours), 0), 2) as mape_pct,
    sum(n_hours) as n_hours
from {{ ref('fct_forecast_accuracy_daily') }}
where date_key >= {{ date_key("dateadd(day, -30, current_date)") }}
group by 1, 2
order by 1, 3
