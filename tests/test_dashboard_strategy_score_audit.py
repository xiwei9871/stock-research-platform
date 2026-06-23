from stock_research.dashboard import strategy_score_audit as dashboard_strategy_score_audit


def test_load_strategy_score_audit_payload_returns_ok_for_clean_summary(monkeypatch):
    monkeypatch.setattr(
        dashboard_strategy_score_audit,
        "load_strategy_score_audit_summary",
        lambda **kwargs: {
            "trade_date": "2026-06-22",
            "status": "success",
            "summary_path": "/tmp/strategy_score_audit_summary.json",
            "detail_path": "/tmp/strategy_score_audit_detail.csv",
            "total_rows": 3,
            "selected_rows": 3,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategies": [{"strategy_id": "mid_trend", "row_count": 3, "selected_count": 3, "anomaly_count": 0}],
        },
    )

    payload = dashboard_strategy_score_audit.load_strategy_score_audit_payload(trade_date="2026-06-22")

    assert payload["overall_status"] == "ok"
    assert payload["warnings"] == []
    assert payload["summary_path"] == "/tmp/strategy_score_audit_summary.json"
    assert payload["detail_path"] == "/tmp/strategy_score_audit_detail.csv"


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
        "warnings": ["strategy score audit artifact not found for trade_date 2026-06-22"],
    }
