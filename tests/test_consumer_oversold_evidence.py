from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.evidence import (
    EVIDENCE_COLUMNS,
    OUTPUT_COLUMNS,
    validate_repair_evidence,
)


TRADE_DATE = "2026-07-29"


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "asset_id": "a1",
        "stock_code": "000759",
        "evidence_as_of_date": "2026-07-28",
        "repair_bucket": "expected_repair",
        "repair_thesis": "同店销售回升可带动利润率修复",
        "leading_indicator": "月度同店销售增速",
        "unrepaired_metrics": "净利率仍低于历史中枢",
        "expected_validation_date": "2026-10-31",
        "main_risks": "消费需求恢复慢于预期",
        "invalidation_conditions": "连续两个季度同店销售恶化",
        "source_title": "公司月度经营公告",
        "source_url": "https://example.com/reports/1",
        "source_publish_date": "2026-07-28",
        "forecast_revision_state": "stable",
        "audit_review_status": "clear",
        "audit_review_source_title": "2025年度审计报告",
        "audit_review_source_url": "https://example.com/audit/1",
        "audit_review_source_publish_date": "2026-04-20",
        "pledge_debt_review_status": "clear",
        "pledge_debt_review_source_title": "股份质押及债务事项核查公告",
        "pledge_debt_review_source_url": "https://example.com/pledge/1",
        "pledge_debt_review_source_publish_date": "2026-05-20",
        "permanent_impairment_status": "clear",
        "permanent_impairment_source_title": "资产减值事项核查公告",
        "permanent_impairment_source_url": "https://example.com/impairment/1",
        "permanent_impairment_source_publish_date": "2026-04-21",
        "catalyst_verifiability_score": 80,
        "expected_improvement_score": 70.5,
        "operator_notes": "",
    }
    row.update(changes)
    return row


