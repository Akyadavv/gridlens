-- Objects in ANALYTICS that dbt does not own:
--   * ML schema: tables written by the Python forecast job (dbt reads them as a source)
--   * OPS schema: a stream + task that keeps a daily demand rollup fresh between dbt runs
--   * APPS schema: home of the Streamlit-in-Snowflake dashboard
--
--   snow sql -f snowflake/02_analytics_objects.sql --role TRANSFORMER

use role TRANSFORMER;
use warehouse GRIDLENS_WH;

-- ---- Forecast outputs ----------------------------------------------------------------
-- Kept in sync with gridlens.forecast.io (which also runs these statements on start-up).

create schema if not exists ANALYTICS.ML comment = 'Written by gridlens-forecast';

create table if not exists ANALYTICS.ML.DEMAND_FORECAST (
    run_id varchar not null,          -- target date (YYYY-MM-DD); re-running a day replaces it
    model_name varchar not null,      -- lightgbm | sarima | seasonal_naive
    region_code varchar not null,
    period_utc timestamp_ntz not null,
    forecast_mwh float,
    is_backtest boolean not null,
    issued_at timestamp_ntz not null
);

create table if not exists ANALYTICS.ML.FORECAST_METRICS (
    run_id varchar not null,
    model_name varchar not null,
    region_code varchar not null,     -- 'ALL' for the pooled score
    window_start date,
    window_end date,
    n_hours number,
    mape float,
    rmse_mwh float,
    issued_at timestamp_ntz not null
);

-- ---- Stream + task: hourly -> daily rollup ---------------------------------------------
-- An append-only stream records new raw rows. Every hour the task (if the stream has data)
-- recomputes only the (region, day) pairs that received new rows, from de-duplicated raw
-- data, so revisions from EIA are reflected. Consuming the stream in the MERGE advances
-- its offset atomically.

create schema if not exists ANALYTICS.OPS comment = 'Near-real-time objects outside dbt';

create table if not exists ANALYTICS.OPS.DAILY_DEMAND_ROLLUP (
    region_code varchar,
    date_utc date,
    demand_mwh number(18, 2),
    peak_demand_mwh number(18, 2),
    hours_reported number,
    refreshed_at timestamp_ltz
);

create stream if not exists ANALYTICS.OPS.REGION_DATA_STREAM
    on table RAW.EIA.REGION_DATA
    append_only = true;

create or replace task ANALYTICS.OPS.ROLLUP_DAILY_DEMAND
    warehouse = GRIDLENS_WH
    schedule = 'USING CRON 20 * * * * UTC'
    when system$stream_has_data('ANALYTICS.OPS.REGION_DATA_STREAM')
as
merge into ANALYTICS.OPS.DAILY_DEMAND_ROLLUP as t
using (
    with touched as (
        select distinct
            record:respondent::varchar as region_code,
            to_date(left(record:period::varchar, 10)) as date_utc
        from ANALYTICS.OPS.REGION_DATA_STREAM
        where record:type::varchar = 'D'
    ),

    latest as (
        select
            record:respondent::varchar as region_code,
            to_timestamp_ntz(record:period::varchar, 'YYYY-MM-DD"T"HH24') as period_utc,
            try_to_decimal(record:value::varchar, 18, 2) as demand_mwh
        from RAW.EIA.REGION_DATA
        where record:type::varchar = 'D'
        qualify row_number() over (
            partition by region_code, period_utc order by _loaded_at desc, _file desc
        ) = 1
    )

    select
        l.region_code,
        to_date(l.period_utc) as date_utc,
        sum(l.demand_mwh) as demand_mwh,
        max(l.demand_mwh) as peak_demand_mwh,
        count(l.demand_mwh) as hours_reported
    from latest as l
    inner join touched as tch
        on l.region_code = tch.region_code and to_date(l.period_utc) = tch.date_utc
    group by 1, 2
) as s
    on t.region_code = s.region_code and t.date_utc = s.date_utc
when matched then update set
    demand_mwh = s.demand_mwh,
    peak_demand_mwh = s.peak_demand_mwh,
    hours_reported = s.hours_reported,
    refreshed_at = current_timestamp()
when not matched then insert
    (region_code, date_utc, demand_mwh, peak_demand_mwh, hours_reported, refreshed_at)
values
    (s.region_code, s.date_utc, s.demand_mwh, s.peak_demand_mwh, s.hours_reported, current_timestamp());

alter task ANALYTICS.OPS.ROLLUP_DAILY_DEMAND resume;

-- ---- Dashboard -----------------------------------------------------------------------

create schema if not exists ANALYTICS.APPS comment = 'Streamlit in Snowflake apps';

-- After `snow streamlit deploy` (see dashboard/README section in the main README):
--   grant usage on streamlit ANALYTICS.APPS.GRIDLENS_DASHBOARD to role REPORTER;
