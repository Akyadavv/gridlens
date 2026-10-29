{#
    EIA-860 uses detailed energy-source codes (BIT, SUB, DFO, ...); the hourly EIA-930 data
    uses broad fuel types (COL, OIL, ...). Mapping 860 -> 930 lets dim_plant and
    fct_generation_by_fuel share one conformed dim_fuel_type.
    Pumped storage is energy source WAT with prime mover PS in 860, but its own PS fuel in 930.
#}
{% macro eia860_to_fuel_type(column, prime_mover_column=none) -%}
    case
        {%- if prime_mover_column %}
        when {{ prime_mover_column }} = 'PS' then 'PS'
        {%- endif %}
        when {{ column }} in ('BIT', 'SUB', 'LIG', 'ANT', 'RC', 'WC', 'SGC') then 'COL'
        when {{ column }} in ('NG', 'OG', 'BFG', 'SGP') then 'NG'
        when {{ column }} in ('DFO', 'RFO', 'JF', 'KER', 'PC', 'WO') then 'OIL'
        when {{ column }} = 'NUC' then 'NUC'
        when {{ column }} = 'WAT' then 'WAT'
        when {{ column }} = 'WND' then 'WND'
        when {{ column }} = 'SUN' then 'SUN'
        when {{ column }} = 'GEO' then 'GEO'
        when {{ column }} = 'MWH' then 'BAT'
        when {{ column }} is null then 'UNK'
        else 'OTH'
    end
{%- endmacro %}
