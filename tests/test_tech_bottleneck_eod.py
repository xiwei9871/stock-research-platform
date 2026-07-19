from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from stock_research import tech_bottleneck_eod
from stock_research.strategy_publication_artifacts import ARTIFACT_VERSION
from stock_research.tech_bottleneck_candidates import TECH_BOTTLENECK_CANDIDATE_COLUMNS


def test_tech_bottleneck_uses_versioned_official_writer_and_keeps_candidate_entry(
    tmp_path, monkeypatch
):
    snapshot = {column: "" for column in TECH_BOTTLENECK_CANDIDATE_COLUMNS}
    snapshot.update(
        {
            "trade_date": "2026-07-18",
            "asset_id": "CN:SH:600000",
            "stock_name": "浦发银行",
            "first_hit_date": "2026-01-01",
            "candidate_as_of_date": "2026-07-18",
            "hit_count_as_of_date": 3,
            "financial_as_of_date": "2026-07-18",
            "technical_as_of_date": "2026-07-18",
            "data_as_of_date": "2026-07-18",
            "filter_decision": "pass",
            "bottleneck_rank": 1,
            "bottleneck_score": 0.88,
            "is_top5": True,
            "engine_version": "tech_bottleneck_daily_candidates_v1",
            "run_id": "strategy-eod-2026-07-18-local",
        }
    )
    snapshots = pd.DataFrame([snapshot], columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)
    monkeypatch.setattr(
        tech_bottleneck_eod,
        "build_point_in_time_candidate_snapshots",
        lambda **kwargs: snapshots,
    )
    monkeypatch.setattr(
        tech_bottleneck_eod,
        "build_tech_bottleneck_v1_from_rank_snapshots",
        lambda **kwargs: {
            "summary": {
                "engine_version": "tech_bottleneck_v1",
                "top_n": 5,
                "transaction_cost_bps": 10.0,
                "adjust_type": "hfq",
                "frequency": "biweekly",
                "universe": "strict_153_st_only_financial_state",
                "protection_name": "rank_exit_top10_1d",
            },
            "equity_curve": [{"trade_date": "2026-07-18", "equity": 1.0}],
            "positions": [{"trade_date": "2026-07-18", "asset_id": "CN:SH:600000"}],
            "trades": [],
        },
    )
    entries = []

    result = tech_bottleneck_eod.run_tech_bottleneck_eod_from_frames(
        base_candidates=pd.DataFrame(),
        prices=pd.DataFrame(),
        market_exposure=pd.DataFrame(),
        start_date="2026-01-01",
        end_date="2026-07-18",
        run_id="strategy-eod-2026-07-18-local",
        output_dir=tmp_path,
        manifest_upsert=entries.append,
    )

    assert [entry["module"] for entry in entries] == [
        "tech_bottleneck_candidates",
        "strategy_tech_bottleneck",
    ]
    candidate_entry, strategy_entry = entries
    assert candidate_entry["artifact_path"] == str(tmp_path / "tech_bottleneck_daily_candidates.csv")
    assert strategy_entry["artifact_path"] == result["review_path"]
    assert "/strategy_runs/tech_bottleneck/" in result["review_path"]
    assert result["artifact_version"] == ARTIFACT_VERSION
    assert result["publication_identity"]["strategy_id"] == "tech_bottleneck"
    metadata = strategy_entry["metadata"]
    assert metadata["artifact_version"] == ARTIFACT_VERSION
    assert metadata["publication_identity"] == result["publication_identity"]
    assert metadata["output_paths"]["review_path"] == result["review_path"]
    assert set(metadata["output_paths"]) == {
        "equity_path",
        "positions_path",
        "trades_path",
        "review_path",
        "summary_path",
        "publication_manifest_path",
    }
    assert metadata["publication_manifest_path"].endswith("publication_manifest.json")
    assert (tmp_path / "strategy_tech_bottleneck_review.csv").exists()


def test_tech_strategy_manifest_ends_after_candidate_and_publication(tmp_path, monkeypatch):
    moments = iter(
        [
            datetime(2026, 7, 18, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 18, 2, tzinfo=timezone.utc),
            datetime(2026, 7, 18, 3, tzinfo=timezone.utc),
        ]
    )

    class Clock:
        @classmethod
        def now(cls, tz=None):
            return next(moments)

    monkeypatch.setattr(tech_bottleneck_eod, "datetime", Clock)
    snapshots = pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)
    monkeypatch.setattr(tech_bottleneck_eod, "build_point_in_time_candidate_snapshots", lambda **kwargs: snapshots)
    monkeypatch.setattr(tech_bottleneck_eod, "write_candidate_snapshots", lambda frame, path: path)
    monkeypatch.setattr(
        tech_bottleneck_eod,
        "build_tech_bottleneck_v1_from_rank_snapshots",
        lambda **kwargs: {
            "summary": {
                "engine_version": "tech_bottleneck_v1",
                "top_n": 5,
                "transaction_cost_bps": 10.0,
                "adjust_type": "hfq",
                "frequency": "biweekly",
                "universe": "strict_153_st_only_financial_state",
                "protection_name": "rank_exit_top10_1d",
            },
            "equity_curve": [],
            "positions": [],
            "trades": [],
        },
    )
    monkeypatch.setattr(
        tech_bottleneck_eod,
        "_review_rows_from_snapshots",
        lambda **kwargs: pd.DataFrame(columns=["trade_date", "asset_id"]),
    )
    entries = []

    tech_bottleneck_eod.run_tech_bottleneck_eod_from_frames(
        base_candidates=pd.DataFrame(),
        prices=pd.DataFrame(),
        market_exposure=pd.DataFrame(),
        start_date="2026-01-01",
        end_date="2026-07-18",
        run_id="r1",
        output_dir=tmp_path,
        manifest_upsert=entries.append,
    )

    candidate, strategy = entries
    assert candidate["ended_at"] == "2026-07-18T02:00:00+00:00"
    assert strategy["ended_at"] == "2026-07-18T03:00:00+00:00"
