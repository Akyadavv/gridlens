from datetime import date

from gridlens.ingest import eia
from gridlens.ingest.pipelines import ingest_eia_hourly, month_range, plan_window
from gridlens.ingest.storage import (
    LocalStorage,
    from_ndjson_gz,
    partition_key,
    read_watermark,
    to_ndjson_gz,
    write_watermark,
)


class FakeEiaClient:
    """Returns rows for any day not in `empty_days`."""

    def __init__(self, empty_days=()):
        self.empty_days = set(empty_days)
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        day = query.start[:10]
        if day in self.empty_days:
            return []
        return [
            {"period": f"{day}T{h:02d}", "respondent": "CISO", "type": "D", "value": "100"}
            for h in range(24)
        ]


def test_ndjson_is_deterministic_regardless_of_row_order():
    rows = [{"b": 2, "a": 1}, {"a": 0}]
    assert to_ndjson_gz(rows) == to_ndjson_gz(list(reversed(rows)))
    assert sorted(from_ndjson_gz(to_ndjson_gz(rows)), key=str) == sorted(rows, key=str)


def test_rerun_is_idempotent(tmp_path):
    storage = LocalStorage(tmp_path)
    args = ("region_data", eia.region_data_query, FakeEiaClient(), storage, ["CISO"])

    first = ingest_eia_hourly(*args, date(2024, 1, 1), date(2024, 1, 2))
    snapshot = {k: storage.get_bytes(k) for k in first.keys}
    second = ingest_eia_hourly(*args, date(2024, 1, 1), date(2024, 1, 2))

    # Same keys, byte-identical content -> same S3 ETag -> Snowpipe will not reload.
    assert first.keys == second.keys
    assert all(storage.get_bytes(k) == snapshot[k] for k in second.keys)
    files = [p for p in tmp_path.rglob("*.ndjson.gz")]
    assert len(files) == 2


def test_watermark_only_advances_past_days_with_data(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeEiaClient(empty_days={"2024-01-03"})
    result = ingest_eia_hourly(
        "region_data", eia.region_data_query, client, storage, ["CISO"],
        date(2024, 1, 1), date(2024, 1, 3),
    )
    assert result.empty_partitions == ["2024-01-03"]
    assert read_watermark(storage, "region_data") == "2024-01-02"
    assert storage.get_bytes(partition_key("eia", "region_data", "2024-01-03")) is None


def test_watermark_never_moves_backwards(tmp_path):
    storage = LocalStorage(tmp_path)
    write_watermark(storage, "region_data", "2024-06-01")
    ingest_eia_hourly(
        "region_data", eia.region_data_query, FakeEiaClient(), storage, ["CISO"],
        date(2024, 1, 1), date(2024, 1, 1),
    )
    assert read_watermark(storage, "region_data") == "2024-06-01"


def test_plan_window_uses_watermark_minus_lookback(tmp_path, settings):
    storage = LocalStorage(tmp_path)
    today = date(2024, 3, 10)
    assert plan_window(storage, "region_data", settings, today) == (date(2024, 1, 1), today)

    write_watermark(storage, "region_data", "2024-03-09")
    assert plan_window(storage, "region_data", settings, today) == (date(2024, 3, 6), today)

    explicit = plan_window(storage, "region_data", settings, today, date(2023, 5, 1), date(2023, 5, 2))
    assert explicit == (date(2023, 5, 1), date(2023, 5, 2))


def test_month_range_crosses_year():
    assert month_range(date(2023, 11, 15), date(2024, 2, 1)) == [
        "2023-11", "2023-12", "2024-01", "2024-02",
    ]
