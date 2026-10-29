"""HTTP GET with retries, exponential backoff + jitter, and Retry-After support."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import requests

from gridlens.common.logging import get_logger, kv

log = get_logger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status


def get_json(
    session: requests.Session,
    url: str,
    params: dict | list[tuple[str, str]] | None = None,
    *,
    max_retries: int = 5,
    backoff_base: float = 1.0,
    backoff_cap: float = 60.0,
    timeout: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """GET `url` and return parsed JSON.

    Retries on connection errors, timeouts and 429/5xx. 4xx errors other than 429 fail
    immediately because retrying a bad request (e.g. invalid API key) never helps.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt > max_retries:
                raise
            delay = _backoff(attempt, backoff_base, backoff_cap)
            log.warning("request error, retrying", extra=kv(attempt=attempt, delay=round(delay, 2), error=type(exc).__name__))
            sleep(delay)
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in RETRYABLE_STATUS and attempt <= max_retries:
            delay = _retry_after(resp) or _backoff(attempt, backoff_base, backoff_cap)
            log.warning("retryable status, retrying", extra=kv(status=resp.status_code, attempt=attempt, delay=round(delay, 2)))
            sleep(delay)
            continue

        raise HttpError(resp.status_code, _redact(resp.url), resp.text)


def _backoff(attempt: int, base: float, cap: float) -> float:
    # "Full jitter" exponential backoff.
    return random.uniform(0, min(cap, base * 2 ** (attempt - 1)))


def _retry_after(resp: requests.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _redact(url: str) -> str:
    """Never leak the API key into logs or exception messages."""
    if "api_key=" not in url:
        return url
    head, _, tail = url.partition("api_key=")
    _, amp, rest = tail.partition("&")
    return f"{head}api_key=***{amp}{rest}"
