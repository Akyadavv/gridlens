"""Structured (key=value) logging that reads well in Airflow task logs."""

from __future__ import annotations

import logging
import os


class _KVFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = getattr(record, "kv", None)
        if extras:
            base += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        return base


def get_logger(name: str) -> logging.Logger:
    # Configure only the package root: child loggers ("gridlens.ingest.eia") propagate to it,
    # so each record is written once. Under Airflow the root logger already has handlers.
    package = logging.getLogger("gridlens")
    if not logging.getLogger().handlers and not package.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_KVFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        package.addHandler(handler)
        package.setLevel(os.getenv("GRIDLENS_LOG_LEVEL", "INFO"))
        # Libraries may configure the root logger later; don't print our records twice.
        package.propagate = False
    return logging.getLogger(name)


def kv(**fields: object) -> dict:
    """Usage: log.info("page fetched", extra=kv(offset=0, rows=5000))."""
    return {"kv": fields}
