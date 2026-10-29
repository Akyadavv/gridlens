{# Time-zone and calendar helpers. Everything is stored in UTC; local time is derived. #}

{# EIA hourly periods look like '2024-01-01T05' and are hour-ending in UTC. #}
{% macro eia_hour_to_utc(column) -%}
    to_timestamp_ntz({{ column }}::varchar, 'YYYY-MM-DD"T"HH24')
{%- endmacro %}

{# Open-Meteo returns ISO minutes in the requested time zone (we always request UTC). #}
{% macro open_meteo_time_to_utc(column) -%}
    to_timestamp_ntz({{ column }}::varchar, 'YYYY-MM-DD"T"HH24:MI')
{%- endmacro %}

{# tz_column holds an IANA name per row (e.g. dim_region.timezone), so DST is handled per region. #}
{% macro utc_to_local(ts_column, tz_column) -%}
    convert_timezone('UTC', {{ tz_column }}, {{ ts_column }})
{%- endmacro %}

{# Integer YYYYMMDD key used by dim_date. #}
{% macro date_key(date_expression) -%}
    to_number(to_char(({{ date_expression }})::date, 'YYYYMMDD'))
{%- endmacro %}
