{#
    prod: use the layer name as-is      -> ANALYTICS.MARTS
    dev/ci: prefix with the target schema -> DEV.DBT_ANKIT_MARTS, DEV.CI_PR_42_MARTS
    so developers and pull requests never collide with each other or with prod.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim | upper }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
