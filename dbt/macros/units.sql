{# Unit conversions, kept in one place so marts never hard-code factors. #}

{% macro mwh_to_gwh(column, precision=3) -%}
    round(({{ column }}) / 1000.0, {{ precision }})
{%- endmacro %}

{% macro celsius_to_fahrenheit(column, precision=1) -%}
    round(({{ column }}) * 9.0 / 5.0 + 32, {{ precision }})
{%- endmacro %}

{% macro kmh_to_ms(column, precision=2) -%}
    round(({{ column }}) / 3.6, {{ precision }})
{%- endmacro %}

{# Degree-hours relative to a 18 C (65 F) base: the standard driver of heating/cooling load. #}
{% macro cooling_degree_hours(temp_c_column, base_c=18) -%}
    greatest(({{ temp_c_column }}) - {{ base_c }}, 0)
{%- endmacro %}

{% macro heating_degree_hours(temp_c_column, base_c=18) -%}
    greatest({{ base_c }} - ({{ temp_c_column }}), 0)
{%- endmacro %}
