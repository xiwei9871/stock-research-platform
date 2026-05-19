import json
from pathlib import Path

from stock_research import run_card


def test_write_run_card_writes_json_markdown_and_manifest(tmp_path):
    result = run_card.write_run_card(
        output_dir=tmp_path,
        run_type="factor_eval",
        run_id="run-1",
        title="Factor Eval",
        config={"factor_name": "ret_20"},
        metrics={"mean_ic": 0.03},
        artifact_paths={"report": "/tmp/report.md"},
        data_coverage={"row_count": 1, "asset_count": 1},
    )

    run_dir = Path(result["run_card_dir"])
    assert run_dir.exists()
    assert (run_dir / "run_card.json").exists()
    assert (run_dir / "run_card.md").exists()
    assert (run_dir / "evidence" / "manifest.json").exists()
    assert Path(result["metrics_json_path"]).exists()
    assert Path(result["config_snapshot_path"]).exists()
    assert Path(result["warnings_md_path"]).exists()
    assert Path(result["data_coverage_json_path"]).exists()
    assert result["run_card_json_path"].endswith("run_card.json")

    payload = json.loads((run_dir / "run_card.json").read_text(encoding="utf-8"))
    assert payload["run_type"] == "factor_eval"
    assert payload["metrics"]["mean_ic"] == 0.03
    assert payload["metadata"] == {}
    assert json.loads(Path(result["metrics_json_path"]).read_text(encoding="utf-8"))["mean_ic"] == 0.03
    assert json.loads(Path(result["config_snapshot_path"]).read_text(encoding="utf-8"))["factor_name"] == "ret_20"
    assert json.loads(Path(result["data_coverage_json_path"]).read_text(encoding="utf-8"))["row_count"] == 1


def test_write_run_card_uses_unique_subdirectories_without_overwriting_previous_run(tmp_path):
    first = run_card.write_run_card(
        output_dir=tmp_path,
        run_type="factor_eval",
        run_id="run-1",
        title="Factor Eval",
        config={"factor_name": "ret_20"},
        metrics={"mean_ic": 0.03},
        artifact_paths={"report": "/tmp/report_a.md"},
    )
    first_json = Path(first["run_card_json_path"])
    first_payload = json.loads(first_json.read_text(encoding="utf-8"))

    second = run_card.write_run_card(
        output_dir=tmp_path,
        run_type="factor_eval",
        run_id="run-1",
        title="Factor Eval",
        config={"factor_name": "ret_20"},
        metrics={"mean_ic": 0.04},
        artifact_paths={"report": "/tmp/report_b.md"},
    )
    second_json = Path(second["run_card_json_path"])

    assert first["run_card_dir"] != second["run_card_dir"]
    assert first["run_card_json_path"] != second["run_card_json_path"]
    assert first["run_card_md_path"] != second["run_card_md_path"]
    assert first_json.exists()
    assert second_json.exists()
    assert json.loads(first_json.read_text(encoding="utf-8")) == first_payload
    assert json.loads(second_json.read_text(encoding="utf-8"))["metrics"]["mean_ic"] == 0.04


def test_build_run_card_markdown_includes_config_metrics_and_artifacts():
    payload = run_card.build_run_card_payload(
        run_type="vectorized_backtest",
        run_id="backtest-1",
        title="Vectorized Backtest",
        config={"top_n": 20},
        metrics={"total_return": 0.12},
        artifact_paths={"equity_curve": "/tmp/equity.csv"},
    )

    markdown = run_card.render_run_card_markdown(payload)

    assert "Vectorized Backtest" in markdown
    assert "top_n" in markdown
    assert "total_return" in markdown
    assert "equity_curve" in markdown
    assert "## Metadata" in markdown


def test_write_run_card_writes_warnings_markdown(tmp_path):
    result = run_card.write_run_card(
        output_dir=tmp_path,
        run_type="daily_pipeline",
        run_id="run-2",
        title="Daily Pipeline",
        config={"trade_date": "2026-05-08"},
        metrics={"top_scores_count": 0},
        warnings=["top_scores_empty"],
        data_coverage={"row_count": 0, "asset_count": 0},
    )

    warnings_text = Path(result["warnings_md_path"]).read_text(encoding="utf-8")
    assert "top_scores_empty" in warnings_text


def test_normalize_data_coverage_leaves_unknown_fields_null_without_expected_sets():
    coverage = run_card.normalize_data_coverage(
        {
            "input_start_date": "2026-05-08",
            "input_end_date": "2026-05-08",
            "actual_dates": ["2026-05-08"],
            "row_count": 3,
            "asset_count": 2,
        }
    )

    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None
    assert coverage["expected_dates"] is None
    assert coverage["expected_assets"] is None


def test_normalize_data_coverage_calculates_missing_dates_and_ratio_when_expected_dates_known():
    coverage = run_card.normalize_data_coverage(
        {
            "expected_dates": ["2026-05-08", "2026-05-09"],
            "actual_dates": ["2026-05-08"],
        }
    )

    assert coverage["missing_dates"] == ["2026-05-09"]
    assert coverage["coverage_ratio"] == 0.5


def test_normalize_data_coverage_calculates_empty_missing_dates_when_expected_dates_fully_covered():
    coverage = run_card.normalize_data_coverage(
        {
            "expected_dates": ["2026-05-08", "2026-05-09"],
            "actual_dates": ["2026-05-08", "2026-05-09"],
        }
    )

    assert coverage["missing_dates"] == []
    assert coverage["coverage_ratio"] == 1.0
