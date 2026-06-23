import json

import pandas as pd

from stock_research.dashboard import strategy_score_audit as dashboard_strategy_score_audit


def test_load_strategy_score_audit_payload_returns_ok_for_clean_summary(monkeypatch):
    monkeypatch.setattr(
        dashboard_strategy_score_audit,
        "load_strategy_score_audit_summary",
        lambda **kwargs: {
            "trade_date": "2026-06-22",
            "status": "success",
            "generated_at": "2026-06-22T10:30:00Z",
            "summary_path": "/tmp/strategy_score_audit_summary.json",
            "detail_path": "/tmp/strategy_score_audit_detail.csv",
            "total_rows": 3,
            "selected_rows": 3,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategies": [{"strategy_id": "mid_trend", "row_count": 3, "selected_count": 3, "anomaly_count": 0}],
            "sample_rows": [{"asset_id": "CN:SZ:002080", "anomaly_flags": []}],
        },
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(trade_date="2026-06-22")

    assert payload["overall_status"] == "ok"
    assert payload["warnings"] == []
    assert payload["generated_at"] == "2026-06-22T10:30:00Z"
    assert payload["summary_path"] == "/tmp/strategy_score_audit_summary.json"
    assert payload["detail_path"] == "/tmp/strategy_score_audit_detail.csv"
    assert payload["sample_rows"] == [{"asset_id": "CN:SZ:002080", "anomaly_flags": []}]


def test_load_strategy_score_audit_payload_returns_warning_for_anomalies(monkeypatch):
    monkeypatch.setattr(
        dashboard_strategy_score_audit,
        "load_strategy_score_audit_summary",
        lambda **kwargs: {
            "trade_date": "2026-06-22",
            "status": "success",
            "total_rows": 3,
            "selected_rows": 3,
            "anomaly_row_count": 1,
            "anomaly_counts_by_type": {"mapped_score_without_raw_score": 1},
            "strategies": [],
        },
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(trade_date="2026-06-22")

    assert payload["overall_status"] == "warning"
    assert payload["warnings"] == ["1 audited rows have anomalies"]


def test_load_strategy_score_audit_payload_returns_warning_for_failed_summary(monkeypatch):
    monkeypatch.setattr(
        dashboard_strategy_score_audit,
        "load_strategy_score_audit_summary",
        lambda **kwargs: {
            "trade_date": "2026-06-22",
            "status": "failed",
            "error": "audit summary write failed",
        },
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(trade_date="2026-06-22")

    assert payload["overall_status"] == "warning"
    assert payload["warnings"] == ["audit summary write failed"]


def test_load_strategy_score_audit_payload_returns_missing_when_artifact_absent(monkeypatch):
    def fake_load_summary(**kwargs):
        raise FileNotFoundError("strategy score audit summary not found")

    monkeypatch.setattr(
        dashboard_strategy_score_audit,
        "load_strategy_score_audit_summary",
        fake_load_summary,
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(trade_date="2026-06-22")

    assert payload == {
        "trade_date": "2026-06-22",
        "status": "missing",
        "overall_status": "missing",
        "summary_path": "",
        "detail_path": "",
        "total_rows": 0,
        "selected_rows": 0,
        "anomaly_row_count": 0,
        "anomaly_counts_by_type": {},
        "strategies": [],
        "sample_rows": [],
        "warnings": ["strategy score audit artifact not found for trade_date 2026-06-22"],
    }


def test_load_strategy_score_audit_payload_preserves_persisted_fields_and_derives_sample_rows(tmp_path):
    output_dir = tmp_path / "research" / "strategy_daily_eod" / "2026-06-22"
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_path = output_dir / "strategy_score_audit_detail.csv"
    summary_path = output_dir / "strategy_score_audit_summary.json"

    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-22",
                "strategy_id": "mid_trend",
                "asset_id": "CN:SZ:002080",
                "stock_name": "Sample A",
                "published_score": 91.2,
                "anomaly_flags": "[]",
            },
            {
                "trade_date": "2026-06-22",
                "strategy_id": "lhb_shortline",
                "asset_id": "CN:SH:600519",
                "stock_name": "Sample B",
                "published_score": 88.5,
                "anomaly_flags": "[\"mapped_score_without_raw_score\"]",
            },
        ]
    ).to_csv(detail_path, index=False)
    summary_path.write_text(
        json.dumps(
            {
                "trade_date": "2026-06-22",
                "status": "success",
                "generated_at": "2026-06-22T12:00:00Z",
                "summary_path": str(summary_path),
                "detail_path": str(detail_path),
                "total_rows": 2,
                "selected_rows": 2,
                "anomaly_row_count": 1,
                "anomaly_counts_by_type": {"mapped_score_without_raw_score": 1},
                "strategies": [{"strategy_id": "mid_trend", "row_count": 1, "selected_count": 1, "anomaly_count": 0}],
                "source_note": "persisted-field",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(
        trade_date="2026-06-22",
        output_root=tmp_path,
    )

    assert payload["generated_at"] == "2026-06-22T12:00:00Z"
    assert payload["source_note"] == "persisted-field"
    assert payload["overall_status"] == "warning"
    assert len(payload["sample_rows"]) == 2
    assert payload["sample_rows"][0]["asset_id"] == "CN:SZ:002080"
    assert payload["sample_rows"][1]["asset_id"] == "CN:SH:600519"
