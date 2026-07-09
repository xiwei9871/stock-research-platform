import json
from pathlib import Path

import pytest

from stock_research import cli
from stock_research import research_external_delivery
from stock_research import research_external_delivery_attempts
from stock_research import research_objects


def _plan(status: str = "preview_ready") -> dict:
    return {
        "delivery_plan_id": "research_external_delivery_plan:abc",
        "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
        "trade_date": "2026-07-06",
        "channel": "feishu_preview",
        "dry_run": True,
        "external_send_enabled": False,
        "status": status,
        "message": {
            "title": "Research Queue Snapshot 2026-07-06",
            "summary": "Cases 2, claims 3, evidence 4, gaps 0. Gate research_ready.",
            "sections": [],
        },
        "source": {
            "package_id": "research_publication_package:abc",
            "gate_status": "research_ready",
            "snapshot_channel": "research_queue_internal",
        },
        "blockers": [],
        "warnings": ["External delivery is not connected in this version."],
    }


def test_research_schema_includes_external_delivery_attempt_tables():
    sql = research_objects.RESEARCH_OBJECTS_SQL

    assert "CREATE TABLE IF NOT EXISTS research.external_delivery_attempt" in sql
    assert "CREATE TABLE IF NOT EXISTS research.external_delivery_event" in sql
    assert "idx_external_delivery_attempt_snapshot" in sql


def test_record_dry_run_attempt_writes_attempt_and_events(monkeypatch):
    executed = []

    class _Cursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: _Conn())

    attempt_id = research_external_delivery_attempts.record_external_delivery_attempt(
        _plan(),
        created_by="operator",
        service="research",
    )

    assert attempt_id.startswith("external_delivery_attempt:")
    attempt_sql, attempt_params = executed[0]
    assert "INSERT INTO research.external_delivery_attempt" in attempt_sql
    assert attempt_params["delivery_attempt_id"] == attempt_id
    assert attempt_params["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert attempt_params["status"] == "preview_recorded"
    assert attempt_params["mode"] == "dry_run"
    assert attempt_params["dry_run"] is True
    assert attempt_params["external_send_enabled"] is False
    assert attempt_params["message_title"] == "Research Queue Snapshot 2026-07-06"
    assert attempt_params["message_hash"]
    event_types = [params["event_type"] for sql, params in executed[1:] if "INSERT INTO research.external_delivery_event" in sql]
    assert event_types == ["plan_built", "validation_passed", "dry_run_recorded"]


@pytest.mark.parametrize(
    "bad_plan,error",
    [
        ({**_plan(), "mode": "live"}, "external_delivery_live_mode_disabled"),
        ({**_plan(), "external_send_enabled": True}, "external_send_must_be_disabled"),
        ({**_plan(), "status": "sent"}, "external_delivery_status_forbidden"),
        ({**_plan(), "message": {"title": "x", "token": "secret"}}, "external_delivery_secret_forbidden"),
        ({**_plan(), "message": {"title": "x", "buy": "CN:SZ:000001"}}, "external_delivery_trading_field_forbidden"),
    ],
)
def test_record_attempt_rejects_live_secret_and_trading_fields(monkeypatch, bad_plan, error):
    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: pytest.fail("must not write invalid plan"))

    with pytest.raises(ValueError, match=error):
        research_external_delivery_attempts.record_external_delivery_attempt(bad_plan, service="research")


def test_record_snapshot_not_found_attempt_status(monkeypatch):
    executed = []

    class _Cursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: _Conn())

    attempt_id = research_external_delivery_attempts.record_external_delivery_attempt(_plan(status="snapshot_not_found"), service="research")

    assert attempt_id.startswith("external_delivery_attempt:")
    assert executed[0][1]["status"] == "snapshot_not_found"
    event_types = [params["event_type"] for sql, params in executed[1:] if "INSERT INTO research.external_delivery_event" in sql]
    assert "snapshot_not_found" in event_types


def test_list_attempts_filters_and_clamps_limit(monkeypatch):
    captured = {}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "delivery_attempt_id": "external_delivery_attempt:abc",
                "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
                "trade_date": "2026-07-06",
                "channel": "feishu_preview",
                "mode": "dry_run",
                "status": "preview_recorded",
                "dry_run": True,
                "external_send_enabled": False,
                "delivery_plan_id": "research_external_delivery_plan:abc",
                "message_title": "Research Queue Snapshot 2026-07-06",
                "created_by": "operator",
                "created_at": "2026-07-08T10:00:00+08:00",
                "error_code": "",
                "error_message": "",
            }
        ]

    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: _Conn())
    monkeypatch.setattr(research_external_delivery_attempts, "fetch_all", fake_fetch_all)

    rows = research_external_delivery_attempts.list_external_delivery_attempts(
        publication_snapshot_id="publication_snapshot:research_queue_internal:abc",
        trade_date="2026-07-06",
        channel="feishu_preview",
        limit=500,
        service="research",
    )

    assert rows[0]["delivery_attempt_id"] == "external_delivery_attempt:abc"
    assert captured["params"] == ["publication_snapshot:research_queue_internal:abc", "2026-07-06", "feishu_preview", 100]
    assert "metadata" not in rows[0]


