import json
from pathlib import Path

import pytest

from stock_research.dashboard.daily_review_lite import (
    _select_latest_daily_review_run,
    load_daily_review_lite,
    resolve_daily_review_lite_artifact,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"
SECTION_KEYS = {
    "data_readiness",
    "market_review",
    "strategy_summaries",
    "holding_review",
    "operator_plan",
    "next_day_checklist",
}


class _Cursor:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row=None):
        self.cursor_obj = _Cursor(row=row)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def _load_fixture_review() -> dict:
    return json.loads((FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8"))


def _write_package(package_root: Path, review: dict, *, include_json: bool = True) -> None:
    package_root.mkdir(parents=True, exist_ok=True)
    if include_json:
        (package_root / "daily_review.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (package_root / "daily_review.md").write_text("# Daily Review\n", encoding="utf-8")
    (package_root / "manifest.json").write_text("{}", encoding="utf-8")
    (package_root / "operator_plan_template.json").write_text("{}", encoding="utf-8")
    evidence_root = package_root / "evidence"
    evidence_root.mkdir(exist_ok=True)
    for name in [
        "market_state",
        "lhb_review",
        "mid_trend_review",
        "technical_bottleneck_review",
    ]:
        (evidence_root / f"{name}.json").write_text("{}", encoding="utf-8")


def test_select_latest_daily_review_run_queries_report_run(monkeypatch):
    row = {
        "run_id": "daily_review_v1:2026-06-20:abc",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "partial",
        "report_paths": {},
        "metadata": {},
        "updated_at": "2026-06-20T22:00:00Z",
    }
    conn = _Connection(row=row)
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite.connect",
        lambda service: _Context(conn),
    )

    result = _select_latest_daily_review_run("2026-06-20", service="research")

    sql, params = conn.cursor_obj.calls[0]
    assert result == row
    assert "FROM report.report_run" in sql
    assert "report_type = %(report_type)s" in sql
    assert "status IN ('success', 'partial', 'failed')" in sql
    assert "ORDER BY updated_at DESC" in sql
    assert params == {"trade_date": "2026-06-20", "report_type": "daily_review_v1"}


def test_load_daily_review_lite_returns_empty_when_no_run_or_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: None,
    )

    result = load_daily_review_lite("2026-06-20", reports_root=tmp_path)

    assert result["trade_date"] == "2026-06-20"
    assert result["state"] == "empty"
    assert result["selected_run"] is None
    assert result["summary"] is None
    assert result["artifacts"] == []
    assert result["sections"].keys() == SECTION_KEYS
    assert result["sections"]["data_readiness"]["status"] == "empty"
    assert result["sections"]["market_review"]["status"] == "empty"
    assert result["sections"]["holding_review"]["status"] == "empty"
    assert result["sections"]["operator_plan"]["status"] == "empty"
    assert result["sections"]["next_day_checklist"]["status"] == "empty"
    assert result["sections"]["strategy_summaries"]["lhb"]["status"] == "empty"
    assert result["sections"]["strategy_summaries"]["mid_trend"]["status"] == "empty"
    assert result["sections"]["strategy_summaries"]["technical_bottleneck"]["status"] == "empty"


def test_load_daily_review_lite_maps_partial_report_run_payload(monkeypatch, tmp_path: Path):
    review = _load_fixture_review()
    review["next_day_plan"]["must_review_items"][0]["reasons"] = [
        {
            "strategy_id": "lhb",
            "reason": {
                "summary": "bank rotation leader",
                "detail": "LHB signal still needs opening-strength confirmation.",
            },
        }
    ]
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review)
    row = {
        "run_id": "daily_review_v1:2026-06-20:abc",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "partial",
        "report_paths": {
            "package_root": str(package_root),
            "json_path": str(package_root / "daily_review.json"),
            "markdown_path": str(package_root / "daily_review.md"),
            "manifest_path": str(package_root / "manifest.json"),
            "operator_plan_template_path": str(package_root / "operator_plan_template.json"),
            "evidence_paths": {
                "market_state": str(package_root / "evidence" / "market_state.json"),
                "lhb_review": str(package_root / "evidence" / "lhb_review.json"),
                "mid_trend_review": str(package_root / "evidence" / "mid_trend_review.json"),
                "technical_bottleneck_review": str(
                    package_root / "evidence" / "technical_bottleneck_review.json"
                ),
            },
        },
        "metadata": {
            "missing_sources": [
                {
                    "source_key": "raw_lhb_payload",
                    "summary": "LHB payload missing for trade date.",
                    "affected_sections": ["lhb", "next_day_plan"],
                    "confidence_impact": "LHB conclusion confidence reduced",
                }
            ]
        },
        "updated_at": "2026-06-20T22:00:00Z",
    }
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: row,
    )

    result = load_daily_review_lite("2026-06-20", reports_root=tmp_path)

    assert result["state"] == "partial"
    assert result["selected_run"]["source"] == "report_run"
    assert result["selected_run"]["artifact_health"] == "healthy"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "healthy"
    assert result["summary"] == {
        "market_status": "cold",
        "overall_position_bias": "defensive",
        "lhb_conclusion": "trial",
        "mid_trend_conclusion": "hold core names",
        "technical_bottleneck_conclusion": "monitor upgrades only",
        "must_review_asset_ids": ["CN:SH:600000"],
        "warning_count": 1,
    }
    assert result["warnings"] == ["source_missing:lhb_feed"]
    assert result["sections"].keys() == SECTION_KEYS
    assert result["sections"]["data_readiness"]["status"] == "partial"
    assert result["sections"]["data_readiness"]["warnings"] == ["source_missing:lhb_feed"]
    assert result["sections"]["market_review"]["status"] == "success"
    assert result["sections"]["market_review"]["warnings"] == []
    assert result["sections"]["holding_review"]["status"] == "success"
    assert result["sections"]["holding_review"]["warnings"] == []
    assert result["sections"]["operator_plan"]["status"] == "success"
    assert result["sections"]["operator_plan"]["warnings"] == []
    assert (
        result["sections"]["strategy_summaries"]["lhb"]["status"] == "partial"
    )
    assert result["sections"]["strategy_summaries"]["mid_trend"]["status"] == "success"
    assert (
        result["sections"]["strategy_summaries"]["technical_bottleneck"]["status"] == "success"
    )
    assert result["sections"]["strategy_summaries"]["lhb"]["warnings"] == [
        "source_missing:lhb_feed"
    ]
    assert result["sections"]["strategy_summaries"]["lhb"]["top_items"][0]["asset_id"] == "CN:SH:600000"
    assert result["sections"]["next_day_checklist"]["status"] == "partial"
    assert result["sections"]["next_day_checklist"]["must_review_items"][0]["reasons"] == [
        {
            "strategy_id": "lhb",
            "summary": "bank rotation leader",
            "detail": "LHB signal still needs opening-strength confirmation.",
        }
    ]
    assert result["sections"]["next_day_checklist"]["must_review_items"][0]["actions"] == [
        "manual_review"
    ]
    assert (
        result["sections"]["next_day_checklist"]["must_review_items"][0]["review_priority"] == "P0"
    )
    assert result["missing_sources"][0] == {
        "source_key": "raw_lhb_payload",
        "summary": "LHB payload missing for trade date.",
        "affected_sections": ["lhb", "next_day_plan"],
        "confidence_impact": "LHB conclusion confidence reduced",
    }
    artifact = next(item for item in result["artifacts"] if item["key"] == "daily_review_json")
    assert artifact["kind"] == "json"
    assert artifact["available"] is True
    assert artifact["filename"] == "daily_review.json"
    assert artifact["url"] == "/api/daily-review-lite/artifacts/2026-06-20/daily_review_json?run_id=daily_review_v1%3A2026-06-20%3Aabc"
    assert "path" not in artifact


