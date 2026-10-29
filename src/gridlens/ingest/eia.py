"""EIA API v2 client: API-key auth, offset pagination, retries.

Docs: https://www.eia.gov/opendata/documentation.php
The API returns at most 5,000 rows per request, so everything goes through `iter_rows`,
which follows `offset` until it has read `response.total` rows.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import requests

from gridlens.common.logging import get_logger, kv
from gridlens.ingest.http import get_json

log = get_logger(__name__)

BASE_URL = "https://api.eia.gov/v2"
MAX_PAGE_SIZE = 5000


@dataclass(frozen=True)
class EiaQuery:
    route: str  # e.g. "electricity/rto/region-data"
    frequency: str  # "hourly" (UTC) | "local-hourly" | "monthly" | ...
    data_fields: Sequence[str] = ("value",)
    facets: dict[str, Sequence[str]] = field(default_factory=dict)
    start: str | None = None
    end: str | None = None

    def params(self, api_key: str, offset: int, length: int) -> list[tuple[str, str]]:
        # The API wants repeated bracketed keys, so build a list of tuples, not a dict.
        p: list[tuple[str, str]] = [("api_key", api_key), ("frequency", self.frequency)]
        p += [(f"data[{i}]", f) for i, f in enumerate(self.data_fields)]
        for facet, values in sorted(self.facets.items()):
            p += [(f"facets[{facet}][]", v) for v in values]
        if self.start:
            p.append(("start", self.start))
        if self.end:
            p.append(("end", self.end))
        # Stable sort is required for offset pagination to be deterministic.
        p += [
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "asc"),
            ("offset", str(offset)),
            ("length", str(length)),
        ]
        return p


class EiaClient:
    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        page_size: int = MAX_PAGE_SIZE,
        **http_kwargs,
    ):
        if not 0 < page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be in 1..{MAX_PAGE_SIZE}")
        self.api_key = api_key
        self.session = session or requests.Session()
        self.page_size = page_size
        self.http_kwargs = http_kwargs

    def iter_rows(self, query: EiaQuery) -> Iterator[dict]:
        url = f"{BASE_URL}/{query.route.strip('/')}/data/"
        offset = 0
        total: int | None = None
        while total is None or offset < total:
            payload = get_json(
                self.session,
                url,
                params=query.params(self.api_key, offset, self.page_size),
                **self.http_kwargs,
            )
            response = payload.get("response") or {}
            for warning in response.get("warnings", []) or []:
                log.warning("eia warning", extra=kv(route=query.route, warning=warning))

            # `total` is a string in some API versions.
            total = int(response.get("total") or 0)
            rows = response.get("data") or []
            log.info(
                "eia page",
                extra=kv(route=query.route, offset=offset, rows=len(rows), total=total),
            )
            if not rows:
                break  # defensive: never loop forever if total and data disagree
            yield from rows
            offset += len(rows)

    def fetch(self, query: EiaQuery) -> list[dict]:
        return list(self.iter_rows(query))


# ---- Dataset definitions -------------------------------------------------------------

def region_data_query(regions: Sequence[str], start: str, end: str) -> EiaQuery:
    """Hourly (UTC) demand (D), day-ahead demand forecast (DF), net generation (NG)
    and total interchange (TI) per balancing authority."""
    return EiaQuery(
        route="electricity/rto/region-data",
        frequency="hourly",
        facets={"respondent": list(regions), "type": ["D", "DF", "NG", "TI"]},
        start=start,
        end=end,
    )


def fuel_type_query(regions: Sequence[str], start: str, end: str) -> EiaQuery:
    """Hourly (UTC) net generation by energy source per balancing authority."""
    return EiaQuery(
        route="electricity/rto/fuel-type-data",
        frequency="hourly",
        facets={"respondent": list(regions)},
        start=start,
        end=end,
    )


GENERATOR_FIELDS = (
    "nameplate-capacity-mw",
    "net-summer-capacity-mw",
    "net-winter-capacity-mw",
    "operating-year-month",
    "planned-retirement-year-month",
)


def generator_capacity_query(regions: Sequence[str], month: str) -> EiaQuery:
    """EIA-860M monthly inventory of operating generators (plant metadata for SCD2)."""
    return EiaQuery(
        route="electricity/operating-generator-capacity",
        frequency="monthly",
        data_fields=GENERATOR_FIELDS,
        facets={"balancing_authority_code": list(regions)},
        start=month,
        end=month,
    )
