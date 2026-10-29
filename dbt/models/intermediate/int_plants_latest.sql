-- Current state of every plant in the most recent EIA-860M month: generators rolled up to
-- plant grain. This is what the snapshot (snapshots/snap_plants.yml) tracks over time.

with generators as (
    select * from {{ ref('stg_eia__generator_capacity') }}
    where report_month = (select max(g.report_month) from {{ ref('stg_eia__generator_capacity') }} as g)
),

fuel_by_plant as (
    select
        plant_id,
        fuel_type_code,
        energy_source_code,
        sum(nameplate_capacity_mw) as capacity_mw
    from generators
    group by 1, 2, 3
),

primary_fuel as (
    select
        plant_id,
        fuel_type_code as primary_fuel_type_code,
        energy_source_code as primary_energy_source_code
    from fuel_by_plant
    qualify row_number() over (partition by plant_id order by capacity_mw desc, energy_source_code asc) = 1
)

select
    g.plant_id,
    max(g.report_month) as report_month,
    any_value(g.plant_name) as plant_name,
    any_value(g.operator_name) as operator_name,
    any_value(g.region_code) as region_code,
    any_value(g.state_code) as state_code,
    any_value(pf.primary_fuel_type_code) as primary_fuel_type_code,
    any_value(pf.primary_energy_source_code) as primary_energy_source_code,
    count(*) as generator_count,
    round(sum(g.nameplate_capacity_mw), 1) as nameplate_capacity_mw,
    round(sum(g.net_summer_capacity_mw), 1) as net_summer_capacity_mw,
    round(sum(g.net_winter_capacity_mw), 1) as net_winter_capacity_mw,
    min(g.operating_year_month) as first_operating_year_month,
    -- A plant counts as operating if any of its generators is.
    max(iff(g.status_code = 'OP', 1, 0)) = 1 as is_operating
from generators as g
left join primary_fuel as pf
    on g.plant_id = pf.plant_id
group by 1
