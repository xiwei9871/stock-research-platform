from __future__ import annotations

from pathlib import Path

import pytest

from stock_research.research_infra.experiment_registry import (
    DuplicateExperimentError,
    ExperimentRecord,
    ExperimentRegistryValidationError,
    append_experiment_record,
    read_experiment_registry,
)


def test_experiment_registry_round_trips_jsonl_record(tmp_path: Path) -> None:
    registry_path = tmp_path / "experiment_registry.jsonl"
    record = ExperimentRecord(
        experiment_id="mid-trend-drawdown-control-2026-06-06",
        created_at="2026-06-06T09:30:00",
        objective="Validate drawdown-control review signal for mid-trend candidates.",
        hypothesis="Candidates with fresh research support recover better after short drawdowns.",
        sample_window={"start_date": "2026-05-01", "end_date": "2026-06-06"},
        universe={"name": "mid_trend_watchlist", "asset_count": 20},
        feature_set_id="feature-set:mid-trend-research-v1",
        label_id="label:entry-success-20d",
        model_or_rule_version="mid_trend_review_v1",
        constraints={"review_only": True, "max_turnover": "n/a"},
        artifact_paths={
            "run_card": "reports/run_card/mid_trend/run_card.json",
            "review": "outputs/research/mid_trend_review.md",
        },
        conclusion="Keep as monitor-only until wider sample confirms stability.",
        reuse_status="monitor_only",
    )

    append_experiment_record(registry_path, record)

    records = read_experiment_registry(registry_path)
    assert records == [record]
    assert registry_path.read_text(encoding="utf-8").count("\n") == 1


def test_experiment_registry_rejects_invalid_reuse_status() -> None:
    with pytest.raises(ExperimentRegistryValidationError) as exc:
        ExperimentRecord(
            experiment_id="bad-status",
            created_at="2026-06-06T09:30:00",
            objective="Validate status handling.",
            hypothesis="Invalid statuses should fail before writing.",
            sample_window={"start_date": "2026-06-01", "end_date": "2026-06-06"},
            universe={"name": "topn", "asset_count": 10},
            feature_set_id="feature-set:topn-v1",
            label_id="label:future-return-5d",
            model_or_rule_version="rules_v1",
            constraints={},
            artifact_paths={"run_card": "reports/run_card/topn/run_card.json"},
            conclusion="Invalid.",
            reuse_status="production_ready",
        )

    assert "reuse_status" in str(exc.value)
    assert "production_ready" in str(exc.value)


def test_experiment_registry_detects_duplicate_experiment_id(tmp_path: Path) -> None:
    registry_path = tmp_path / "experiment_registry.jsonl"
    record = ExperimentRecord(
        experiment_id="duplicate-id",
        created_at="2026-06-06T09:30:00",
        objective="Validate duplicate detection.",
        hypothesis="Duplicate experiment ids should fail.",
        sample_window={"start_date": "2026-06-01", "end_date": "2026-06-06"},
        universe={"name": "topn", "asset_count": 10},
        feature_set_id="feature-set:topn-v1",
        label_id="label:future-return-5d",
        model_or_rule_version="rules_v1",
        constraints={},
        artifact_paths={"run_card": "reports/run_card/topn/run_card.json"},
        conclusion="Duplicate fixture.",
        reuse_status="draft",
    )
    append_experiment_record(registry_path, record)
    append_experiment_record(registry_path, record)

    with pytest.raises(DuplicateExperimentError) as exc:
        read_experiment_registry(registry_path)

    assert "duplicate-id" in str(exc.value)