def test_get_attempt_detail_supports_events(monkeypatch):
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        if "FROM research.external_delivery_attempt" in sql:
            return [
                {
                    "delivery_attempt_id": "external_delivery_attempt:abc",
                    "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
                    "trade_date": "2026-07-06",
                    "channel": "feishu_preview",
                    "mode": "dry_run",
                    "status": "preview_recorded",
                    "dry_run": True,
                    "external_send_enabled": False,
                    "delivery_plan_id": "research_external_delivery_plan:abc",
                    "message_title": "Research Queue Snapshot 2026-07-06",
                    "created_by": "operator",
                    "created_at": "2026-07-08T10:00:00+08:00",
                    "finished_at": "2026-07-08T10:00:01+08:00",
                    "error_code": "",
                    "error_message": "",
                    "metadata": {"warnings": ["External delivery is not connected in this version."], "token": "secret"},
                }
            ]
        return [
            {
                "delivery_event_id": "external_delivery_event:abc",
                "delivery_attempt_id": "external_delivery_attempt:abc",
                "event_index": 0,
                "event_type": "plan_built",
                "status": "ok",
                "payload": {"delivery_plan_id": "research_external_delivery_plan:abc", "secret": "nope"},
                "created_at": "2026-07-08T10:00:00+08:00",
            }
        ]

    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: _Conn())
    monkeypatch.setattr(research_external_delivery_attempts, "fetch_all", fake_fetch_all)

    detail = research_external_delivery_attempts.get_external_delivery_attempt("external_delivery_attempt:abc", service="research")

    assert detail["delivery_attempt_id"] == "external_delivery_attempt:abc"
    assert detail["events"][0]["event_type"] == "plan_built"
    encoded = json.dumps(detail, ensure_ascii=False).lower()
    assert "secret" not in encoded
    assert "token" not in encoded


def test_get_attempt_returns_none(monkeypatch):
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_external_delivery_attempts, "connect", lambda service: _Conn())
    monkeypatch.setattr(research_external_delivery_attempts, "fetch_all", lambda _conn, sql, params=None: [])

    assert research_external_delivery_attempts.get_external_delivery_attempt("external_delivery_attempt:missing", service="research") is None


def test_delivery_plan_runner_records_attempt_only_when_requested(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(research_external_delivery, "build_research_external_delivery_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(
        research_external_delivery,
        "record_external_delivery_attempt",
        lambda plan, **kwargs: calls.append((plan, kwargs)) or "external_delivery_attempt:abc",
    )

    no_record = research_external_delivery.run_research_external_delivery_plan(
        publication_snapshot_id="publication_snapshot:research_queue_internal:abc",
        output_dir=tmp_path / "no_record",
        record_attempt=False,
    )
    recorded = research_external_delivery.run_research_external_delivery_plan(
        publication_snapshot_id="publication_snapshot:research_queue_internal:abc",
        output_dir=tmp_path / "recorded",
        record_attempt=True,
    )

    assert no_record["attempt_recorded"] is False
    assert no_record["delivery_attempt_id"] is None
    assert recorded["attempt_recorded"] is True
    assert recorded["delivery_attempt_id"] == "external_delivery_attempt:abc"
    assert len(calls) == 1


def test_attempt_audit_no_attempts_writes_success_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(research_external_delivery_attempts, "list_external_delivery_attempts", lambda **kwargs: [])

    result = research_external_delivery_attempts.run_research_external_delivery_attempt_audit(
        publication_snapshot_id="publication_snapshot:missing",
        output_dir=tmp_path,
        service="research",
    )

    assert result["attempt_count"] == 0
    assert result["latest_attempt_id"] is None
    assert result["external_send_enabled_count"] == 0
    assert Path(result["json_path"]).exists()
    assert "attempt_count=0" in Path(result["markdown_path"]).read_text(encoding="utf-8")


def test_attempt_cli_wires_record_and_audit(monkeypatch, tmp_path):
    captured = {}

    def fake_plan(**kwargs):
        captured["plan"] = kwargs
        return {"status": "snapshot_not_found", "attempt_recorded": True, "delivery_attempt_id": "external_delivery_attempt:abc"}

    def fake_audit(**kwargs):
        captured["audit"] = kwargs
        return {"attempt_count": 0, "json_path": str(tmp_path / "audit.json"), "markdown_path": str(tmp_path / "audit.md")}

    monkeypatch.setattr(cli, "run_research_external_delivery_plan", fake_plan)
    monkeypatch.setattr(cli, "run_research_external_delivery_attempt_audit", fake_audit)

    cli.main_for_args(
        [
            "research-external-delivery-plan",
            "--publication-snapshot-id",
            "publication_snapshot:missing",
            "--record-attempt",
            "--output-dir",
            str(tmp_path / "plan"),
        ]
    )
    cli.main_for_args(
        [
            "research-external-delivery-attempt-audit",
            "--publication-snapshot-id",
            "publication_snapshot:missing",
            "--output-dir",
            str(tmp_path / "audit"),
        ]
    )

    assert captured["plan"]["record_attempt"] is True
    assert captured["plan"]["publication_snapshot_id"] == "publication_snapshot:missing"
    assert captured["audit"]["publication_snapshot_id"] == "publication_snapshot:missing"
