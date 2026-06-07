from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_core_tech_top100 import (
    build_baseline_comparison,
    build_weekly_topn_candidates,
    run_core_tech_top100_from_files,
    write_core_tech_top100_artifacts,
)


def test_top100_selection_keeps_top100_per_date_and_marks_top50_boundary() -> None:
    score_rows = pd.DataFrame(
        [
            {
                "asset_id": f"CN:SH:{asset_number:06d}",
                "stock_name": f"样本{asset_number}",
                "trade_date": "2026/06/05",
                "score": 200 - asset_number,
                "factor_note": f"note-{asset_number}",
            }
            for asset_number in range(1, 106)
        ]
    )

    candidates = build_weekly_topn_candidates(score_rows=score_rows, top_n=100)

    assert len(candidates) == 100
    assert candidates["trade_date"].unique().tolist() == ["2026-06-05"]
    assert candidates["rank"].tolist() == list(range(1, 101))
    assert "factor_note" in candidates.columns
    rows = candidates.set_index("rank")
    assert bool(rows.loc[50, "in_top50_baseline"]) is True
    assert bool(rows.loc[51, "in_top50_baseline"]) is False
    assert "CN:SH:000105" not in set(candidates["asset_id"])


def test_top100_selection_normalizes_integer_yyyymmdd_dates_and_ranks_by_date() -> None:
    score_rows = pd.DataFrame(
        [
            {"asset_id": "CN:SH:688002", "stock_name": "低分", "trade_date": 20260605, "score": 10},
            {"asset_id": "CN:SH:688001", "stock_name": "高分", "trade_date": 20260605, "score": 20},
            {"asset_id": "CN:SH:688003", "stock_name": "次日", "trade_date": 20260606, "score": 30},
        ]
    )

    candidates = build_weekly_topn_candidates(score_rows=score_rows, top_n=100)

    assert candidates["trade_date"].tolist() == ["2026-06-05", "2026-06-05", "2026-06-06"]
    assert candidates["asset_id"].tolist() == ["CN:SH:688001", "CN:SH:688002", "CN:SH:688003"]
    assert candidates["rank"].tolist() == [1, 2, 1]


def test_baseline_comparison_reports_new_top100_p1_p2_names_from_ranks_51_100() -> None:
    top100_candidates = pd.DataFrame(
        [
            {"asset_id": "CN:SH:688001", "stock_name": "既有P1", "trade_date": "2026-06-05", "rank": 50},
            {"asset_id": "CN:SH:688051", "stock_name": "新增P1", "trade_date": "2026-06-05", "rank": 51},
            {"asset_id": "CN:SH:688052", "stock_name": "新增P2证据", "trade_date": "2026-06-05", "rank": 52},
            {"asset_id": "CN:SH:688053", "stock_name": "新增P2映射", "trade_date": "2026-06-05", "rank": 53},
            {"asset_id": "CN:SH:688054", "stock_name": "噪声", "trade_date": "2026-06-05", "rank": 54},
        ]
    )
    quality_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "既有P1",
                "trade_date": "2026-06-05",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688051",
                "stock_name": "新增P1",
                "trade_date": "2026-06-05",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688052",
                "stock_name": "新增P2证据",
                "trade_date": "2026-06-05",
                "p3_decision": "needs_more_evidence",
            },
            {
                "asset_id": "CN:SH:688053",
                "stock_name": "新增P2映射",
                "trade_date": "2026-06-05",
                "p3_decision": "needs_product_family_mapping",
            },
            {
                "asset_id": "CN:SH:688054",
                "stock_name": "噪声",
                "trade_date": "2026-06-05",
                "p3_decision": "reject",
            },
        ]
    )
    baseline_promotions = pd.DataFrame(
        [{"asset_id": "CN:SH:688001", "stock_name": "既有P1", "trade_date": "2026-06-05"}]
    )

    outputs = build_baseline_comparison(
        top100_candidates=top100_candidates,
        quality_review=quality_review,
        baseline_promotions=baseline_promotions,
    )

    diff = outputs["top50_vs_top100_diff"]
    assert diff["stock_name"].tolist() == ["新增P1", "新增P2证据", "新增P2映射", "噪声"]
    assert diff["top100_increment_status"].tolist() == [
        "new_p1_auto_promotion",
        "new_p2_research_queue",
        "new_p2_research_queue",
        "new_p3_reject_or_noise",
    ]
    assert outputs["manifest"]["baseline_p1_asset_count"] == 1
    assert outputs["manifest"]["top100_p1_asset_count"] == 2
    assert outputs["manifest"]["top100_p2_asset_count"] == 2
    assert outputs["manifest"]["new_p1_from_rank_51_100"] == 1
    assert outputs["manifest"]["new_p2_from_rank_51_100"] == 2
    assert "- New P1 from ranks 51-100: 1 (新增P1)" in outputs["baseline_comparison_md"]
    assert "- New P2 from ranks 51-100: 2 (新增P2证据, 新增P2映射)" in outputs["baseline_comparison_md"]


