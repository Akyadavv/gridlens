"""Snowflake connection helper using key-pair auth (PEM from env var or file)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # CLIs like gridlens-forecast import this without going through config.py


def _load_private_key_der() -> bytes:
    from cryptography.hazmat.primitives import serialization

    pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    if pem:
        pem_bytes = pem.replace("\\n", "\n").encode()
    else:
        path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
        if not path:
            raise RuntimeError("Set SNOWFLAKE_PRIVATE_KEY or SNOWFLAKE_PRIVATE_KEY_PATH")
        pem_bytes = Path(path).expanduser().read_bytes()

    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    key = serialization.load_pem_private_key(
        pem_bytes, password=passphrase.encode() if passphrase else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_connection(database: str | None = None, schema: str | None = None, role: str | None = None):
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=_load_private_key_der(),
        role=role or os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "GRIDLENS_WH"),
        database=database,
        schema=schema,
        session_parameters={"QUERY_TAG": "gridlens"},
    )
