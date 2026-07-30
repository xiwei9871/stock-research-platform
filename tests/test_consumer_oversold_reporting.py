from __future__ import annotations

import json
import hashlib
import os
import stat
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import UNIFIED_OUTPUT_FILENAMES
from stock_research.consumer_oversold.evidence import (
    EVIDENCE_COLUMNS,
    OUTPUT_COLUMNS,
    validate_repair_evidence,
)
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


OUTPUT_FILENAMES = UNIFIED_OUTPUT_FILENAMES


def _legacy_payload() -> dict[str, object]:
    expected = _selected("000001.SZ", "expected_repair", "甲公司")
    early = _selected("000002.SZ", "early_validation", "乙公司")
    scores = pd.concat([expected, early], ignore_index=True)
    exclusions = pd.DataFrame(
        [{"asset_id": "000003.SZ", "exclusion_reasons": "证据不完整|风险未核验"}]
    )
    return {
        "trade_date": "2026-07-29",
        "evidence": validate_repair_evidence(
            pd.DataFrame(
                [
                    {
                        "asset_id": "000001.SZ",
                        "stock_code": "000001",
                        "evidence_as_of_date": "2026-07-20",
                        "repair_bucket": "expected_repair",
                        "repair_thesis": "需求企稳",
                        "leading_indicator": "月度销量",
                        "unrepaired_metrics": "毛利率",
                        "expected_validation_date": "2026-08-30",
                        "main_risks": "价格战",
                        "invalidation_conditions": "销量继续下滑",
                        "source_title": "公司公告",
                        "source_url": "https://example.com/filing",
                        "source_publish_date": "2026-07-18",
                        "forecast_revision_state": "improving",
                        "audit_review_status": "clear",
                        "audit_review_source_title": "审计报告",
                        "audit_review_source_url": "https://example.com/audit/1",
                        "audit_review_source_publish_date": "2026-07-14",
                        "pledge_debt_review_status": "clear",
                        "pledge_debt_review_source_title": "质押债务核查",
                        "pledge_debt_review_source_url": "https://example.com/pledge/1",
                        "pledge_debt_review_source_publish_date": "2026-07-15",
                        "permanent_impairment_status": "clear",
                        "permanent_impairment_source_title": "永久减值核查",
                        "permanent_impairment_source_url": "https://example.com/impairment/1",
                        "permanent_impairment_source_publish_date": "2026-07-16",
                        "catalyst_verifiability_score": 68.0,
                        "expected_improvement_score": 75.0,
                        "operator_notes": "=external formula",
                    }
                ],
                columns=EVIDENCE_COLUMNS,
            ),
            trade_date="2026-07-29",
        ),
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


def _unified_payload() -> dict[str, object]:
    payload = _legacy_payload()
    top20 = payload.pop("expected").copy(deep=True)
    reserve = payload.pop("early").copy(deep=True)
    for rank, frame in enumerate((top20, reserve), start=1):
        frame["final_rank"] = rank
        frame["repair_rank_percentile"] = 100.0 - (rank - 1) * 50.0
        frame["elasticity_rank_percentile"] = rank * 50.0
        frame["final_rank_score"] = 0.7 * frame["repair_rank_percentile"] + 0.3 * frame[
            "elasticity_rank_percentile"
        ]
        frame["eligible"] = True
        frame["elasticity_coverage"] = True
    preaudit = pd.concat([top20, reserve], ignore_index=True)
    payload.update(
        top20=top20,
        reserve=reserve,
        preaudit=preaudit,
        comparison=pd.DataFrame(
            [
                {"asset_id": "000001.SZ", "old_rank": 1, "new_rank": 1},
                {"asset_id": "000002.SZ", "old_rank": 2, "new_rank": 2},
            ]
        ),
    )
    payload["coverage"].update(
        publication_status="ready",
        final_top_n=1,
        reserve_top_n=1,
        preaudit_size=2,
        minimum_evidence_complete=2,
        unified_funnel={
            "full": 2,
            "automatic": 2,
            "preaudit": 2,
            "evidence_reviewed": 2,
            "evidence_complete": 2,
            "elasticity_complete": 2,
            "final": 1,
            "reserve": 1,
        },
    )
    return payload


def _payload() -> dict[str, object]:
    return _unified_payload()


def test_writes_exactly_nine_unified_artifacts(tmp_path):
    result = write_consumer_oversold_artifacts(_unified_payload(), output_dir=tmp_path)

    assert set(result["paths"]) == set(UNIFIED_OUTPUT_FILENAMES)
    assert set(result) == {
        "paths",
        "evidence",
        "scores",
        "exclusions",
        "coverage",
        "report",
        "top20",
        "reserve",
        "preaudit",
        "comparison",
    }
    assert not ({"expected", "early"} & set(result["paths"]))


def test_report_renders_rank_percentiles_as_zero_to_one_hundred_scores(tmp_path):
    payload = _payload()
    payload["top20"].loc[0, "repair_rank_percentile"] = 100.0
    payload["top20"].loc[0, "elasticity_rank_percentile"] = 82.5

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")

    assert "| 100.0 | 82.5 |" in report
    assert "10000.0%" not in report
    assert "8250.0%" not in report


def test_report_candidate_details_include_market_cap_and_elasticity_metrics(tmp_path):
    payload = _payload()
    metrics = {
        "current_total_market_cap": 12_345_000_000.0,
        "current_float_market_cap": 9_876_000_000.0,
        "market_cap_source": "latest_close_times_shares",
        "limit_up_count_2y": 7,
        "up_7pct_count_2y": 8,
        "up_5pct_count_2y": 9,
        "positive_after_big_up_1d_rate": 0.61,
        "positive_after_big_up_3d_rate": 0.62,
        "positive_after_big_up_5d_rate": 0.63,
        "drawdown_from_high_1y": -0.41,
        "drawdown_from_high_2y": -0.42,
        "price_position_1y": 0.21,
        "price_position_2y": 0.22,
        "distance_hfq_ma120": -0.11,
        "distance_hfq_ma250": -0.12,
        "rebound_from_low_60d": 0.31,
        "rebound_from_low_120d": 0.32,
        "residual_deviation_score": 71.0,
        "stock_character_score": 72.0,
        "market_capacity_score": 73.0,
        "catalyst_liquidity_score": 74.0,
        "elasticity_score": 75.0,
    }
    for field, value in metrics.items():
        payload["scores"].loc[payload["scores"]["asset_id"].eq("000001.SZ"), field] = value
        if field not in {
            "positive_after_big_up_1d_rate",
            "positive_after_big_up_3d_rate",
            "positive_after_big_up_5d_rate",
        }:
            payload["top20"].loc[0, field] = value

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")

    for text in (
        "总市值 123.45 亿元",
        "流通市值 98.76 亿元",
        r"latest\_close\_times\_shares",
        "涨停 7 次",
        "上涨超过7% 8 次",
        "上涨超过5% 9 次",
        "1日 61.0%",
        "3日 62.0%",
        "5日 63.0%",
        "1年回撤 -41.0%",
        "2年回撤 -42.0%",
        "1年位置 21.0%",
        "2年位置 22.0%",
        "MA120 -11.0%",
        "MA250 -12.0%",
        "60日反弹 31.0%",
        "120日反弹 32.0%",
        "残差偏离 71.0",
        "股票特性 72.0",
        "市场容量 73.0",
        "催化流动性 74.0",
        "反弹弹性 75.0",
    ):
        assert text in report


def test_report_always_explains_fixed_three_stock_comparison_outside_preaudit(tmp_path):
    payload = _payload()
    payload["comparison"] = pd.concat(
        [
            payload["comparison"],
            pd.DataFrame(
                [
                    {
                        "asset_id": "600418.SH",
                        "stock_code": "600418",
                        "stock_name": "江淮汽车",
                        "old_combined_rank": 12,
                        "new_rank": 31,
                        "rank_change": -19,
                        "exclusion_reasons": "reserve_only",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    payload["scores"] = pd.concat(
        [
            payload["scores"],
            pd.DataFrame(
                [
                    {
                        "asset_id": "600702.SH",
                        "stock_code": "600702",
                        "stock_name": "舍得酒业",
                        "exclusion_reasons": "evidence_incomplete",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")

    assert "## 江淮汽车、舍得酒业、赛力斯对照" in report
    assert "### 江淮汽车（600418）" in report
    assert "旧排名 12；新排名 31；排名变化 -19" in report
    assert r"reserve\_only" in report
    assert "### 舍得酒业（600702）" in report
    assert "无可用排名" in report
    assert r"evidence\_incomplete" in report
    assert "### 赛力斯（601127）" in report
    assert "未进入本期终端消费审计" in report
    for heading, next_heading in (
        ("### 江淮汽车（600418）", "### 舍得酒业（600702）"),
        ("### 舍得酒业（600702）", "### 赛力斯（601127）"),
        ("### 赛力斯（601127）", "## 剔除原因摘要"),
    ):
        section = report.split(heading, 1)[1].split(next_heading, 1)[0]
        assert "未进入本期终端消费审计" in section


def _artifact_contents(output_dir: Path) -> dict[str, bytes]:
    return {
        key: (output_dir / "current" / filename).read_bytes()
        for key, filename in OUTPUT_FILENAMES.items()
    }


def _tree_snapshot(root: Path) -> list[tuple[str, str, bytes | str]]:
    snapshot: list[tuple[str, str, bytes | str]] = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            snapshot.append((relative, "symlink", os.readlink(path)))
        elif path.is_dir():
            snapshot.append((relative, "dir", b""))
        else:
            snapshot.append((relative, "file", path.read_bytes()))
    return snapshot


def test_writes_nine_stable_artifacts_and_chinese_report(tmp_path):
    result = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path / "nested")

    assert set(result) == {
        "paths",
        "evidence",
        "scores",
        "exclusions",
        "coverage",
        "report",
        "top20",
        "reserve",
        "preaudit",
        "comparison",
    }
    assert set(result["paths"]) == set(OUTPUT_FILENAMES)
    for key, filename in OUTPUT_FILENAMES.items():
        path = Path(result["paths"][key])
        assert path.is_absolute()
        assert path.name == filename
        assert path.parent == tmp_path / "nested" / "current"
        assert path.exists()
    assert (tmp_path / "nested" / "current").is_symlink()
    assert os.readlink(tmp_path / "nested" / "current").startswith(".releases/")

    top20_csv = pd.read_csv(result["paths"]["top20"])
    top20_order = [column for column in REPORT_COLUMNS if column in _payload()["top20"].columns]
    top20_extras = sorted(
        column for column in _payload()["top20"].columns if column not in top20_order
    )
    assert top20_csv.columns.tolist() == [*top20_order, *top20_extras]
    assert top20_csv.loc[0, "stock_name"] == "甲公司"
    evidence_csv = pd.read_csv(result["paths"]["evidence"])
    assert evidence_csv.columns.tolist() == OUTPUT_COLUMNS
    assert evidence_csv.loc[0, "operator_notes"] == "'=external formula"

    coverage = json.loads(Path(result["paths"]["coverage"]).read_text(encoding="utf-8"))
    assert coverage["trade_date"] == "2026-07-29"
    assert coverage["funnel"] == FUNNEL
    assert coverage["warnings"][0] == "部分财务数据滞后"
    assert "final_top_n=1" in coverage["warnings"][1]

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    for text in [
        "2026-07-29",
        "研究候选，不是交易指令",
        "数据覆盖",
        "修复潜力 70% + 反弹弹性 30%",
        "最终统一榜单 Top 20",
        "储备榜单 21-40",
        "审计前 Top 60",
        "新旧排名对照",
        "江淮汽车、舍得酒业、赛力斯对照",
        "剔除原因摘要",
        "警告",
        "失效条件",
        "甲公司",
        "https://example.com/a_(b)",
    ]:
        assert text in report
    assert "白色家电\\|厨电 细分" in report
    assert "公告\\|原文 链接" in report
    assert "CSV 为审阅安全转义" in report


def test_published_evidence_is_immutable_from_later_external_input_changes(tmp_path):
    payload = _payload()
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    release = (tmp_path / "current").resolve()
    evidence_path = release / OUTPUT_FILENAMES["evidence"]
    manifest_path = release / ".manifest.sha256"
    evidence_before = evidence_path.read_bytes()
    manifest_before = manifest_path.read_bytes()

    payload["evidence"].loc[0, "repair_thesis"] = "外部文件随后被修改"

    assert evidence_path.read_bytes() == evidence_before
    assert manifest_path.read_bytes() == manifest_before


def test_release_evidence_tampering_fails_manifest_hash_check(tmp_path):
    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    release = (tmp_path / "current").resolve()
    evidence_path = release / OUTPUT_FILENAMES["evidence"]
    manifest_path = release / ".manifest.sha256"
    expected_digest = next(
        line.split("  ", 1)[0]
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.endswith(f"  {OUTPUT_FILENAMES['evidence']}")
    )

    evidence_path.chmod(0o644)
    evidence_path.write_bytes(evidence_path.read_bytes() + b"tampered")

    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() != expected_digest


def test_rejects_evidence_without_validated_output_columns(tmp_path):
    payload = _payload()
    payload["evidence"] = payload["evidence"].drop(columns=["evidence_complete"])

    with pytest.raises(ValueError, match="evidence missing validated columns: evidence_complete"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_empty_frames_still_write_asset_id_headers_and_missing_markdown_values(tmp_path):
    payload = _payload()
    for key in ("top20", "reserve", "preaudit", "comparison", "scores", "exclusions"):
        payload[key] = pd.DataFrame()
    payload["coverage"].update(publication_status="coverage_insufficient")
    payload["coverage"]["unified_funnel"].update(
        full=0,
        automatic=0,
        preaudit=0,
        evidence_reviewed=0,
        evidence_complete=0,
        elasticity_complete=0,
        final=0,
        reserve=0,
    )

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for key in ("top20", "reserve", "preaudit", "comparison", "scores", "exclusions"):
        assert Path(result["paths"][key]).read_text(encoding="utf-8").splitlines()[0] == "asset_id"
    assert "暂无候选" in Path(result["paths"]["report"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        (lambda p: p.pop("coverage"), ValueError, "missing required keys.*coverage"),
        (lambda p: p.update(top20=[]), TypeError, "top20 must be a pandas DataFrame"),
        (lambda p: p.update(trade_date="20260729"), ValueError, "trade_date"),
        (lambda p: p["coverage"].pop("warnings"), ValueError, "coverage missing required keys.*warnings"),
    ],
)
def test_rejects_missing_or_wrongly_typed_payload(mutation, error, message, tmp_path):
    payload = _payload()
    mutation(payload)
    with pytest.raises(error, match=message):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_rejects_rank_overlap_duplicate_empty_and_gate_contracts(tmp_path):
    payload = _payload()
    payload["reserve"]["asset_id"] = payload["top20"].loc[0, "asset_id"]
    with pytest.raises(ValueError, match="mutually exclusive"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["coverage"]["final_top_n"] = 2
    payload["coverage"]["preaudit_size"] = 3
    payload["coverage"]["minimum_evidence_complete"] = 3
    with pytest.raises(ValueError, match="top20 length"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for field, invalid in [
        ("evidence_complete", False),
        ("eligible", False),
        ("elasticity_coverage", False),
    ]:
        payload = _payload()
        payload["top20"].loc[0, field] = invalid
        with pytest.raises(ValueError, match=field):
            write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for values in (["", "X"], ["X", "X"]):
        payload = _payload()
        payload["preaudit"] = pd.concat([payload["preaudit"].iloc[[0]]] * 2, ignore_index=True)
        payload["preaudit"]["asset_id"] = values
        with pytest.raises(ValueError, match="asset_id"):
            write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize(
    "missing_gate",
    ["evidence_complete", "eligible", "elasticity_coverage"],
)
def test_nonempty_selected_frame_requires_every_publication_gate(missing_gate, tmp_path):
    payload = _payload()
    payload["top20"] = payload["top20"].drop(columns=[missing_gate])

    with pytest.raises(ValueError, match=f"top20 missing required columns.*{missing_gate}"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize(
    ("frame_name", "bad_rank"),
    [("top20", 2), ("reserve", 1)],
)
def test_nonempty_selected_frame_requires_its_exact_rank_range(frame_name, bad_rank, tmp_path):
    payload = _payload()
    payload[frame_name] = payload[frame_name].drop(columns=["final_rank"])
    with pytest.raises(ValueError, match=f"{frame_name} missing required columns.*final_rank"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload[frame_name].loc[0, "final_rank"] = bad_rank
    with pytest.raises(ValueError, match=f"{frame_name} final_rank"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize("bad_count", [True, 1.5, -1, "1"])
def test_funnel_counts_are_nonnegative_strict_integers(bad_count, tmp_path):
    payload = _payload()
    payload["coverage"]["funnel"]["raw_assets"] = bad_count
    with pytest.raises((TypeError, ValueError), match="raw_assets.*integer|raw_assets.*non-negative"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_funnel_order_and_unified_counts_are_consistent(tmp_path):
    payload = _payload()
    payload["coverage"]["funnel"]["consumer_universe"] = 101
    with pytest.raises(ValueError, match="funnel.*non-increasing"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["coverage"]["unified_funnel"]["final"] = 0
    with pytest.raises(ValueError, match="unified_funnel final.*top20"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["coverage"]["funnel"]["valuation_eligible"] = 1
    with pytest.raises(ValueError, match="selected_expected.*selected_early"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("full", 1),
        ("automatic", 1),
        ("evidence_reviewed", 1),
        ("evidence_complete", 0),
        ("elasticity_complete", 0),
    ],
)
def test_rejects_unified_funnel_invariant_violations(field, value, tmp_path):
    payload = _payload()
    payload["coverage"]["unified_funnel"][field] = value

    with pytest.raises(ValueError, match="unified_funnel|ready publication"):
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
    originals = {
        key: payload[key].copy(deep=True)
        for key in ("top20", "reserve", "preaudit", "comparison", "scores", "exclusions")
    }

    write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    for key, original in originals.items():
        pd.testing.assert_frame_equal(payload[key], original)


def test_csv_text_formula_cells_are_escaped_without_changing_numeric_cells(tmp_path):
    payload = _payload()
    payload["top20"].loc[0, "stock_name"] = " =2+2"
    payload["top20"].loc[0, "a_extra"] = "@cmd"

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    written = pd.read_csv(result["paths"]["top20"])
    assert written.loc[0, "stock_name"] == "' =2+2"
    assert written.loc[0, "a_extra"] == "'@cmd"
    assert written.loc[0, "return_6m"] == pytest.approx(-0.31)
    assert payload["top20"].loc[0, "stock_name"] == " =2+2"


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://example.com/a b",
        "https://example.com/<bad>",
        "https://example.com/a\tb",
        "https://example.com:bad/path",
        "https://user@example.com/path",
        "https://localhost/path",
        "https://127.0.0.1/path",
        "ftp://example.com/path",
    ],
)
def test_report_rejects_urls_that_can_break_markdown_link_boundaries(bad_url, tmp_path):
    payload = _payload()
    payload["top20"].loc[0, "source_url"] = bad_url
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert bad_url not in report


def test_report_escapes_markdown_link_label_metacharacters(tmp_path):
    payload = _payload()
    payload["top20"].loc[0, "source_title"] = "反\\斜[左]|右]\n下一行"
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    source_line = next(
        line for line in Path(result["paths"]["report"]).read_text(encoding="utf-8").splitlines()
        if line.startswith("- 来源：") and "example.com" in line
    )
    assert "反\\\\斜\\[左\\]\\|右\\] 下一行" in source_line


def test_existing_release_switches_once_and_unrelated_file_is_preserved(tmp_path, monkeypatch):
    first = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_target = os.readlink(tmp_path / "current")
    old_contents = _artifact_contents(tmp_path)
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("untouched", encoding="utf-8")
    payload = _payload()
    payload["top20"].loc[0, "stock_name"] = "新甲公司"
    real_replace = os.replace
    observations = []

    def observe_switch(source, destination):
        if Path(destination) == tmp_path / "current":
            observations.append((os.readlink(tmp_path / "current"), _artifact_contents(tmp_path)))
            result = real_replace(source, destination)
            observations.append((os.readlink(tmp_path / "current"), _artifact_contents(tmp_path)))
            return result
        return real_replace(source, destination)

    monkeypatch.setattr("stock_research.consumer_oversold.reporting.os.replace", observe_switch)
    second = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    assert len(observations) == 2
    assert observations[0] == (old_target, old_contents)
    assert observations[1][0] != old_target
    assert observations[1][1] == _artifact_contents(tmp_path)
    assert (tmp_path / old_target).is_dir()
    assert Path(first["paths"]["top20"]).read_text(encoding="utf-8") != ""
    assert "新甲公司" in Path(second["paths"]["top20"]).read_text(encoding="utf-8")
    assert unrelated.read_text(encoding="utf-8") == "untouched"


def test_publish_uses_exclusive_flock(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.reporting as reporting

    calls = []
    monkeypatch.setattr(reporting.fcntl, "flock", lambda fd, operation: calls.append(operation))
    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    assert calls == [reporting.fcntl.LOCK_EX, reporting.fcntl.LOCK_UN]


def test_stale_tool_entries_are_cleaned_without_touching_unrelated_files(tmp_path):
    releases = tmp_path / ".releases"
    releases.mkdir(parents=True)
    stale_dir = releases / ".consumer-oversold-staging-stale"
    stale_dir.mkdir()
    stale_link = tmp_path / ".consumer-oversold-current-tmp-stale"
    stale_link.symlink_to(".releases/missing")
    unrelated = tmp_path / ".someone-else-staging"
    unrelated.mkdir()

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert not stale_dir.exists()
    assert not stale_link.exists() and not stale_link.is_symlink()
    assert unrelated.is_dir()


def test_rejects_releases_symlink_without_touching_external_victim(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    victim = tmp_path / "victim"
    managed_looking = victim / "consumer-oversold-existing"
    managed_looking.mkdir(parents=True)
    (victim / "sentinel.txt").write_text("sentinel", encoding="utf-8")
    (managed_looking / "artifact.txt").write_text("preserve", encoding="utf-8")
    before = _tree_snapshot(victim)
    (output / ".releases").symlink_to(victim, target_is_directory=True)

    with pytest.raises(ValueError, match=r"\.releases"):
        write_consumer_oversold_artifacts(_payload(), output_dir=output)

    assert _tree_snapshot(victim) == before


def test_rejects_publish_lock_symlink_without_touching_external_file(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    victim = tmp_path / "external.lock"
    victim.write_bytes(b"external-lock-sentinel")
    (output / ".publish.lock").symlink_to(victim)

    with pytest.raises((OSError, ValueError), match="publish.lock|symlink|symbolic"):
        write_consumer_oversold_artifacts(_payload(), output_dir=output)

    assert victim.read_bytes() == b"external-lock-sentinel"
    assert not (output / ".releases").exists()


@pytest.mark.parametrize(
    "target_kind",
    ["absolute", "parent", "wrong_namespace", "missing_managed", "symlinked_managed"],
)
def test_rejects_unsafe_current_symlink_targets(target_kind, tmp_path):
    output = tmp_path / "output"
    releases = output / ".releases"
    releases.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "sentinel.txt").write_text("sentinel", encoding="utf-8")
    before = _tree_snapshot(victim)
    if target_kind == "absolute":
        target = str(victim)
    elif target_kind == "parent":
        target = ".releases/../victim"
    elif target_kind == "wrong_namespace":
        target = "other/consumer-oversold-existing"
    elif target_kind == "missing_managed":
        target = ".releases/consumer-oversold-missing"
    else:
        (releases / "consumer-oversold-linked").symlink_to(
            victim, target_is_directory=True
        )
        target = ".releases/consumer-oversold-linked"
    (output / "current").symlink_to(target)

    with pytest.raises(ValueError, match="current"):
        write_consumer_oversold_artifacts(_payload(), output_dir=output)

    assert os.readlink(output / "current") == target
    assert _tree_snapshot(victim) == before


def test_first_publish_creates_complete_current_release(tmp_path):
    assert not (tmp_path / "current").exists()
    result = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    assert (tmp_path / "current").is_symlink()
    assert set(path.name for path in (tmp_path / "current").iterdir()) == {
        *OUTPUT_FILENAMES.values(),
        ".manifest.sha256",
    }
    assert all(Path(path).exists() for path in result["paths"].values())


def test_release_is_hash_verified_and_sealed_read_only(tmp_path):
    result = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    release = (tmp_path / "current").resolve()
    manifest = release / ".manifest.sha256"

    assert set(result["paths"]) == set(OUTPUT_FILENAMES)
    assert manifest.is_file()
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", 1)
        entries[filename] = digest
    assert list(entries) == sorted(OUTPUT_FILENAMES.values())
    assert set(entries) == set(OUTPUT_FILENAMES.values())
    for filename, digest in entries.items():
        artifact = release / filename
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o444
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o444
    assert stat.S_IMODE(release.stat().st_mode) == 0o555


def test_old_sealed_release_bytes_remain_unchanged_after_next_publish(tmp_path):
    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_release = (tmp_path / "current").resolve()
    before = {path.name: path.read_bytes() for path in old_release.iterdir() if path.is_file()}

    payload = _payload()
    payload["top20"].loc[0, "stock_name"] = "新版本公司"
    write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    assert {path.name: path.read_bytes() for path in old_release.iterdir() if path.is_file()} == before
    assert stat.S_IMODE(old_release.stat().st_mode) == 0o555


def test_write_failure_keeps_current_on_complete_old_release(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.reporting as reporting

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_target = os.readlink(tmp_path / "current")
    old_contents = _artifact_contents(tmp_path)
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

    assert os.readlink(tmp_path / "current") == old_target
    assert _artifact_contents(tmp_path) == old_contents


@pytest.mark.parametrize("failure_point", ["fsync", "symlink", "replace"])
def test_prepublication_failure_keeps_current_on_complete_old_release(
    failure_point, tmp_path, monkeypatch
):
    import stock_research.consumer_oversold.reporting as reporting

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_target = os.readlink(tmp_path / "current")
    old_contents = _artifact_contents(tmp_path)
    if failure_point == "fsync":
        monkeypatch.setattr(reporting, "_dir_fsync", lambda path: (_ for _ in ()).throw(OSError("fsync failed")))
    elif failure_point == "symlink":
        monkeypatch.setattr(reporting.os, "symlink", lambda *args: (_ for _ in ()).throw(OSError("symlink failed")))
    else:
        real_replace = reporting.os.replace

        def fail_current_replace(source, destination):
            if Path(destination) == tmp_path / "current":
                raise OSError("replace failed")
            return real_replace(source, destination)

        monkeypatch.setattr(reporting.os, "replace", fail_current_replace)

    with pytest.raises(OSError, match="failed"):
        write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert os.readlink(tmp_path / "current") == old_target
    assert _artifact_contents(tmp_path) == old_contents


def test_post_switch_fsync_failure_durably_restores_old_current(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.reporting as reporting

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_target = os.readlink(tmp_path / "current")
    old_contents = _artifact_contents(tmp_path)
    real_dir_fsync = reporting._dir_fsync
    output_fsyncs = 0

    def fail_post_switch_once(path):
        nonlocal output_fsyncs
        if Path(path) == tmp_path:
            output_fsyncs += 1
            if output_fsyncs == 2:
                raise OSError("post-switch fsync failed")
        return real_dir_fsync(path)

    monkeypatch.setattr(reporting, "_dir_fsync", fail_post_switch_once)
    with pytest.raises(OSError, match="post-switch"):
        write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert output_fsyncs == 3
    assert os.readlink(tmp_path / "current") == old_target
    assert _artifact_contents(tmp_path) == old_contents


@pytest.mark.parametrize("rollback_failure", ["replace", "fsync"])
def test_incomplete_post_switch_rollback_is_explicit_and_preserves_new_release(
    rollback_failure, tmp_path, monkeypatch
):
    import stock_research.consumer_oversold.reporting as reporting

    write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    old_target = os.readlink(tmp_path / "current")
    real_dir_fsync = reporting._dir_fsync
    real_replace = reporting.os.replace
    output_fsyncs = 0
    current_replaces = 0

    def fail_output_fsync(path):
        nonlocal output_fsyncs
        if Path(path) == tmp_path:
            output_fsyncs += 1
            if output_fsyncs == 2 or (rollback_failure == "fsync" and output_fsyncs == 3):
                raise OSError(f"rollback {rollback_failure} failed")
        return real_dir_fsync(path)

    def fail_restore_replace(source, destination):
        nonlocal current_replaces
        if Path(destination) == tmp_path / "current":
            current_replaces += 1
            if rollback_failure == "replace" and current_replaces == 2:
                raise OSError("rollback replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(reporting, "_dir_fsync", fail_output_fsync)
    monkeypatch.setattr(reporting.os, "replace", fail_restore_replace)
    with pytest.raises(RuntimeError, match="rollback incomplete") as caught:
        write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)

    assert isinstance(caught.value.__cause__, OSError)
    current_target = os.readlink(tmp_path / "current")
    if rollback_failure == "replace":
        assert current_target != old_target
    else:
        assert current_target == old_target
    assert (tmp_path / current_target).is_dir()
    releases = [path for path in (tmp_path / ".releases").iterdir() if not path.name.startswith(".")]
    assert len(releases) == 2


def test_all_external_markdown_text_is_rendered_inert(tmp_path):
    payload = _payload()
    attack = "\\escape [link](https://evil) ![img](x) *em* _u_ `code` # head > quote <script>&"
    for frame_name in ("top20", "reserve"):
        for column in (
            "stock_name",
            "consumer_subindustry",
            "repair_thesis",
            "leading_indicator",
            "main_risks",
            "invalidation_conditions",
            "source_title",
        ):
            payload[frame_name].loc[0, column] = attack + "\r\nnext"
        payload[frame_name]["return_6m"] = payload[frame_name]["return_6m"].astype(object)
        payload[frame_name].loc[0, "return_6m"] = "[numeric-link](https://evil)"
    payload["coverage"]["warnings"] = [attack + "\nnext"]

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")

    assert "[link](https://evil)" not in report
    assert "[numeric-link](https://evil)" not in report
    assert "![img](x)" not in report
    assert "<script>" not in report
    assert "&lt;script&gt;&amp;" in report
    assert "\\[link\\]\\(https://evil\\)" in report
    assert "\\!\\[img\\]\\(x\\)" in report
    assert "\\# head &gt; quote" in report
    assert "\nnext" not in report
