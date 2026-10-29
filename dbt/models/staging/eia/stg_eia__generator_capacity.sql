-- One row per generator per report month (EIA-860M inventory).

with source as (
    select * from {{ source('eia', 'generator_capacity') }}
),

renamed as (
    select
        to_date(record:period::varchar || '-01') as report_month,
        record:plantid::varchar as plant_id,
        record:generatorid::varchar as generator_id,
        record:plantName::varchar as plant_name,
        record:entityName::varchar as operator_name,
        record:balancing_authority_code::varchar as region_code,
        record:stateid::varchar as state_code,
        record:technology::varchar as technology,
        record:energy_source_code::varchar as energy_source_code,
        record:prime_mover_code::varchar as prime_mover_code,
        {{ eia860_to_fuel_type('record:energy_source_code::varchar', 'record:prime_mover_code::varchar') }}
            as fuel_type_code,
        record:status::varchar as status_code,
        record:statusDescription::varchar as status_description,
        try_to_double(record:"nameplate-capacity-mw"::varchar) as nameplate_capacity_mw,
        try_to_double(record:"net-summer-capacity-mw"::varchar) as net_summer_capacity_mw,
        try_to_double(record:"net-winter-capacity-mw"::varchar) as net_winter_capacity_mw,
        record:"operating-year-month"::varchar as operating_year_month,
        record:"planned-retirement-year-month"::varchar as planned_retirement_year_month,
        _file as source_file,
        _loaded_at as loaded_at
    from source
)

select * from renamed
qualify row_number() over (
        partition by plant_id, generator_id, report_month
        order by loaded_at desc, source_file desc
    ) = 1
