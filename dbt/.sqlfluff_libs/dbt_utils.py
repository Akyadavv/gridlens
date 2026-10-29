"""Minimal stand-ins for dbt_utils macros so SQLFluff's jinja templater renders valid SQL.

Only used for linting; dbt itself uses the real package from dbt_packages/.
"""


def generate_surrogate_key(field_list):
    return "md5(" + " || '-' || ".join(f"coalesce(({f})::varchar, '')" for f in field_list) + ")"


def date_spine(datepart, start_date, end_date):
    return (
        f"select dateadd({datepart}, seq4(), {start_date}) as date_{datepart} "
        "from table(generator(rowcount => 5000))"
    )
