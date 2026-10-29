import json

import pytest

from gridlens.ingest.snowpipe import wait_for_pipes


class FakeConn:
    """Each call to cursor().execute pops the next status for that pipe."""

    def __init__(self, statuses: dict[str, list[dict]]):
        self.statuses = statuses

    def cursor(self):
        conn = self

        class Cursor:
            def execute(self, sql, params):
                self.pipe = params[0]

            def fetchone(self):
                queue = conn.statuses[self.pipe]
                return (json.dumps(queue.pop(0) if len(queue) > 1 else queue[0]),)

        return Cursor()


def running(pending=0):
    return {"executionState": "RUNNING", "pendingFileCount": pending}


def test_waits_until_pending_files_are_loaded():
    conn = FakeConn({"P1": [running(3), running(1), running(0)], "P2": [running(0)]})
    sleeps = []
    wait_for_pipes(conn, ["P1", "P2"], sleep=sleeps.append, clock=lambda: 0)
    assert sleeps == [30, 15, 15]  # settle, then two polls


def test_fails_fast_on_stopped_pipe():
    conn = FakeConn({"P1": [{"executionState": "STOPPED_STAGE_DROPPED"}]})
    with pytest.raises(RuntimeError, match="STOPPED"):
        wait_for_pipes(conn, ["P1"], sleep=lambda _: None)


def test_times_out():
    conn = FakeConn({"P1": [running(5)]})
    ticks = iter([0, 0, 1000])
    with pytest.raises(TimeoutError):
        wait_for_pipes(conn, ["P1"], timeout_s=60, sleep=lambda _: None, clock=lambda: next(ticks))
