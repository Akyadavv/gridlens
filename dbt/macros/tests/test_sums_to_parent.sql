{#
    Generic test: the children of a parent row must add up to the parent's value.

    Used to check that generation by fuel type sums to the balancing authority's reported
    net generation for the same hour. EIA publishes these as two separate series, so small
    gaps are normal; the test fails on hours that differ by more than `tolerance_pct` percent.

        - sums_to_parent:
            arguments:
              parent_model: ref('fct_hourly_demand')
              parent_column: net_generation_mwh
              join_columns: [region_code, period_utc]
              tolerance_pct: 2
#}
{% test sums_to_parent(model, column_name, parent_model, parent_column, join_columns, tolerance_pct=1, min_abs_mwh=50) %}

with children as (
    select
        {{ join_columns | join(', ') }},
        sum({{ column_name }}) as child_total
    from {{ model }}
    group by {{ join_columns | join(', ') }}
),

parents as (
    select
        {{ join_columns | join(', ') }},
        {{ parent_column }} as parent_total
    from {{ parent_model }}
    where {{ parent_column }} is not null
)

select
    p.*,
    c.child_total,
    c.child_total - p.parent_total as diff
from parents as p
inner join children as c
    on {% for col in join_columns %}p.{{ col }} = c.{{ col }}{% if not loop.last %} and {% endif %}{% endfor %}
where abs(c.child_total - p.parent_total) > greatest({{ min_abs_mwh }}, abs(p.parent_total) * {{ tolerance_pct }} / 100.0)

{% endtest %}
