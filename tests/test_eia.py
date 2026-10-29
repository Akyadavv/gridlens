from gridlens.ingest.eia import EiaClient, EiaQuery, region_data_query
from tests.conftest import FakeResponse, FakeSession


def _page(rows, total):
    return FakeResponse(200, {"response": {"total": str(total), "data": rows}})


def test_paginates_until_total_reached():
    rows = [{"period": f"2024-01-01T{h:02d}", "value": str(h)} for h in range(5)]
    session = FakeSession([_page(rows[:2], 5), _page(rows[2:4], 5), _page(rows[4:], 5)])
    client = EiaClient("k", session=session, page_size=2)

    assert client.fetch(EiaQuery("electricity/rto/region-data", "hourly")) == rows
    offsets = [dict(c["params"])["offset"] for c in session.calls]
    assert offsets == ["0", "2", "4"]


def test_stops_on_empty_page_even_if_total_is_wrong():
    session = FakeSession([_page([{"a": 1}], 10), _page([], 10)])
    client = EiaClient("k", session=session, page_size=1)
    assert client.fetch(EiaQuery("r", "hourly")) == [{"a": 1}]
    assert len(session.calls) == 2


def test_query_params_shape():
    q = region_data_query(["CISO", "PJM"], "2024-01-01T00", "2024-01-01T23")
    params = q.params("KEY", offset=0, length=5000)
    assert ("api_key", "KEY") in params
    assert ("facets[respondent][]", "CISO") in params
    assert ("facets[respondent][]", "PJM") in params
    assert ("facets[type][]", "DF") in params
    assert ("data[0]", "value") in params
    assert ("sort[0][column]", "period") in params
    assert ("start", "2024-01-01T00") in params
