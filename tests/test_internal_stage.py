import os
from datetime import datetime, timedelta, timezone

from gridlens.ingest.internal_stage import to_upload


def test_uploads_new_and_locally_changed_files_only(tmp_path):
    old, changed, new = (tmp_path / n for n in ("a.ndjson.gz", "b.ndjson.gz", "c.ndjson.gz"))
    for f in (old, changed, new):
        f.write_bytes(b"x")
    staged_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    # `old` was written before it was staged; `changed` was rewritten afterwards (EIA revision).
    os.utime(old, (staged_at.timestamp() - 3600,) * 2)
    os.utime(changed, ((staged_at + timedelta(hours=1)).timestamp(),) * 2)

    staged = {"a.ndjson.gz": staged_at, "b.ndjson.gz": staged_at}
    assert [f.name for f in to_upload([old, changed, new], staged)] == ["b.ndjson.gz", "c.ndjson.gz"]
