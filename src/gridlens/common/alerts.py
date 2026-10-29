"""Failure alerts for Airflow tasks: post to a Slack incoming webhook if one is configured."""

from __future__ import annotations

import os

import requests

from gridlens.common.logging import get_logger, kv

log = get_logger(__name__)


def format_failure(context: dict) -> str:
    ti = context.get("task_instance") or context.get("ti")
    dag_id = getattr(ti, "dag_id", "?")
    task_id = getattr(ti, "task_id", "?")
    try_number = getattr(ti, "try_number", "?")
    log_url = getattr(ti, "log_url", "")
    exc = context.get("exception")
    lines = [
        f":red_circle: *{dag_id}.{task_id}* failed (try {try_number})",
        f"logical date: {context.get('logical_date') or context.get('ds', '?')}",
    ]
    if exc:
        lines.append(f"error: `{str(exc)[:300]}`")
    if log_url:
        lines.append(f"<{log_url}|task log>")
    return "\n".join(lines)


def notify_failure(context: dict, webhook_url: str | None = None, session=None) -> None:
    """Airflow `on_failure_callback`. Never raises: a broken alert must not mask the failure."""
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    text = format_failure(context)
    if not url:
        log.error("task failed (no SLACK_WEBHOOK_URL set)", extra=kv(message=text))
        return
    try:
        (session or requests).post(url, json={"text": text}, timeout=10)
    except Exception as exc:
        log.error("slack alert failed", extra=kv(error=exc))
