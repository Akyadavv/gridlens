from types import SimpleNamespace

from gridlens.common.alerts import format_failure, notify_failure


class RecordingSession:
    def __init__(self, fail=False):
        self.posts = []
        self.fail = fail

    def post(self, url, json=None, timeout=None):
        if self.fail:
            raise ConnectionError("slack down")
        self.posts.append((url, json))


def _context():
    ti = SimpleNamespace(dag_id="gridlens_daily", task_id="dbt_build", try_number=2, log_url="http://x/log")
    return {"task_instance": ti, "ds": "2024-05-01", "exception": ValueError("boom")}


def test_message_has_task_error_and_link():
    text = format_failure(_context())
    assert "gridlens_daily.dbt_build" in text
    assert "boom" in text
    assert "http://x/log" in text


def test_posts_to_webhook():
    session = RecordingSession()
    notify_failure(_context(), webhook_url="https://hooks/x", session=session)
    assert session.posts[0][0] == "https://hooks/x"
    assert "dbt_build" in session.posts[0][1]["text"]


def test_never_raises(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    notify_failure(_context())  # no webhook: logs only
    notify_failure(_context(), webhook_url="https://hooks/x", session=RecordingSession(fail=True))
