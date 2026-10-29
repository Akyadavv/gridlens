import pytest
import requests

from gridlens.ingest.http import HttpError, _redact, get_json
from tests.conftest import FakeResponse, FakeSession


def test_retries_on_5xx_then_succeeds():
    session = FakeSession([FakeResponse(503), FakeResponse(429), FakeResponse(200, {"ok": 1})])
    sleeps = []
    assert get_json(session, "u", sleep=sleeps.append) == {"ok": 1}
    assert len(session.calls) == 3
    assert len(sleeps) == 2


def test_honours_retry_after_header():
    session = FakeSession([FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, {})])
    sleeps = []
    get_json(session, "u", sleep=sleeps.append)
    assert sleeps == [7.0]


def test_retries_on_connection_error():
    session = FakeSession([requests.ConnectionError("boom"), FakeResponse(200, {"ok": 1})])
    assert get_json(session, "u", sleep=lambda _: None) == {"ok": 1}


def test_does_not_retry_4xx():
    session = FakeSession([FakeResponse(403, {"error": "bad key"})])
    with pytest.raises(HttpError) as exc:
        get_json(session, "u", sleep=lambda _: None)
    assert exc.value.status == 403
    assert len(session.calls) == 1
    assert "SECRET" not in str(exc.value)  # API key is redacted


def test_gives_up_after_max_retries():
    session = FakeSession([FakeResponse(500)] * 4)
    with pytest.raises(HttpError):
        get_json(session, "u", max_retries=3, sleep=lambda _: None)
    assert len(session.calls) == 4


def test_redact():
    assert _redact("https://x/?a=1&api_key=abc&b=2") == "https://x/?a=1&api_key=***&b=2"
    assert _redact("https://x/?api_key=abc") == "https://x/?api_key=***"
