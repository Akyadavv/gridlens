-- SCD Type 2 plant dimension. Join facts on plant_id and
-- `event_ts >= valid_from and event_ts < valid_to` for as-was reporting, or filter
-- `is_current` for as-is reporting.

with snapshot as (
    select * from {{ ref('snap_plants') }}
)

select
    dbt_scd_id as plant_version_key,
    plant_id,
    plant_name,
    operator_name,
    {{ dbt_utils.generate_surrogate_key(['region_code']) }} as region_key,
    region_code,
    state_code,
    primary_energy_source_code,
    {{ dbt_utils.generate_surrogate_key(['primary_fuel_type_code']) }} as fuel_type_key,
    primary_fuel_type_code as fuel_type_code,
    generator_count,
    nameplate_capacity_mw,
    net_summer_capacity_mw,
    net_winter_capacity_mw,
    first_operating_year_month,
    is_operating,
    report_month as source_report_month,
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to = to_timestamp_ntz('9999-12-31') as is_current
from snapshot