def _frame(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(rows or [_row()], columns=EVIDENCE_COLUMNS)


def _validate(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    return validate_repair_evidence(_frame() if frame is None else frame, trade_date=TRADE_DATE)


def test_valid_evidence_is_normalized_complete_and_sorted_by_asset_id():
    frame = _frame(
        _row(asset_id=" b ", stock_code=759.0, repair_bucket=" early_validation "),
        _row(asset_id="a", stock_code="601888"),
    )

    result = _validate(frame)

    assert list(result.columns) == OUTPUT_COLUMNS
    assert result["asset_id"].tolist() == ["a", "b"]
    assert result["stock_code"].tolist() == ["601888", "000759"]
    assert result.loc[1, "repair_bucket"] == "early_validation"
    assert result["evidence_complete"].tolist() == [True, True]
    assert result["evidence_errors"].tolist() == ["", ""]


@pytest.mark.parametrize("trade_date", ["", "2026-02-30", "2026-7-29", "not-a-date"])
def test_trade_date_must_be_a_real_strict_iso_date(trade_date):
    with pytest.raises(ValueError, match="trade_date"):
        validate_repair_evidence(_frame(), trade_date=trade_date)


def test_missing_columns_raise_with_column_names_and_empty_frame_has_stable_structure():
    with pytest.raises(ValueError, match="source_url.*operator_notes"):
        validate_repair_evidence(
            pd.DataFrame(columns=EVIDENCE_COLUMNS).drop(columns=["source_url", "operator_notes"]),
            trade_date=TRADE_DATE,
        )

    result = validate_repair_evidence(pd.DataFrame(columns=EVIDENCE_COLUMNS), trade_date=TRADE_DATE)

    assert result.empty
    assert list(result.columns) == OUTPUT_COLUMNS


@pytest.mark.parametrize("asset_id", ["", "   ", None, np.nan])
def test_asset_id_must_be_non_empty(asset_id):
    with pytest.raises(ValueError, match="asset_id"):
        _validate(_frame(_row(asset_id=asset_id)))


def test_duplicate_asset_id_is_rejected_after_normalization():
    with pytest.raises(ValueError, match="duplicate.*a1"):
        _validate(_frame(_row(asset_id=" a1 "), _row(asset_id="a1")))


@pytest.mark.parametrize("field", ["evidence_as_of_date", "source_publish_date"])
def test_evidence_dates_cannot_be_in_the_future(field):
    with pytest.raises(ValueError, match=rf"a1.*{field}|{field}.*a1"):
        _validate(_frame(_row(**{field: "2026-07-30"})))


@pytest.mark.parametrize("field", ["evidence_as_of_date", "source_publish_date", "expected_validation_date"])
@pytest.mark.parametrize("value", ["2026-02-30", "2026-7-1", "not-a-date"])
def test_non_empty_dates_must_be_real_strict_iso(field, value):
    with pytest.raises(ValueError, match=field):
        _validate(_frame(_row(**{field: value})))


def test_expected_validation_date_cannot_precede_evidence_date():
    with pytest.raises(ValueError, match="expected_validation_date.*evidence_as_of_date"):
        _validate(_frame(_row(expected_validation_date="2026-07-27")))


def test_source_publish_date_cannot_follow_evidence_as_of_date():
    with pytest.raises(
        ValueError,
        match=r"a1.*source_publish_date.*evidence_as_of_date|source_publish_date.*evidence_as_of_date.*a1",
    ):
        _validate(
            _frame(
                _row(
                    evidence_as_of_date="2026-07-27",
                    source_publish_date="2026-07-28",
                )
            )
        )


def test_source_publish_date_is_retained_when_evidence_as_of_date_is_missing():
    result = _validate(
        _frame(_row(evidence_as_of_date="", source_publish_date="2026-07-28"))
    )

    assert result.loc[0, "source_publish_date"] == "2026-07-28"
    assert result.loc[0, "evidence_errors"] == "missing_evidence_as_of_date"
    assert not result.loc[0, "evidence_complete"]


@pytest.mark.parametrize("bucket", ["", " ", None, "late_validation"])
def test_repair_bucket_must_be_non_empty_and_allowed(bucket):
    with pytest.raises(ValueError, match="repair_bucket"):
        _validate(_frame(_row(repair_bucket=bucket)))


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("repair_thesis", "missing_repair_thesis"),
        ("leading_indicator", "missing_leading_indicator"),
        ("unrepaired_metrics", "missing_unrepaired_metrics"),
        ("expected_validation_date", "missing_expected_validation_date"),
        ("main_risks", "missing_main_risks"),
        ("invalidation_conditions", "missing_invalidation_conditions"),
        ("source_title", "missing_source_title"),
        ("source_url", "missing_source_url"),
        ("source_publish_date", "missing_source_publish_date"),
        ("evidence_as_of_date", "missing_evidence_as_of_date"),
    ],
)
def test_missing_evidence_text_marks_incomplete_instead_of_raising(field, error):
    result = _validate(_frame(_row(**{field: "  "})))

    assert not result.loc[0, "evidence_complete"]
    assert result.loc[0, "evidence_errors"] == error


@pytest.mark.parametrize(
    "url",
    [
        "example.com/a",
        "ftp://example.com/a",
        "https:///missing-host",
        "http://",
        "https://:80/path",
        "https://exa mple.com/a",
        "https://./a",
        "https://-bad-.com/a",
        "https://localhost/a",
        "https://user@example.com/a",
        "https://user:password@example.com/a",
        "https://example.com:not-a-port/a",
        "https://example.com:70000/a",
        "https://127.0.0.1/a",
        "https://10.0.0.1/a",
        "https://169.254.169.254/latest/meta-data",
        "https://224.0.0.1/a",
        "https://240.0.0.1/a",
        "https://0.0.0.0/a",
        "https://[::1]/a",
        "https://[fc00::1]/a",
        "https://[fe80::1]/a",
        "https://[ff02::1]/a",
    ],
)
def test_non_empty_source_url_requires_http_or_https_and_a_host(url):
    with pytest.raises(ValueError, match="source_url.*a1|a1.*source_url"):
        _validate(_frame(_row(source_url=url)))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a",
        "http://reports.example.com/a",
        "https://xn--fsqu00a.xn--0zwm56d/a",
        "https://例子.测试/a",
        "https://8.8.8.8/a",
        "https://[2606:4700:4700::1111]/a",
    ],
)
def test_source_url_accepts_valid_dns_idna_and_ip_hosts(url):
    result = _validate(_frame(_row(source_url=url)))

    assert result.loc[0, "source_url"] == url


