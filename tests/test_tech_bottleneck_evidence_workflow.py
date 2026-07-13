from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.tech_bottleneck_evidence_workflow import (
    build_tech_bottleneck_evidence_workflow,
)


def _asset_queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "ts_code": "300308.SZ",
                "primary_chain_id": "ai_optical_interconnect",
                "source_collection_priority": 150,
            },
            {
                "asset_id": "CN:SH:600855",
                "stock_name": "航天长峰",
                "ts_code": "600855.SH",
                "primary_chain_id": "high_end_sensors",
                "source_collection_priority": 132,
                "missing_fields": "stale_input_value",
            },
            {
                "asset_id": "CN:SZ:003026",
                "stock_name": "中晶科技",
                "ts_code": "003026.SZ",
                "primary_chain_id": "semiconductor_materials",
                "source_collection_priority": 132,
            },
        ]
    )


def _evidence_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "source_backed_field_count": 3,
                "artifact_only_or_missing_field_count": 0,
                "revenue_exposure_bucket_evidence_grade": "primary_strong",
                "customer_certification_stage_evidence_grade": "primary_strong",
                "supplier_concentration_type_evidence_grade": "primary_strong",
            },
            {
                "asset_id": "CN:SH:600855",
                "source_backed_field_count": 0,
                "artifact_only_or_missing_field_count": 3,
                "revenue_exposure_bucket_evidence_grade": "missing",
                "customer_certification_stage_evidence_grade": "missing",
                "supplier_concentration_type_evidence_grade": "missing",
            },
            {
                "asset_id": "CN:SZ:003026",
                "source_backed_field_count": 2,
                "artifact_only_or_missing_field_count": 1,
                "revenue_exposure_bucket_evidence_grade": "primary_strong",
                "customer_certification_stage_evidence_grade": "missing",
                "supplier_concentration_type_evidence_grade": "primary_partial",
            },
        ]
    )


def test_workflow_builds_topn_backfill_queue_and_daily_weak_evidence_rescore(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-06-18", "asset_id": "CN:SH:600855", "bottleneck_rank": 1, "bottleneck_score": 0.90},
            {"trade_date": "2026-06-18", "asset_id": "CN:SZ:300308", "bottleneck_rank": 2, "bottleneck_score": 0.82},
            {"trade_date": "2026-06-18", "asset_id": "CN:SZ:003026", "bottleneck_rank": 3, "bottleneck_score": 0.80},
        ]
    )

    result = build_tech_bottleneck_evidence_workflow(
        asset_queue=_asset_queue(),
        evidence_detail=_evidence_detail(),
        candidates=candidates,
        trade_date="2026-06-18",
        top_n=3,
        output_dir=tmp_path,
    )

    top_queue = result["topn_backfill_queue"]
    assert top_queue["asset_id"].tolist() == ["CN:SH:600855", "CN:SZ:003026"]
    assert top_queue.set_index("asset_id").loc["CN:SH:600855", "evidence_status"] == "missing_blocking"
    assert top_queue.set_index("asset_id").loc["CN:SH:600855", "missing_fields"] != "stale_input_value"
    assert "customer_certification_stage" in top_queue.set_index("asset_id").loc["CN:SZ:003026", "missing_fields"]

    weak = result["weak_evidence_queue"]
    assert weak["asset_id"].tolist() == ["CN:SH:600855", "CN:SZ:003026"]
    assert weak.set_index("asset_id").loc["CN:SH:600855", "evidence_status"] == "missing_blocking"

    adjusted = result["adjusted_candidates"].sort_values("evidence_adjusted_rank")
    assert adjusted.iloc[0]["asset_id"] == "CN:SZ:300308"
    assert adjusted.set_index("asset_id").loc["CN:SH:600855", "evidence_confidence_multiplier"] == 0.6
    assert Path(result["paths"]["weak_evidence_queue"]).exists()


def test_cli_dispatches_tech_bottleneck_evidence_workflow(monkeypatch, tmp_path: Path, capsys):
    asset_path = tmp_path / "assets.csv"
    evidence_path = tmp_path / "evidence.csv"
    candidate_path = tmp_path / "candidates.csv"
    asset_path.write_text("asset_id\nA\n", encoding="utf-8")
    evidence_path.write_text("asset_id\nA\n", encoding="utf-8")
    candidate_path.write_text("asset_id\nA\n", encoding="utf-8")
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {
            "topn_backfill_queue": pd.DataFrame([{"asset_id": "A"}]),
            "weak_evidence_queue": pd.DataFrame([{"asset_id": "A"}]),
            "adjusted_candidates": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "topn_backfill_queue": str(tmp_path / "top.csv"),
                "weak_evidence_queue": str(tmp_path / "weak.csv"),
                "adjusted_candidates": str(tmp_path / "adjusted.csv"),
                "yanbaoke_tasks": str(tmp_path / "yanbaoke.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_tech_bottleneck_evidence_workflow", fake_run, raising=False)

    cli.main(
        [
            "tech-bottleneck-evidence-workflow",
            "--asset-queue-path",
            str(asset_path),
            "--evidence-detail-path",
            str(evidence_path),
            "--candidate-path",
            str(candidate_path),
            "--trade-date",
            "2026-06-18",
            "--top-n",
            "100",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert called["asset_queue_path"] == str(asset_path)
    assert called["evidence_detail_path"] == str(evidence_path)
    assert called["candidate_path"] == str(candidate_path)
    assert called["trade_date"] == "2026-06-18"
    assert called["top_n"] == 100
    out = capsys.readouterr().out
    assert "tech_bottleneck_evidence|weak_queue|" in out
