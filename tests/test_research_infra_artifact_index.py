from __future__ import annotations

import json
from pathlib import Path

from stock_research.research_infra.artifact_index import (
    ResearchInfraArtifactIndexRecord,
    append_artifact_index_record,
    export_artifact_index_record,
    read_artifact_index,
)


def _record(run_id: str = "run-1") -> ResearchInfraArtifactIndexRecord:
    return ResearchInfraArtifactIndexRecord(
        run_id=run_id,
        run_type="mid_trend_portfolio_review",
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        created_at="2026-06-04T15:00:00",
        research_infra_dir="outputs/research/research_infra",
        run_card_json_path="outputs/research/research_infra/run_card/run_card.json",
        research_signals_json_path="outputs/research/research_infra/research_signals.json",
        attribution_cards_json_path="outputs/research/research_infra/attribution_cards.json",
        attribution_cards_md_path="outputs/research/research_infra/attribution_cards.md",
        experiment_registry_path="outputs/research/research_infra/experiment_registry.jsonl",
        metrics={"research_signal_count": 6, "attribution_card_count": 1},
        warnings=[],
        caveats=["review-only; no execution instruction"],
    )


def test_append_and_read_artifact_index_record(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "research_infra_index.jsonl"
    append_artifact_index_record(path, _record())

    rows = read_artifact_index(path)

    assert len(rows) == 1
    assert rows[0] == _record()
    raw_line = path.read_text(encoding="utf-8").strip()
    payload = json.loads(raw_line)
    assert payload["run_id"] == "run-1"
    assert payload["metrics"]["research_signal_count"] == 6


def test_append_artifact_index_record_skips_duplicate_run_dir_pair(tmp_path: Path) -> None:
    path = tmp_path / "research_infra_index.jsonl"
    append_artifact_index_record(path, _record())
    append_artifact_index_record(path, _record())

    rows = read_artifact_index(path)

    assert len(rows) == 1
    assert rows[0].run_id == "run-1"


def test_read_artifact_index_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert read_artifact_index(tmp_path / "missing.jsonl") == []


def test_export_artifact_index_record_uses_stable_keys() -> None:
    payload = export_artifact_index_record(_record())

    assert list(payload) == [
        "attribution_cards_json_path",
        "attribution_cards_md_path",
        "caveats",
        "created_at",
        "experiment_registry_path",
        "metrics",
        "research_infra_dir",
        "research_signals_json_path",
        "run_card_json_path",
        "run_id",
        "run_type",
        "strategy_variant",
        "trade_date",
        "warnings",
    ]