def test_load_daily_review_lite_marks_fallback_source(monkeypatch, tmp_path: Path):
    review = _load_fixture_review()
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review)
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: None,
    )

    result = load_daily_review_lite("2026-06-20", reports_root=tmp_path)

    assert result["state"] == "partial"
    assert result["selected_run"]["source"] == "fallback"
    assert result["selected_run"]["status"] == "partial"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "healthy"
    assert result["summary"]["must_review_asset_ids"] == ["CN:SH:600000"]
    assert result["sections"]["strategy_summaries"]["technical_bottleneck"]["top_items"][0][
        "asset_id"
    ] == "CN:SH:600000"


def test_load_daily_review_lite_returns_failed_when_core_artifact_missing(
    monkeypatch,
    tmp_path: Path,
):
    review = _load_fixture_review()
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review, include_json=False)
    row = {
        "run_id": "daily_review_v1:2026-06-20:missing",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "success",
        "report_paths": {
            "package_root": str(package_root),
            "json_path": str(package_root / "daily_review.json"),
            "markdown_path": str(package_root / "daily_review.md"),
        },
        "metadata": {},
        "updated_at": "2026-06-20T22:00:00Z",
    }
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: row,
    )

    result = load_daily_review_lite("2026-06-20", reports_root=tmp_path)

    assert result["state"] == "failed"
    assert result["summary"] is None
    assert result["selected_run"]["artifact_health"] == "missing"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "missing"
    assert result["sections"].keys() == SECTION_KEYS
    assert result["sections"]["data_readiness"]["status"] == "empty"
    assert result["sections"]["market_review"]["status"] == "empty"
    assert result["sections"]["holding_review"]["status"] == "empty"
    assert result["sections"]["operator_plan"]["status"] == "empty"
    assert result["sections"]["next_day_checklist"]["status"] == "empty"
    assert result["sections"]["strategy_summaries"]["lhb"]["status"] == "empty"


