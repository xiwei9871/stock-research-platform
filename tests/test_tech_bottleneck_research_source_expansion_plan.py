from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_research_source_expansion_plan.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_research_source_expansion_plan", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_source_inventory_contains_required_categories() -> None:
    module = _load_module()
    inventory = module.build_source_inventory(project_root=Path("/tmp/nonexistent"))

    categories = set(inventory["source_category"])

    assert {"broker_report", "news", "announcement", "fundamentals", "valuation"}.issubset(categories)


def test_watchlist_gap_covers_standard_watchlist_assets() -> None:
    module = _load_module()
    index = pd.DataFrame(
        {
            "asset_id": ["A", "B"],
            "symbol": ["A", "B"],
            "name": ["甲", "乙"],
            "source_type_set": ["research_selection_snapshot|broker_report", "research_selection_snapshot"],
            "missing_fields": ["fundamental_recovery_score|valuation_position_score", "fundamental_recovery_score"],
            "human_review_required": [True, True],
        }
    )

    gap = module.build_watchlist_source_gap(index)

    assert gap["asset_id"].nunique() == 2
    assert {"fundamentals", "valuation", "announcement", "news"}.issubset(set(gap["source_category"]))


def test_field_mapping_plan_contains_required_pit_fields() -> None:
    module = _load_module()
    mapping = module.build_source_field_mapping_plan()

    required_targets = {"announcement_date", "as_of_date", "financial_as_of_date", "source_date", "valuation_position_score"}

    assert required_targets.issubset(set(mapping["target_contract_field"]))


def test_priority_roadmap_does_not_recommend_trading_layer_next() -> None:
    module = _load_module()
    roadmap = module.build_source_priority_roadmap()

    joined = " ".join(roadmap["recommended_next_task"].astype(str)).lower()

    assert "trigger" not in joined
    assert "holding" not in joined
    assert "exit" not in joined


def test_pit_checklist_contains_core_asof_rules() -> None:
    module = _load_module()
    text = module.build_pit_checklist_text()

    assert "source_date <= trade_date" in text
    assert "as_of_date <= trade_date" in text
    assert "announcement_date <= trade_date" in text
    assert "financial_as_of_date <= trade_date" in text


def test_report_text_has_no_actionable_trading_language() -> None:
    module = _load_module()
    text = module.render_main_report(
        inventory=pd.DataFrame({"source_category": ["announcement"], "existing_in_project": [True]}),
        gap=pd.DataFrame({"source_category": ["fundamentals"], "gap_severity": ["critical"]}),
        roadmap=module.build_source_priority_roadmap(),
        report_quality=pd.DataFrame({"metric": ["generated_report_count"], "value": [102], "note": [""]}),
        git_info={"repo_root": "/repo", "formal_strategy_status": "?? src/stock_research/tech_bottleneck_v1.py", "formal_strategy_ls_files": "", "formal_strategy_stat": ""},
        scanned_paths=["src/stock_research/news_source_backfill.py"],
    )

    assert not module.contains_actionable_trading_language(text)
