from __future__ import annotations

from datetime import date

import pytest

from gridlens.common.config import IngestSettings


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.url = "https://api.eia.gov/v2/x?api_key=SECRET&frequency=hourly"
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Returns queued responses in order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def settings(tmp_path) -> IngestSettings:
    return IngestSettings(
        eia_api_key="test-key",
        storage="local",
        s3_bucket=None,
        local_root=str(tmp_path),
        lookback_days=3,
        backfill_start=date(2024, 1, 1),
    )