def test_load_daily_review_lite_returns_failed_when_core_artifact_json_is_invalid(
    monkeypatch,
    tmp_path: Path,
):
    package_root = tmp_path / "2026-06-20"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "daily_review.json").write_text("{not-json", encoding="utf-8")
    row = {
        "run_id": "daily_review_v1:2026-06-20:invalid",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "failed",
        "report_paths": {
            "package_root": str(package_root),
            "json_path": str(package_root / "daily_review.json"),
        },
        "metadata": {},
        "updated_at": "2026-06-20T22:00:00Z",
    }
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: row,
    )

    result = load_daily_review_lite("2026-06-20", reports_root=tmp_path)

    assert result["state"] == "failed"
    assert result["selected_run"]["status"] == "failed"
    assert result["selected_run"]["artifact_health"] == "invalid"
    assert result["selected_run"]["artifact_health_detail"]["daily_review_json"] == "healthy"
    assert result["summary"] is None
    assert result["sections"]["data_readiness"]["status"] == "empty"


def test_load_daily_review_lite_uses_fallback_when_run_id_resolves_to_wrong_trade_date(
    monkeypatch,
    tmp_path: Path,
):
    review = _load_fixture_review()
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review)
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_daily_review_run_by_id",
        lambda run_id, service=None: {
            "run_id": run_id,
            "trade_date": "2026-06-19",
            "report_type": "daily_review_v1",
            "status": "success",
            "report_paths": {},
            "metadata": {},
            "updated_at": "2026-06-19T22:00:00Z",
        },
    )

    result = load_daily_review_lite("2026-06-20", run_id="daily_review_v1:2026-06-19:abc", reports_root=tmp_path)

    assert result["state"] == "partial"
    assert result["selected_run"]["source"] == "fallback"
    assert result["selected_run"]["run_id"] == "fallback:2026-06-20"


def test_resolve_daily_review_lite_artifact_returns_controlled_metadata(monkeypatch, tmp_path: Path):
    review = _load_fixture_review()
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review)
    row = {
        "run_id": "daily_review_v1:2026-06-20:artifact",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "partial",
        "report_paths": {
            "package_root": str(package_root),
            "json_path": str(package_root / "daily_review.json"),
            "markdown_path": str(package_root / "daily_review.md"),
        },
        "metadata": {},
        "updated_at": "2026-06-20T22:00:00Z",
    }
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: row,
    )

    result = resolve_daily_review_lite_artifact("2026-06-20", "daily_review_json", reports_root=tmp_path)

    assert result == {
        "key": "daily_review_json",
        "label": "Daily Review JSON",
        "kind": "json",
        "content_type": "application/json",
        "required": True,
        "path": str(package_root / "daily_review.json"),
        "filename": "daily_review.json",
        "trade_date": "2026-06-20",
        "run_id": "daily_review_v1:2026-06-20:artifact",
        "source": "report_run",
    }


def test_resolve_daily_review_lite_artifact_returns_none_when_registered_file_missing(
    monkeypatch,
    tmp_path: Path,
):
    package_root = tmp_path / "2026-06-20"
    package_root.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": "daily_review_v1:2026-06-20:missing-artifact",
        "trade_date": "2026-06-20",
        "report_type": "daily_review_v1",
        "status": "partial",
        "report_paths": {
            "package_root": str(package_root),
            "json_path": str(package_root / "daily_review.json"),
        },
        "metadata": {},
        "updated_at": "2026-06-20T22:00:00Z",
    }
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: row,
    )

    result = resolve_daily_review_lite_artifact("2026-06-20", "daily_review_json", reports_root=tmp_path)

    assert result is None


def test_resolve_daily_review_lite_artifact_uses_explicit_run_id(monkeypatch, tmp_path: Path):
    review = _load_fixture_review()
    package_root = tmp_path / "2026-06-20"
    _write_package(package_root, review)
    calls = []

    def _fake_select(run_id, service=None):
        calls.append(run_id)
        return {
            "run_id": run_id,
            "trade_date": "2026-06-20",
            "report_type": "daily_review_v1",
            "status": "failed",
            "report_paths": {
                "package_root": str(package_root),
                "json_path": str(package_root / "daily_review.json"),
            },
            "metadata": {},
            "updated_at": "2026-06-20T22:00:00Z",
        }

    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_daily_review_run_by_id",
        _fake_select,
    )

    result = resolve_daily_review_lite_artifact(
        "2026-06-20",
        "daily_review_json",
        run_id="daily_review_v1:2026-06-20:explicit",
        reports_root=tmp_path,
    )

    assert calls == ["daily_review_v1:2026-06-20:explicit"]
    assert result["run_id"] == "daily_review_v1:2026-06-20:explicit"
    assert result["source"] == "report_run"


def test_resolve_daily_review_lite_artifact_rejects_unknown_key(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "stock_research.dashboard.daily_review_lite._select_latest_daily_review_run",
        lambda trade_date, service=None: None,
    )

    with pytest.raises(ValueError, match="unknown artifact key"):
        resolve_daily_review_lite_artifact("2026-06-20", "not_real", reports_root=tmp_path)
