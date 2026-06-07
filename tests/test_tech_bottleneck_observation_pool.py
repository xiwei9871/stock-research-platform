from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_observation_pool import (
    build_observation_pool,
    run_observation_pool_from_files,
)


def test_build_observation_pool_creates_asset_level_pool_and_comparison_groups() -> None:
    promotion_assets = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "review_priority": "P1_observe",
                "review_action": "add_to_observation_pool",
                "product_family": "chrome_chemicals",
                "evidence_quality_score": 12,
                "candidate_count_for_asset": 1,
                "candidate_dates_for_asset": "2025-04-30",
            },
            {
                "asset_id": "CN:SH:603239",
                "stock_name": "浙江仙通",
                "trade_date": "2025-05-16",
                "review_priority": "P2_observe_after_review",
                "review_action": "add_to_observation_pool",
                "product_family": "auto_sealing",
                "evidence_quality_score": 9,
                "candidate_count_for_asset": 1,
                "candidate_dates_for_asset": "2025-05-16",
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {"asset_id": "CN:SH:603067", "stock_name": "振华股份", "trade_date": "2025-04-30", "rank": 38},
            {"asset_id": "CN:SZ:000729", "stock_name": "燕京啤酒", "trade_date": "2025-01-03", "rank": 1},
        ]
    )
    pass_pool = pd.DataFrame(
        [
            {"asset_id": "CN:SH:603067", "stock_name": "振华股份", "trade_date": "2025-04-30", "rank": 38},
            {"asset_id": "CN:SZ:002028", "stock_name": "思源电气", "trade_date": "2025-01-24", "rank": 13},
        ]
    )

    outputs = build_observation_pool(
        promotion_assets=promotion_assets,
        candidates=candidates,
        pass_pool=pass_pool,
        source_manifest_path=Path("pn_quality_review_ready29/manifest.json"),
        horizons=[120, 250, 500],
    )

    pool = outputs["observation_pool"]
    assert pool["asset_id"].tolist() == ["CN:SH:603067", "CN:SH:603239"]
    assert pool["observation_start_date"].tolist() == ["2025-04-30", "2025-05-16"]
    assert pool["observation_horizons"].tolist() == ["120|250|500", "120|250|500"]
    assert pool.iloc[0]["source_manifest"] == "pn_quality_review_ready29/manifest.json"
    assert pool.iloc[0]["observation_status"] == "active"

    groups = outputs["comparison_groups"]
    assert set(groups["comparison_group"]) == {
        "original_topn_candidates",
        "readiness_pass_pool",
        "quality_promotion_pool",
    }
    counts = outputs["manifest"]["comparison_group_counts"]
    assert counts == {
        "original_topn_candidates": 2,
        "readiness_pass_pool": 2,
        "quality_promotion_pool": 2,
    }


def test_run_observation_pool_from_files_writes_artifacts(tmp_path: Path) -> None:
    promotion_csv = tmp_path / "promotion_assets.csv"
    candidates_csv = tmp_path / "candidates.csv"
    pass_pool_csv = tmp_path / "pass_pool.csv"
    source_manifest = tmp_path / "quality_manifest.json"
    source_manifest.write_text(json.dumps({"inputs": {"product_rows_csv": "strict_product.csv"}}), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "review_priority": "P1_observe",
                "review_action": "add_to_observation_pool",
                "product_family": "chrome_chemicals",
                "evidence_quality_score": 12,
            }
        ]
    ).to_csv(promotion_csv, index=False)
    pd.DataFrame([{"asset_id": "CN:SH:603067", "stock_name": "振华股份", "trade_date": "2025-04-30"}]).to_csv(
        candidates_csv,
        index=False,
    )
    pd.DataFrame([{"asset_id": "CN:SH:603067", "stock_name": "振华股份", "trade_date": "2025-04-30"}]).to_csv(
        pass_pool_csv,
        index=False,
    )

    paths = run_observation_pool_from_files(
        promotion_assets_csv=promotion_csv,
        candidates_csv=candidates_csv,
        pass_pool_csv=pass_pool_csv,
        output_dir=tmp_path / "out",
        source_manifest_path=source_manifest,
        horizons=[120, 250, 500],
    )

    assert paths["observation_pool"].exists()
    assert paths["comparison_groups"].exists()
    assert paths["summary"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["observation_asset_count"] == 1
    assert manifest["inputs"]["source_manifest_path"] == str(source_manifest)
    assert "strict_product.csv" in json.dumps(manifest, ensure_ascii=False)
