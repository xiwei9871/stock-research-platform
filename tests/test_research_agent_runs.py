from stock_research import research_objects


class _Cursor:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, sql, params=None):
        self.captured.append((sql, params))


class _Conn:
    def __init__(self, captured):
        self.captured = captured

    def cursor(self):
        return self

    def __enter__(self):
        return _Cursor(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.captured.append(("COMMIT", None))


class _Ctx:
    def __init__(self, captured):
        self.captured = captured

    def __enter__(self):
        return _Conn(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False


def test_record_agent_run_writes_run_and_events(monkeypatch):
    captured = []
    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx(captured))

    run_id = research_objects.record_agent_run(
        {
            "workflow": "daily_brief_draft",
            "request_id": "req-1",
            "trade_date": "2026-07-06",
            "input_payload": {"asset_id": "CN:SZ:000001"},
            "events": [
                {"event_type": "model_call", "status": "ok", "payload": {"model": "test"}},
                {"event_type": "human_review", "status": "pending", "payload": {"reviewer": "operator"}},
            ],
        },
        service="research",
    )

    assert run_id.startswith("agent_run:")
    assert any("INSERT INTO research.agent_run" in sql for sql, _params in captured)
    assert any("INSERT INTO research.agent_run_event" in sql for sql, _params in captured)


def test_record_agent_run_requires_workflow():
    try:
        research_objects.record_agent_run({}, service="research")
    except ValueError as exc:
        assert str(exc) == "workflow_required"
    else:
        raise AssertionError("workflow_required was not raised")
