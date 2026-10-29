"""Regenerate dbt/seeds/us_holidays.csv (US federal holidays) for the dim_date range.

    python scripts/generate_holiday_seed.py            # needs `pip install holidays`
"""

from __future__ import annotations

import csv
from pathlib import Path

import holidays

SEED = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "us_holidays.csv"
YEARS = range(2019, 2031)


def main() -> None:
    rows = sorted(holidays.country_holidays("US", years=YEARS).items())
    with SEED.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["holiday_date", "holiday_name"])
        for day, name in rows:
            writer.writerow([day.isoformat(), name])
    print(f"wrote {len(rows)} holidays to {SEED}")


if __name__ == "__main__":
    main()
