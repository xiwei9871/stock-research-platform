from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_dashboard_readonly_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_watchlist_dashboard_readonly.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_dashboard_readonly", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dashboard_summary_json_exists_and_counts_watchlist() -> None:
    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_summary.json").read_text(encoding="utf-8"))

    assert summary["watchlist_count"] == 102
    assert summary["consolidated_report_count"] == 102
    assert summary["lookahead_violation_rows"] == 0
    assert summary["trading_signal_present"] is False
    assert "degraded" in summary["degraded_source_warning"]


def test_dashboard_table_and_cards_have_102_rows_without_execution_fields() -> None:
    module = _load_module()
    table = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_dashboard_table.csv")
    cards = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_cards.json").read_text(encoding="utf-8"))
    forbidden_columns = {
        "target_price",
        "position_size",
        "entry_signal",
        "exit_signal",
        "buy",
        "sell",
        "hold",
    }

    assert len(table) == 102
    assert len(cards) == 102
    assert forbidden_columns.isdisjoint(table.columns)
    assert not module.contains_actionable_trading_language(table.to_csv(index=False))
    assert not module.contains_actionable_trading_language(json.dumps(cards, ensure_ascii=False))


def test_report_links_exist_and_are_clean() -> None:
    links = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_dashboard_report_links.csv")

    assert len(links) == 102
    assert links["report_exists"].astype(bool).all()
    assert links["report_file_size"].gt(0).all()
    assert not links["contains_trading_language"].astype(bool).any()


def test_warnings_include_required_boundary_messages() -> None:
    warnings = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_warnings.json").read_text(encoding="utf-8"))
    warning_ids = {item["warning_id"] for item in warnings}

    assert {
        "not_trading_signal",
        "degraded_source_warning",
        "formal_strategy_file_untracked_warning",
    }.issubset(warning_ids)


def test_filters_and_cards_keep_forward_return_as_post_review_context() -> None:
    module = _load_module()
    filters = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_filters.json").read_text(encoding="utf-8"))
    cards = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_cards.json").read_text(encoding="utf-8"))

    assert "research_priority" in filters
    assert "valuation_context_level" in filters
    assert "baidu_validation_status" in filters
    for card in cards[:10]:
        assert "仅用于事后复盘" in card["forward_return_context"]
        assert "预测" not in card["forward_return_context"]
    assert not module.contains_actionable_trading_language(json.dumps(filters, ensure_ascii=False))


def test_contract_main_report_audit_and_formal_strategy_status() -> None:
    contract = (OUTPUT_DIR / "tech_bottleneck_dashboard_contract.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1.md").read_text(encoding="utf-8")
    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_dashboard_summary.json").read_text(encoding="utf-8"))

    assert "read_only_internal_review: ready" in contract
    assert "production_dashboard: not ready" in contract
    assert "frontend integration deferred" in report
    assert "无法仅靠 `git diff` 完整证明" in report
    assert summary["lookahead_violation_rows"] == 0
