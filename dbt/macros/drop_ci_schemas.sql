{#
    Drops every schema a pull request created, e.g. CI_PR_42 and CI_PR_42_MARTS, but not CI_PR_421.
        dbt run-operation drop_ci_schemas --args '{prefix: CI_PR_42}' --target ci
#}
{% macro drop_ci_schemas(prefix) %}
    {% set prefix = prefix | upper %}
    {% if not prefix.startswith('CI_') %}
        {{ exceptions.raise_compiler_error("Refusing to drop schemas without a CI_ prefix: " ~ prefix) }}
    {% endif %}

    {% set schemas = run_query(
        "select schema_name from " ~ target.database ~ ".information_schema.schemata "
        ~ "where schema_name = '" ~ prefix ~ "' or startswith(schema_name, '" ~ prefix ~ "_')"
    ) %}

    {% for row in schemas.rows %}
        {% do log("dropping " ~ target.database ~ "." ~ row[0], info=true) %}
        {% do run_query("drop schema if exists " ~ target.database ~ "." ~ row[0] ~ " cascade") %}
    {% endfor %}
{% endmacro %}
