"""Raw landing zone: S3 (prod) or local filesystem (dev/tests), same key layout.

Idempotency, layer 1: every (dataset, partition) maps to exactly one deterministic key,
and the gzip bytes are deterministic (sorted rows, mtime=0). Re-running a day overwrites
the same object with identical bytes, so the S3 ETag is unchanged and Snowpipe skips it.
If EIA revised the data, the bytes differ, Snowpipe loads the new version, and dbt staging
keeps only the latest-loaded row per natural key (idempotency, layer 2).
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes) -> str: ...
    def get_bytes(self, key: str) -> bytes | None: ...


def partition_key(source: str, dataset: str, partition: str) -> str:
    """e.g. eia/region_data/date=2024-01-01/region_data_2024-01-01.ndjson.gz"""
    return f"{source}/{dataset}/date={partition}/{dataset}_{partition}.ndjson.gz"


def to_ndjson_gz(rows: list[dict]) -> bytes:
    lines = sorted(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    return buf.getvalue()


def from_ndjson_gz(data: bytes) -> list[dict]:
    text = gzip.decompress(data).decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on the same filesystem
        return str(path)

    def get_bytes(self, key: str) -> bytes | None:
        path = self.root / key
        return path.read_bytes() if path.exists() else None


class S3Storage:
    def __init__(self, bucket: str, client=None):
        import boto3

        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def put_bytes(self, key: str, data: bytes) -> str:
        content_type = "application/gzip" if key.endswith(".gz") else "application/json"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return f"s3://{self.bucket}/{key}"

    def get_bytes(self, key: str) -> bytes | None:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None


def make_storage(kind: str, s3_bucket: str | None, local_root: str) -> Storage:
    if kind == "s3":
        if not s3_bucket:
            raise RuntimeError("GRIDLENS_S3_BUCKET must be set when GRIDLENS_STORAGE=s3")
        return S3Storage(s3_bucket)
    if kind == "local":
        return LocalStorage(local_root)
    raise ValueError(f"Unknown storage backend: {kind}")


# ---- Watermarks ------------------------------------------------------------------------

def _state_key(dataset: str) -> str:
    return f"_state/{dataset}.json"


def read_watermark(storage: Storage, dataset: str) -> str | None:
    raw = storage.get_bytes(_state_key(dataset))
    return json.loads(raw)["watermark"] if raw else None


def write_watermark(storage: Storage, dataset: str, watermark: str) -> None:
    storage.put_bytes(_state_key(dataset), json.dumps({"watermark": watermark}).encode())
