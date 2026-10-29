"""Run a SQL script in Snowflake with the project's key-pair connection (no Snowflake CLI needed).

    python scripts/run_sql.py snowflake/01_raw_landing.sql --role LOADER
    python scripts/run_sql.py snowflake/01b_s3_snowpipe.sql --role LOADER -D bucket=gridlens-raw-x

`-D name=value` fills `<% name %>` placeholders, the same syntax `snow sql -D` uses.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from gridlens.common.snowflake import get_connection


def render(sql: str, variables: dict[str, str]) -> str:
    def sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in variables:
            raise SystemExit(f"missing -D {name}=...")
        return variables[name]

    return re.sub(r"<%\s*(\w+)\s*%>", sub, sql)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--role", required=True)
    parser.add_argument("-D", dest="defines", action="append", default=[], metavar="NAME=VALUE")
    args = parser.parse_args(argv)

    variables = dict(d.split("=", 1) for d in args.defines)
    sql = render(args.file.read_text(encoding="utf-8"), variables)

    conn = get_connection(role=args.role)
    try:
        for cur in conn.execute_string(sql, remove_comments=True):
            first = cur.fetchone() if cur.description else None
            print(f"ok  {cur.query.strip().splitlines()[0][:90]}" + (f"  -> {first[0]}" if first else ""))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
