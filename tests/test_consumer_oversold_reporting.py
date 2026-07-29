from __future__ import annotations

import json
import os
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
        key: (output_dir / "current" / filename).read_bytes()
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
        assert path.parent == tmp_path / "nested" / "current"
        assert path.exists()
    assert (tmp_path / "nested" / "current").is_symlink()
    assert os.readlink(tmp_path / "nested" / "current").startswith(".releases/")

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
    assert "CSV 为审阅安全转义" in report


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
    payload["early"]["repair_bucket"] = "early_validation"
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


@pytest.mark.parametrize(
    "missing_gate",
    ["evidence_complete", "hard_risk_triggered", "hard_risk_review_unknown"],
)
def test_nonempty_selected_frame_requires_every_risk_gate(missing_gate, tmp_path):
    payload = _payload()
    payload["expected"] = payload["expected"].drop(columns=[missing_gate])

    with pytest.raises(ValueError, match=f"expected missing required columns.*{missing_gate}"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize(
    ("frame_name", "bucket"),
    [("expected", "expected_repair"), ("early", "early_validation")],
)
def test_nonempty_selected_frame_requires_its_exact_repair_bucket(frame_name, bucket, tmp_path):
    payload = _payload()
    payload[frame_name] = payload[frame_name].drop(columns=["repair_bucket"])
    with pytest.raises(ValueError, match=f"{frame_name} missing required columns.*repair_bucket"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload[frame_name].loc[0, "repair_bucket"] = "wrong_bucket"
    with pytest.raises(ValueError, match=f"{frame_name} field repair_bucket.*{bucket}"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


@pytest.mark.parametrize("bad_count", [True, 1.5, -1, "1"])
def test_funnel_counts_are_nonnegative_strict_integers(bad_count, tmp_path):
    payload = _payload()
    payload["coverage"]["funnel"]["raw_assets"] = bad_count
    with pytest.raises((TypeError, ValueError), match="raw_assets.*integer|raw_assets.*non-negative"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)


def test_funnel_order_and_selected_counts_are_consistent(tmp_path):
    payload = _payload()
    payload["coverage"]["funnel"]["consumer_universe"] = 101
    with pytest.raises(ValueError, match="funnel.*non-increasing"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["coverage"]["funnel"]["selected_expected"] = 0
    with pytest.raises(ValueError, match="selected_expected.*expected"):
        write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    payload = _payload()
    payload["coverage"]["funnel"]["valuation_eligible"] = 1
    with pytest.raises(ValueError, match="selected_expected.*selected_early"):
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


def test_csv_text_formula_cells_are_escaped_without_changing_numeric_cells(tmp_path):
    payload = _payload()
    payload["expected"].loc[0, "stock_name"] = " =2+2"
    payload["expected"].loc[0, "a_extra"] = "@cmd"

    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    written = pd.read_csv(result["paths"]["expected"])
    assert written.loc[0, "stock_name"] == "' =2+2"
    assert written.loc[0, "a_extra"] == "'@cmd"
    assert written.loc[0, "return_6m"] == pytest.approx(-0.31)
    assert payload["expected"].loc[0, "stock_name"] == " =2+2"


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
    payload["expected"].loc[0, "source_url"] = bad_url
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert bad_url not in report


def test_report_escapes_markdown_link_label_metacharacters(tmp_path):
    payload = _payload()
    payload["expected"].loc[0, "source_title"] = "反\\斜[左]|右]\n下一行"
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
    payload["expected"].loc[0, "stock_name"] = "新甲公司"
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
    assert Path(first["paths"]["expected"]).read_text(encoding="utf-8") != ""
    assert "新甲公司" in Path(second["paths"]["expected"]).read_text(encoding="utf-8")
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


def test_first_publish_creates_complete_current_release(tmp_path):
    assert not (tmp_path / "current").exists()
    result = write_consumer_oversold_artifacts(_payload(), output_dir=tmp_path)
    assert (tmp_path / "current").is_symlink()
    assert set(path.name for path in (tmp_path / "current").iterdir()) == set(OUTPUT_FILENAMES.values())
    assert all(Path(path).exists() for path in result["paths"].values())


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
