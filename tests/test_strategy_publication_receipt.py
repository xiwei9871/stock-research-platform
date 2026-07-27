import json

import pytest

from stock_research.strategy_publication_receipt import (
    PublicationReceiptSummaryInvalid,
    build_publication_receipt,
    file_fingerprint,
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


@pytest.mark.parametrize(
    ("field_path", "malformed"),
    [
        (("strategy_status",), "bad"),
        (("strategy_status",), ["bad"]),
        (("strategy_status",), None),
        (("score_audit",), "bad"),
        (("score_audit",), ["bad"]),
        (("score_audit",), None),
        (("score_audit", "strategy_counts"), "bad"),
        (("score_audit", "strategy_counts"), ["bad"]),
        (("score_audit", "strategy_counts"), None),
    ],
)
def test_receipt_build_rejects_malformed_mappings_safely(
    tmp_path, field_path, malformed
):
    path = tmp_path / "strategy_eod_publish_summary.json"
    payload = _summary()
    if len(field_path) == 1:
        payload[field_path[0]] = malformed
    else:
        payload[field_path[0]][field_path[1]] = malformed
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PublicationReceiptSummaryInvalid) as exc_info:
        build_publication_receipt(
            summary_path=path,
            expected_trade_date="2026-07-24",
            repair_run_id="repair-1",
        )

    assert exc_info.value.error_code == "publication_receipt_summary_invalid"


@pytest.mark.parametrize("malformed", ["bad", ["bad"], None])
def test_receipt_build_never_leaks_value_error_for_non_object_summary(
    tmp_path, malformed
):
    path = tmp_path / "strategy_eod_publish_summary.json"
    path.write_text(json.dumps(malformed), encoding="utf-8")

    with pytest.raises(PublicationReceiptSummaryInvalid) as exc_info:
        build_publication_receipt(
            summary_path=path,
            expected_trade_date="2026-07-24",
            repair_run_id="repair-1",
        )

    assert exc_info.value.error_code == "publication_receipt_summary_invalid"


@pytest.mark.parametrize(
    ("field_path", "malformed"),
    [
        (("strategy_status",), "bad"),
        (("score_audit",), ["bad"]),
        (("score_audit", "strategy_counts"), None),
    ],
)
def test_receipt_validation_rejects_malformed_summary_mappings_safely(
    tmp_path, field_path, malformed
):
    path = tmp_path / "strategy_eod_publish_summary.json"
    path.write_text(json.dumps(_summary()), encoding="utf-8")
    receipt = build_publication_receipt(
        summary_path=path,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
    )
    payload = _summary()
    if len(field_path) == 1:
        payload[field_path[0]] = malformed
    else:
        payload[field_path[0]][field_path[1]] = malformed
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt["fingerprint"] = file_fingerprint(path)

    result = validate_publication_receipt(
        receipt,
        expected_trade_date="2026-07-24",
        repair_run_id="repair-1",
        expected_summary_path=path,
        release_root=tmp_path,
    )

    assert result == {
        "status": "failed",
        "error_code": "publication_receipt_summary_invalid",
    }
