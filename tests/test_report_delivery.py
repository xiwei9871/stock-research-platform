from decimal import Decimal
import json
from pathlib import Path

import pandas as pd

from stock_research import report_delivery, run_card
from stock_research.reports import watchlist_report


def test_collect_artifacts_aggregates_real_run_card_bundle(tmp_path):
    output = run_card.write_run_card(
        output_dir=tmp_path / "run-cards",
        run_type="daily_research",
        run_id="2026-05-20-core",
        title="Daily Research",
        config={"universe": "core"},
        metrics={"rows": 2},
        artifact_paths={"report": "daily_research.md"},
        warnings=["coverage gap"],
        metadata={"owner": "test"},
        data_coverage={"expected_dates": ["2026-05-20"], "actual_dates": ["2026-05-20"]},
    )

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[],
        run_card_dirs=[output["run_card_dir"]],
        artifact_paths=[],
    )

    run_card_artifact = next(item for item in artifacts if item.report_type == "run_card")

    assert len([item for item in artifacts if item.report_type == "run_card"]) == 1
    assert "evidence_bundle" not in {item.report_type for item in artifacts}
    assert run_card_artifact.run_card_path == output["run_card_json_path"]
    assert run_card_artifact.evidence_dir == str((Path(output["run_card_dir"]) / "evidence"))
    assert warnings == []


def test_collect_artifacts_aggregates_real_watchlist_outputs(tmp_path):
    signal_rows = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "watchlist_id": "core",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "Ping An Bank",
                "priority": 1,
                "signal_score": Decimal("9.5"),
                "primary_signal": "breakout",
                "signal_tags": ["breakout", "volume"],
                "risk_tags": [],
                "reason_json": {"thesis": "momentum"},
                "must_watch": True,
            },
            {
                "trade_date": "2026-05-20",
                "watchlist_id": "core",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "Vanke",
                "priority": 2,
                "signal_score": Decimal("7.1"),
                "primary_signal": "pullback",
                "signal_tags": ["pullback"],
                "risk_tags": ["risk_excluded"],
                "reason_json": {"thesis": "mean_reversion"},
                "must_watch": False,
            },
        ]
    )
    output = watchlist_report.write_watchlist_report(
        signal_rows,
        output_dir=tmp_path / "watchlists",
    )

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[tmp_path / "watchlists"],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    watchlist_artifact = next(item for item in artifacts if item.report_type == "watchlist")

    assert len([item for item in artifacts if item.report_type == "watchlist"]) == 1
    assert watchlist_artifact.markdown_path == output["markdown_path"]
    assert watchlist_artifact.json_path == output["json_path"]
    assert watchlist_artifact.csv_paths == [
        output["signals_csv_path"],
        output["must_watch_csv_path"],
    ]
    assert warnings == []


def test_collect_artifacts_returns_warning_for_empty_input_dir(tmp_path):
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [f"no_artifacts_found:{input_dir}"]


def test_collect_artifacts_warns_for_missing_explicit_dirs(tmp_path):
    missing_report_dir = tmp_path / "missing-report-dir"
    missing_run_card_dir = tmp_path / "missing-run-card-dir"

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[missing_report_dir],
        run_card_dirs=[missing_run_card_dir],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [
        f"missing_report_dir:{missing_report_dir}",
        f"missing_run_card_dir:{missing_run_card_dir}",
    ]


def test_collect_artifacts_warns_for_missing_explicit_path(tmp_path):
    missing_input_dir = tmp_path / "missing-input"

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[missing_input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [f"missing_input_dir:{missing_input_dir}"]


def test_collect_artifacts_warns_for_missing_explicit_artifact_path(tmp_path):
    missing_artifact_path = tmp_path / "missing-artifact.json"

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[missing_artifact_path],
    )

    assert artifacts == []
    assert warnings == [f"missing_artifact_path:{missing_artifact_path}"]


def test_collect_artifacts_classifies_daily_topn_markdown_artifact(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text("# topn\n", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    artifact = next(item for item in artifacts if item.markdown_path is not None)

    assert warnings == []
    assert artifact.report_type == "daily_topn_report"
    assert artifact.severity == "info"
    assert artifact.summary == "Daily TopN"
    assert artifact.tags == ["daily", "topn"]
    assert artifact.recommended_channels == ["local", "openclaw"]
    assert artifact.requires_attention is False
    assert artifact.delivery_priority == 10


def test_deliver_local_writes_manifest_and_delivery_log(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text("# topn\n", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    result = adapter.deliver_local(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=False,
    )

    manifest_path = Path(result.manifest_path)
    delivery_log_path = Path(result.delivery_log_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log_lines = delivery_log_path.read_text(encoding="utf-8").splitlines()
    copied_artifacts = sorted((tmp_path / "delivery" / "artifacts").rglob("*"))

    assert result.status == "completed"
    assert result.channel == "local"
    assert result.artifact_count == 1
    assert manifest["channel"] == "local"
    assert manifest["trade_date"] == "2026-05-20"
    assert manifest["artifact_count"] == 1
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["status"] == "completed"
    assert any(path.name == "daily_topn_2026-05-20_manual_v1.md" for path in copied_artifacts)


def test_deliver_local_reports_dry_run_manifest_includes_classification_fields(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text("# topn\n", encoding="utf-8")

    result = report_delivery.deliver_local_reports(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]

    assert result.status == "dry_run"
    assert manifest["channel"] == "local"
    assert manifest["trade_date"] == "2026-05-20"
    assert manifest["artifact_count"] == 1
    assert manifest["warnings"] == []
    assert manifest["errors"] == []
    assert len(manifest["artifacts"]) == 1
    assert artifact["report_type"] == "daily_topn_report"
    assert artifact["severity"] == "info"
    assert artifact["summary"] == "Daily TopN"
    assert artifact["tags"] == ["daily", "topn"]
    assert artifact["recommended_channels"] == ["local", "openclaw"]
    assert artifact["requires_attention"] is False
    assert artifact["delivery_priority"] == 10


def test_deliver_local_dry_run_does_not_write_delivery_log(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "watchlist_report_2026-05-20_core.md").write_text("# watchlist\n", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    result = adapter.deliver_local(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert result.delivery_log_path is None
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 1
    assert not (tmp_path / "delivery" / "artifacts").exists()
    assert not (tmp_path / "delivery" / "delivery_log.jsonl").exists()


def test_deliver_local_reports_returns_clear_error_for_missing_input_dir(tmp_path):
    missing_input_dir = tmp_path / "missing"

    result = report_delivery.deliver_local_reports(
        trade_date="2026-05-20",
        input_dirs=[missing_input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    assert result.status == "error"
    assert result.artifact_count == 0
    assert result.errors == [f"missing_input_dir:{missing_input_dir}"]
