-- One row per region, UTC hour and series type. Raw can hold the same hour several times
-- (re-pulls inside the lookback window, EIA revisions); the most recently loaded row wins.

with source as (
    select * from {{ source('eia', 'region_data') }}
),

renamed as (
    select
        record:respondent::varchar as region_code,
        {{ eia_hour_to_utc('record:period') }} as period_utc,
        record:type::varchar as series_type,
        try_to_decimal(record:value::varchar, 18, 2) as value_mwh,
        record:"value-units"::varchar as value_units,
        _file as source_file,
        _loaded_at as loaded_at
    from source
)

select * from renamed
qualify row_number() over (
        partition by region_code, period_utc, series_type
        order by loaded_at desc, source_file desc
    ) = 1