def test_missing_risk_statuses_normalize_to_unknown_and_set_unknown_flag():
    result = _validate(
        _frame(_row(audit_review_status=" ", pledge_debt_review_status=None))
    )

    assert result.loc[0, "audit_review_status"] == "unknown"
    assert result.loc[0, "pledge_debt_review_status"] == "unknown"
    assert not result.loc[0, "hard_risk_manual_trigger"]
    assert result.loc[0, "hard_risk_review_unknown"]
    assert result.loc[0, "evidence_complete"]


def test_any_triggered_risk_sets_manual_trigger_flag():
    result = _validate(_frame(_row(permanent_impairment_status=" triggered ")))

    assert result.loc[0, "permanent_impairment_status"] == "triggered"
    assert result.loc[0, "hard_risk_manual_trigger"]
    assert not result.loc[0, "hard_risk_review_unknown"]


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("audit_review_source_title", "missing_audit_review_source_title"),
        ("audit_review_source_url", "missing_audit_review_source_url"),
        (
            "audit_review_source_publish_date",
            "missing_audit_review_source_publish_date",
        ),
        ("pledge_debt_review_source_title", "missing_pledge_debt_review_source_title"),
        ("pledge_debt_review_source_url", "missing_pledge_debt_review_source_url"),
        (
            "pledge_debt_review_source_publish_date",
            "missing_pledge_debt_review_source_publish_date",
        ),
        (
            "permanent_impairment_source_title",
            "missing_permanent_impairment_source_title",
        ),
        (
            "permanent_impairment_source_url",
            "missing_permanent_impairment_source_url",
        ),
        (
            "permanent_impairment_source_publish_date",
            "missing_permanent_impairment_source_publish_date",
        ),
    ],
)
def test_each_hard_risk_status_requires_its_own_source_triplet(field, error):
    result = _validate(_frame(_row(**{field: ""})))

    assert not result.loc[0, "evidence_complete"]
    assert error in result.loc[0, "evidence_errors"]


@pytest.mark.parametrize(
    "field",
    [
        "audit_review_source_publish_date",
        "pledge_debt_review_source_publish_date",
        "permanent_impairment_source_publish_date",
    ],
)
def test_hard_risk_source_dates_cannot_be_future(field):
    with pytest.raises(ValueError, match=field):
        _validate(_frame(_row(**{field: "2026-07-30"})))


@pytest.mark.parametrize(
    "field",
    [
        "audit_review_source_url",
        "pledge_debt_review_source_url",
        "permanent_impairment_source_url",
    ],
)
def test_hard_risk_source_urls_are_validated(field):
    with pytest.raises(ValueError, match=field):
        _validate(_frame(_row(**{field: "seller-note-without-url"})))


def test_hard_risk_reviews_cannot_reuse_one_source_for_all_three_checks():
    with pytest.raises(ValueError, match="hard risk source URLs must be distinct"):
        _validate(
            _frame(
                _row(
                    audit_review_source_url="https://example.com/seller/1",
                    pledge_debt_review_source_url="https://example.com/seller/1",
                    permanent_impairment_source_url="https://example.com/seller/1",
                )
            )
        )


