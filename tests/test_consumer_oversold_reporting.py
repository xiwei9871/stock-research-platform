from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import OUTPUT_FILENAMES
from stock_research.consumer_oversold.reporting import (
    REPORT_COLUMNS,
    write_consumer_oversold_artifacts,
)


FUNNEL = {
    "raw_assets": 100,
    "consumer_universe": 50,
    "market_eligible": 40,
    "oversold_eligible": 20,
    "hard_risk_clear": 15,
    "evidence_complete": 12,
    "valuation_eligible": 10,
    "selected_expected": 1,
    "selected_early": 1,
}


def _selected(asset_id: str, bucket: str, name: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "z_extra": "tail",
                "asset_id": asset_id,
                "stock_code": asset_id,
                "stock_name": name,
                "consumer_subindustry": "白色家电|厨电\n细分",
                "repair_bucket": bucket,
                "bucket_rank": 1,
                "return_6m": -0.31,
                "max_drawdown_12m": -0.42,
                "relative_return_6m": -0.19,
                "valuation_method": "PE",
                "valuation_percentile": 0.12,
                "pessimistic_upside": -0.05,
                "base_upside": 0.35,
                "optimistic_upside": 0.72,
                "repair_thesis": "需求企稳",
                "unrepaired_metrics": "毛利率",
                "leading_indicator": "月度销量",
                "expected_validation_date": "2026-08-30",
                "source_title": "公告|原文\n链接",
                "source_url": "https://example.com/a_(b)",
                "source_publish_date": "2026-07-20",
                "main_risks": "价格战",
                "invalidation_conditions": "销量继续下滑",
                "operating_gap_score": 80.0,
                "repair_potential_score": 75.0,
                "valuation_repair_score": 88.0,
                "oversold_score": 82.0,
                "balance_sheet_score": 70.0,
                "catalyst_verifiability_score": 68.0,
                "priced_in_penalty": 4.0,
                "composite_score": 78.3,
                "evidence_complete": True,
                "hard_risk_triggered": False,
                "hard_risk_review_unknown": False,
                "a_extra": "first-extra",
            }
        ]
    )


def _payload() -> dict[str, object]:
    expected = _selected("000001.SZ", "expected_repair", "甲公司")
    early = _selected("000002.SZ", "early_validation", "乙公司")
    scores = pd.concat([expected, early], ignore_index=True)
    exclusions = pd.DataFrame(
        [{"asset_id": "000003.SZ", "exclusion_reasons": "证据不完整|风险未核验"}]
    )
    return {
        "trade_date": "2026-07-29",
        "expected": expected,
        "early": early,
        "scores": scores,
        "exclusions": exclusions,
        "coverage": {
            "funnel": FUNNEL.copy(),
            "data_date_maxima": {"prices": "2026-07-29"},
            "missing_field_counts": {"pe": 2},
            "warnings": ["部分财务数据滞后"],
            "valuation_history_coverage": {"covered": 8, "total": 10},
            "finance_history_coverage": {"covered": 9, "total": 10},
        },
    }


def _artifact_contents(output_dir: Path) -> dict[str, bytes]:
    return {
        key: (output_dir / filename).read_bytes()
        for key, filename in OUTPUT_FILENAMES.items()
    }


def test_writes_six_stable_artifacts_and_chinese_report(tmp_path):
    result = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path / "nested")

    assert set(result) == {"paths", "expected", "early", "scores", "exclusions", "coverage", "report"}
    assert set(result["paths"]) == set(OUTPUT_FILENAMES)
    for key, filename in OUTPUT_FILENAMES.items():
        path = Path(result["paths"][key])
        assert path.is_absolute()
        assert path.name == filename
        assert path.exists()

    expected_csv = pd.read_csv(result["paths"]["expected"])
    expected_order = [column for column in REPORT_COLUMNS if column in _payload()["expected"].columns]
    expected_extras = sorted(
        column for column in _payload()["expected"].columns if column not in expected_order
    )
    assert expected_csv.columns.tolist() == [*expected_order, *expected_extras]
    assert expected_csv.loc[0, "stock_name"] == "甲公司"

    coverage = json.loads(Path(result["paths"]["coverage"]).read_text(encoding="utf-8"))
    assert coverage["trade_date"] == "2026-07-29"
    assert coverage["funnel"] == FUNNEL
    assert coverage["warnings"] == ["部分财务数据滞后"]

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    for text in [
        "2026-07-29",
        "研究候选，不是交易指令",
        "数据覆盖",
        "纯预期修复",
        "初步验证但尚未充分定价",
        "剔除原因摘要",
        "警告",
        "失效条件",
        "甲公司",
        "https://example.com/a_(b)",
    ]:
        assert text in report
    assert "白色家电\\|厨电 细分" in report
    assert "公告\\|原文 链接" in report


