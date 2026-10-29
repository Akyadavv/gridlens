{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['region_code', 'period_utc'],
        on_schema_change='append_new_columns',
        cluster_by=['to_date(period_utc)']
    )
}}

-- Grain: one row per region and UTC hour.
--
-- Incremental logic: the source is long (one row per series type) and this fact is wide,
-- so filtering staging rows by load time alone would merge half-empty rows (e.g. a revised
-- DF value without its D). Instead, find the (region, hour) keys that received any new row
-- and rebuild those keys completely from staging.

with staged as (
    select * from {{ ref('stg_eia__region_data') }}
),

{% if is_incremental() %}
    changed_keys as (
        select distinct
            region_code,
            period_utc
        from staged
        where loaded_at >= (select coalesce(max(t.loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }} as t)
    ),
{% endif %}

pivoted as (
    select
        s.region_code,
        s.period_utc,
        max(iff(s.series_type = 'D', s.value_mwh, null)) as demand_mwh,
        max(iff(s.series_type = 'DF', s.value_mwh, null)) as eia_day_ahead_forecast_mwh,
        max(iff(s.series_type = 'NG', s.value_mwh, null)) as net_generation_mwh,
        max(iff(s.series_type = 'TI', s.value_mwh, null)) as total_interchange_mwh,
        max(s.loaded_at) as loaded_at
    from staged as s
    {% if is_incremental() %}
        inner join changed_keys as k
            on s.region_code = k.region_code and s.period_utc = k.period_utc
    {% endif %}
    group by 1, 2
),

regions as (
    select
        region_key,
        region_code,
        timezone
    from {{ ref('dim_region') }}
),

final as (
    select
        r.region_key,
        p.region_code,
        p.period_utc,
        {{ utc_to_local('p.period_utc', 'r.timezone') }} as period_local,
        {{ date_key(utc_to_local('p.period_utc', 'r.timezone')) }} as date_key,
        hour({{ utc_to_local('p.period_utc', 'r.timezone') }}) as hour_key,
        p.demand_mwh,
        p.eia_day_ahead_forecast_mwh,
        p.net_generation_mwh,
        p.total_interchange_mwh,
        p.eia_day_ahead_forecast_mwh - p.demand_mwh as eia_forecast_error_mwh,
        iff(
            p.demand_mwh > 0,
            abs(p.eia_day_ahead_forecast_mwh - p.demand_mwh) / p.demand_mwh * 100,
            null
        ) as eia_forecast_ape_pct,
        p.loaded_at
    from pivoted as p
    inner join regions as r
        on p.region_code = r.region_code
)

select * from final