@pytest.mark.parametrize("field", ["audit_review_status", "pledge_debt_review_status", "permanent_impairment_status"])
def test_invalid_risk_status_raises(field):
    with pytest.raises(ValueError, match=field):
        _validate(_frame(_row(**{field: "pending"})))


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("catalyst_verifiability_score", "missing_catalyst_verifiability_score"),
        ("expected_improvement_score", "missing_expected_improvement_score"),
    ],
)
def test_missing_score_marks_evidence_incomplete(field, error):
    result = _validate(_frame(_row(**{field: None})))

    assert not result.loc[0, "evidence_complete"]
    assert result.loc[0, "evidence_errors"] == error


@pytest.mark.parametrize("shape", ["mixed", "all_missing", "empty"])
def test_score_columns_have_stable_nullable_float_dtype(shape):
    if shape == "mixed":
        frame = _frame(
            _row(asset_id="a1", catalyst_verifiability_score=None),
            _row(asset_id="a2", expected_improvement_score=None),
        )
    elif shape == "all_missing":
        frame = _frame(
            _row(
                asset_id="a1",
                catalyst_verifiability_score=None,
                expected_improvement_score=None,
            ),
            _row(
                asset_id="a2",
                catalyst_verifiability_score=np.nan,
                expected_improvement_score=pd.NA,
            ),
        )
    else:
        frame = pd.DataFrame(columns=EVIDENCE_COLUMNS)

    result = _validate(frame)

    assert str(result["catalyst_verifiability_score"].dtype) == "Float64"
    assert str(result["expected_improvement_score"].dtype) == "Float64"
    if not result.empty:
        missing = result[
            ["catalyst_verifiability_score", "expected_improvement_score"]
        ].isna()
        assert missing.any(axis=None)


@pytest.mark.parametrize("value", [-1, 101, "80", True, np.bool_(False), np.inf, -np.inf])
@pytest.mark.parametrize("field", ["catalyst_verifiability_score", "expected_improvement_score"])
def test_invalid_scores_raise(field, value):
    with pytest.raises(ValueError, match=field):
        _validate(_frame(_row(**{field: value})))


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        (None, "unknown"),
        (" ", "unknown"),
        (" improving ", "improving"),
        ("not_available", "not_available"),
        ("stable", "stable"),
        ("deteriorating", "deteriorating"),
        ("broadly_priced", "broadly_priced"),
    ],
)
def test_forecast_revision_state_is_normalized(value, normalized):
    result = _validate(_frame(_row(forecast_revision_state=value)))

    assert result.loc[0, "forecast_revision_state"] == normalized


def test_invalid_forecast_revision_state_raises():
    with pytest.raises(ValueError, match="forecast_revision_state"):
        _validate(_frame(_row(forecast_revision_state="upgraded")))


@pytest.mark.parametrize(
    "stock_code",
    [None, np.nan, "", "abc", "1234567", -1, -1.0, 1.5, True, np.bool_(False), np.inf],
)
def test_invalid_stock_codes_raise(stock_code):
    with pytest.raises(ValueError, match="stock_code"):
        _validate(_frame(_row(stock_code=stock_code)))


def test_csv_numeric_stock_code_is_zero_padded(tmp_path):
    path = tmp_path / "evidence.csv"
    _frame(_row(stock_code="000759")).to_csv(path, index=False)
    loaded = pd.read_csv(path)

    result = _validate(loaded)

    assert result.loc[0, "stock_code"] == "000759"


def test_multiple_missing_fields_have_deduplicated_stably_sorted_errors():
    result = _validate(
        _frame(
            _row(
                repair_thesis="",
                leading_indicator=None,
                source_title=" ",
                expected_improvement_score=np.nan,
            )
        )
    )

    assert result.loc[0, "evidence_errors"] == "|".join(
        sorted(
            {
                "missing_repair_thesis",
                "missing_leading_indicator",
                "missing_source_title",
                "missing_expected_improvement_score",
            }
        )
    )


def test_template_contains_only_the_exact_header():
    template = Path(__file__).parents[1] / "config" / "consumer_oversold_repair_evidence_template_v1.csv"
    lines = template.read_text(encoding="utf-8").splitlines()

    assert lines == [",".join(EVIDENCE_COLUMNS)]
