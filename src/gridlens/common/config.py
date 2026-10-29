"""Settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class IngestSettings:
    eia_api_key: str | None
    storage: str
    s3_bucket: str | None
    local_root: str
    lookback_days: int
    backfill_start: date

    @classmethod
    def from_env(cls) -> IngestSettings:
        return cls(
            eia_api_key=_env("EIA_API_KEY"),
            storage=_env("GRIDLENS_STORAGE", "local"),
            s3_bucket=_env("GRIDLENS_S3_BUCKET"),
            local_root=_env("GRIDLENS_LOCAL_ROOT", "./data/raw"),
            lookback_days=int(_env("GRIDLENS_LOOKBACK_DAYS", "3")),
            backfill_start=date.fromisoformat(_env("GRIDLENS_BACKFILL_START", "2024-01-01")),
        )

    def require_eia_key(self) -> str:
        if not self.eia_api_key:
            raise RuntimeError("EIA_API_KEY is not set. Get a free key at eia.gov/opendata.")
        return self.eia_api_key
