with source as (
    select * from {{ source('eia', 'fuel_type_data') }}
),

renamed as (
    select
        record:respondent::varchar as region_code,
        {{ eia_hour_to_utc('record:period') }} as period_utc,
        record:fueltype::varchar as fuel_type_code,
        try_to_decimal(record:value::varchar, 18, 2) as net_generation_mwh,
        _file as source_file,
        _loaded_at as loaded_at
    from source
)

select * from renamed
qualify row_number() over (
        partition by region_code, period_utc, fuel_type_code
        order by loaded_at desc, source_file desc
    ) = 1
