-- SCD2 integrity: a plant can never have two open (current) versions, and versions of the
-- same plant must not overlap in time.

with versions as (
    select
        plant_id,
        valid_from,
        valid_to,
        is_current,
        lead(valid_from) over (partition by plant_id order by valid_from) as next_valid_from
    from {{ ref('dim_plant') }}
)

select
    plant_id,
    'multiple current versions' as problem
from versions
where is_current
group by 1
having count(*) > 1

union all

select
    plant_id,
    'overlapping versions' as problem
from versions
where next_valid_from is not null and valid_to > next_valid_from