def test_rank_51_100_increment_counts_exclude_top50_cohort_and_baseline_assets() -> None:
    top100_candidates = pd.DataFrame(
        [
            {"asset_id": "CN:SH:688040", "stock_name": "A", "trade_date": "2026-06-05", "rank": 40},
            {"asset_id": "CN:SH:688040", "stock_name": "A", "trade_date": "2026-06-12", "rank": 70},
            {"asset_id": "CN:SH:688075", "stock_name": "B", "trade_date": "2026-06-12", "rank": 75},
            {"asset_id": "CN:SH:688080", "stock_name": "基线", "trade_date": "2026-06-12", "rank": 80},
        ]
    )
    quality_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688040",
                "stock_name": "A",
                "trade_date": "2026-06-12",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688075",
                "stock_name": "B",
                "trade_date": "2026-06-12",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688080",
                "stock_name": "基线",
                "trade_date": "2026-06-12",
                "p3_decision": "auto_approve",
            },
        ]
    )
    baseline_promotions = pd.DataFrame(
        [{"asset_id": "CN:SH:688080", "stock_name": "基线", "trade_date": "2026-06-05"}]
    )

    outputs = build_baseline_comparison(
        top100_candidates=top100_candidates,
        quality_review=quality_review,
        baseline_promotions=baseline_promotions,
    )

    diff = outputs["top50_vs_top100_diff"].set_index("asset_id")
    assert diff.loc["CN:SH:688040", "top100_increment_status"] == "existing_top50_or_baseline_asset"
    assert diff.loc["CN:SH:688075", "top100_increment_status"] == "new_p1_auto_promotion"
    assert diff.loc["CN:SH:688080", "top100_increment_status"] == "existing_top50_or_baseline_asset"
    assert outputs["manifest"]["new_p1_from_rank_51_100"] == 1
    assert outputs["manifest"]["new_p2_from_rank_51_100"] == 0
    assert "- New P1 from ranks 51-100: 1 (B)" in outputs["baseline_comparison_md"]


def test_file_runner_writes_artifacts_and_manifest_counts(tmp_path: Path) -> None:
    scores_csv = tmp_path / "scores.csv"
    quality_review_csv = tmp_path / "quality_review.csv"
    baseline_promotions_csv = tmp_path / "baseline_promotions.csv"
    output_dir = tmp_path / "out"

    score_rows = [
        {"asset_id": "CN:SH:688001", "stock_name": "既有P1", "trade_date": "2026-06-05", "score": 100}
    ]
    score_rows.extend(
        {
            "asset_id": f"CN:SH:60{asset_number:04d}",
            "stock_name": f"填充{asset_number}",
            "trade_date": "2026-06-05",
            "score": 100 - asset_number,
        }
        for asset_number in range(2, 51)
    )
    score_rows.extend(
        [
            {"asset_id": "CN:SH:688051", "stock_name": "新增P1", "trade_date": "2026-06-05", "score": 49},
            {"asset_id": "CN:SH:688052", "stock_name": "新增P2", "trade_date": "2026-06-05", "score": 48},
        ]
    )
    pd.DataFrame(score_rows).to_csv(scores_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "既有P1",
                "trade_date": "2026-06-05",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688051",
                "stock_name": "新增P1",
                "trade_date": "2026-06-05",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "CN:SH:688052",
                "stock_name": "新增P2",
                "trade_date": "2026-06-05",
                "p3_decision": "needs_more_evidence",
            },
        ]
    ).to_csv(quality_review_csv, index=False)
    pd.DataFrame(
        [{"asset_id": "CN:SH:688001", "stock_name": "既有P1", "trade_date": "2026-06-05"}]
    ).to_csv(baseline_promotions_csv, index=False)

    paths = run_core_tech_top100_from_files(
        scores_csv=scores_csv,
        quality_review_csv=quality_review_csv,
        baseline_promotions_csv=baseline_promotions_csv,
        output_dir=output_dir,
        top_n=52,
    )

    assert paths == {
        "candidates_top100": output_dir / "candidates_top100.csv",
        "top50_vs_top100_diff": output_dir / "top50_vs_top100_diff.csv",
        "baseline_comparison": output_dir / "baseline_comparison.md",
        "manifest": output_dir / "manifest.json",
    }
    for path in paths.values():
        assert path.exists()

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["top100_candidate_count"] == 52
    assert manifest["top100_asset_count"] == 52
    assert manifest["baseline_p1_asset_count"] == 1
    assert manifest["top100_p1_asset_count"] == 2
    assert manifest["top100_p2_asset_count"] == 1
    assert manifest["new_p1_from_rank_51_100"] == 1
    assert manifest["new_p2_from_rank_51_100"] == 1
    assert "Top50 baseline P1 count: 1" in paths["baseline_comparison"].read_text(encoding="utf-8")


def test_artifact_writer_accepts_planned_keyword_only_api(tmp_path: Path) -> None:
    candidates_top100 = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688051",
                "stock_name": "新增P1",
                "trade_date": "2026-06-05",
                "rank": 51,
                "in_top50_baseline": False,
                "p3_decision": "auto_approve",
                "top100_increment_status": "new_p1_auto_promotion",
            }
        ]
    )
    comparison = {
        "top50_vs_top100_diff": candidates_top100.copy(),
        "baseline_comparison_md": "# Custom Comparison\n",
        "manifest": {"top100_candidate_count": 1},
    }
    inputs = {"scores_csv": "scores.csv", "top_n": 100}

    paths = write_core_tech_top100_artifacts(
        candidates_top100=candidates_top100,
        comparison=comparison,
        output_dir=tmp_path,
        inputs=inputs,
    )

    assert pd.read_csv(paths["candidates_top100"])["asset_id"].tolist() == ["CN:SH:688051"]
    assert pd.read_csv(paths["top50_vs_top100_diff"])["top100_increment_status"].tolist() == [
        "new_p1_auto_promotion"
    ]
    assert paths["baseline_comparison"].read_text(encoding="utf-8") == "# Custom Comparison\n"
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["inputs"] == inputs
    assert manifest["files"]["candidates_top100"] == "candidates_top100.csv"
