{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['region_code', 'period_utc', 'fuel_type_code'],
        on_schema_change='append_new_columns',
        cluster_by=['to_date(period_utc)']
    )
}}

-- Grain: one row per region, UTC hour and fuel type. The source is already at this grain,
-- so the incremental filter can work on load time directly. Negative values are real:
-- batteries and pumped storage consume energy while charging.

with staged as (
    select * from {{ ref('stg_eia__fuel_type_data') }}
    {% if is_incremental() %}
        where loaded_at >= (select coalesce(max(t.loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }} as t)
    {% endif %}
),

regions as (
    select
        region_key,
        region_code,
        timezone
    from {{ ref('dim_region') }}
),

fuels as (
    select
        fuel_type_key,
        fuel_type_code
    from {{ ref('dim_fuel_type') }}
)

select
    r.region_key,
    coalesce(f.fuel_type_key, {{ dbt_utils.generate_surrogate_key(["'UNK'"]) }}) as fuel_type_key,
    s.region_code,
    s.fuel_type_code,
    s.period_utc,
    {{ utc_to_local('s.period_utc', 'r.timezone') }} as period_local,
    {{ date_key(utc_to_local('s.period_utc', 'r.timezone')) }} as date_key,
    hour({{ utc_to_local('s.period_utc', 'r.timezone') }}) as hour_key,
    s.net_generation_mwh,
    s.loaded_at
from staged as s
inner join regions as r
    on s.region_code = r.region_code
left join fuels as f
    on s.fuel_type_code = f.fuel_type_code
