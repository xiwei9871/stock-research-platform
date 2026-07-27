import json

from stock_research.strategy_publication_receipt import (
    build_publication_receipt,
    validate_publication_receipt,
)


def _summary(trade_date="2026-07-24"):
    return {
        "trade_date": trade_date,
        "run_id": f"strategy-eod-{trade_date}-local",
        "status": "success",
        "publishable": True,
        "review_rows": 15,
        "strategy_status": {
            "lhb_shortline": "success",
            "mid_trend": "success",
            "midtrend_artifacts": "success",
            "tech_bottleneck": "success",
        },
        "score_audit": {
            "status": "success",
            "strategy_counts": {
                "lhb_shortline": 5,
                "mid_trend": 5,
                "tech_bottleneck": 5,
            },
        },
    }


def test_receipt_binds_complete_publication_contract(tmp_path):
    path = tmp_path / "strategy_eod_publish_summary.json"
    path.write_text(json.dumps(_summary()), encoding="utf-8")

    receipt = build_publication_receipt(
        summary_path=path,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
    )

    assert receipt["publishable"] is True
    assert receipt["review_rows"] == 15
    assert receipt["strategy_counts"] == {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    assert receipt["score_audit_status"] == "success"
    assert validate_publication_receipt(
        receipt,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
        expected_summary_path=path,
        release_root=tmp_path,
    )["status"] == "success"


def test_nonempty_legacy_receipt_fails_closed_as_missing_contract(tmp_path):
    path = tmp_path / "strategy_eod_publish_summary.json"
    path.write_text(json.dumps(_summary()), encoding="utf-8")
    receipt = build_publication_receipt(
        summary_path=path,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
    )
    for key in ("publishable", "review_rows", "strategy_counts", "score_audit_status"):
        receipt.pop(key)

    result = validate_publication_receipt(
        receipt,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
        expected_summary_path=path,
        release_root=tmp_path,
    )

    assert result == {
        "status": "failed",
        "error_code": "publication_receipt_missing_contract",
    }


def test_receipt_rejects_summary_with_broken_complete_contract(tmp_path):
    path = tmp_path / "strategy_eod_publish_summary.json"
    payload = _summary()
    payload["score_audit"]["strategy_counts"]["tech_bottleneck"] = 4
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = build_publication_receipt(
        summary_path=path,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
    )

    result = validate_publication_receipt(
        receipt,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
        expected_summary_path=path,
        release_root=tmp_path,
    )

    assert result["error_code"] == "publication_receipt_summary_mismatch"