def test_empty_frames_still_write_asset_id_headers_and_missing_markdown_values(tmp_path):
    payload = _payload()
    for key in ("expected", "early", "scores", "exclusions"):
        payload[key] = pd.DataFrame()
    payload["coverage"]["funnel"].update(selected_expected=0, selected_early=0)

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for key in ("expected", "early", "scores", "exclusions"):
        assert Path(result["paths"][key]).read_text(encoding="utf-8").splitlines()[0] == "asset_id"
    assert "暂无候选" in Path(result["paths"]["report"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        (lambda p: p.pop("coverage"), ValueError, "missing required keys.*coverage"),
        (lambda p: p.update(expected=[]), TypeError, "expected must be a pandas DataFrame"),
        (lambda p: p.update(trade_date="20260729"), ValueError, "trade_date"),
        (lambda p: p["coverage"].pop("warnings"), ValueError, "coverage missing required keys.*warnings"),
    ],
)
def test_rejects_missing_or_wrongly_typed_payload(mutation, error, message, tmp_path):
    payload = _payload()
    mutation(payload)
    with pytest.raises(error, match=message):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_rejects_bucket_overlap_limit_duplicate_empty_and_risk_contracts(tmp_path):
    payload = _payload()
    payload["early"] = payload["expected"].copy(deep=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["expected"] = pd.concat([payload["expected"]] * 21, ignore_index=True)
    payload["expected"]["asset_id"] = [f"A{i}" for i in range(21)]
    with pytest.raises(ValueError, match="at most 20"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for field, invalid in [
        ("evidence_complete", False),
        ("hard_risk_triggered", True),
        ("hard_risk_review_unknown", True),
    ]:
        payload = _payload()
        payload["expected"].loc[0, field] = invalid
        with pytest.raises(ValueError, match=field):
            write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for values in (["", "X"], ["X", "X"]):
        payload = _payload()
        payload["expected"] = pd.concat([payload["expected"]] * 2, ignore_index=True)
        payload["expected"]["asset_id"] = values
        with pytest.raises(ValueError, match="asset_id"):
            write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_rejects_non_json_safe_coverage_values(bad, tmp_path):
    payload = _payload()
    payload["coverage"]["missing_field_counts"]["pe"] = bad
    with pytest.raises(ValueError, match="finite|JSON"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_normalizes_numpy_json_scalars(tmp_path):
    payload = _payload()
    payload["coverage"]["extra"] = {"integer": np.int64(3), "boolean": np.bool_(True)}

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    coverage = json.loads(Path(result["paths"]["coverage"]).read_text(encoding="utf-8"))
    assert coverage["extra"] == {"integer": 3, "boolean": True}


def test_does_not_modify_input_frames(tmp_path):
    payload = _payload()
    originals = {key: payload[key].copy(deep=True) for key in ("expected", "early", "scores", "exclusions")}

    write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for key, original in originals.items():
        pd.testing.assert_frame_equal(payload[key], original)


def test_existing_artifacts_are_replaced_and_unrelated_file_is_preserved(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    for filename in OUTPUT_FILENAMES.values():
        (tmp_path / filename).write_text("old", encoding="utf-8")
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("untouched", encoding="utf-8")

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert unrelated.read_text(encoding="utf-8") == "untouched"
    assert all(content != b"old" for content in _artifact_contents(tmp_path).values())


def test_write_failure_leaves_no_partial_new_artifact_set(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.reporting as reporting

    real_write_csv = reporting._write_csv
    calls = 0

    def fail_third(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated write failure")
        return real_write_csv(*args, **kwargs)

    monkeypatch.setattr(reporting, "_write_csv", fail_third)
    with pytest.raises(OSError, match="simulated"):
        write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert not any((tmp_path / name).exists() for name in OUTPUT_FILENAMES.values())


def test_third_replace_failure_restores_complete_old_set(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.reporting as reporting

    for key, filename in OUTPUT_FILENAMES.items():
        (tmp_path / filename).write_text(f"old-{key}", encoding="utf-8")
    before = _artifact_contents(tmp_path)
    real_replace = reporting.os.replace
    promotions = 0

    def fail_third_promotion(source, destination):
        nonlocal promotions
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.parent.name == "new" and destination_path.parent == tmp_path:
            promotions += 1
            if promotions == 3:
                raise OSError("simulated replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(reporting.os, "replace", fail_third_promotion)
    with pytest.raises(OSError, match="simulated"):
        write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert _artifact_contents(tmp_path) == before
