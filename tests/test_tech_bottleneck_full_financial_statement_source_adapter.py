from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_full_financial_statement_source_adapter.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_full_financial_statement_source_adapter_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("full_financial_statement_adapter", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_full_financial_statement_outputs_exist_and_summary_is_valid() -> None:
    expected = {
        "full_financial_statement_summary.json",
        "full_financial_statement_features.csv",
        "full_financial_statement_features.json",
        "full_financial_statement_coverage.csv",
        "full_financial_statement_field_dictionary.csv",
        "full_financial_statement_pit_audit.csv",
        "full_financial_statement_missing_fields.csv",
        "full_financial_statement_source_quality.csv",
        "full_financial_statement_guardrails.json",
        "tech_bottleneck_full_financial_statement_source_adapter_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "full_financial_statement_summary.json").read_text(encoding="utf-8"))
    assert summary["watchlist_count"] == 102
    assert summary["financial_statement_support_count"] >= 0
    assert summary["pit_strong_count"] + summary["missing_count"] == 102
    assert summary["lookahead_violation_rows"] == 0
    assert summary["acceptance_decision"] in {
        "financial_statement_source_adapter_ready",
        "conditionally_ready_with_degraded_pit_dates",
        "blocked_due_to_source_unavailable",
    }


def test_features_have_pit_columns_and_guardrail_flags() -> None:
    features = pd.read_csv(OUTPUT_DIR / "full_financial_statement_features.csv")
    required = {
        "ts_code",
        "stock_code",
        "stock_name",
        "first_admission_date",
        "report_period",
        "announce_date",
        "source",
        "source_table",
        "pit_status",
        "source_quality",
        "used_for_signal",
        "used_for_dashboard",
        "used_for_manual_review",
        "used_for_admission",
        "research_only",
        "revenue",
        "net_profit",
        "operating_cashflow",
        "inventory",
        "accounts_receivable",
        "rd_expense",
        "capex",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "gross_margin",
        "net_margin",
        "roe",
        "roa",
        "asset_liability_ratio",
    }
    assert len(features) == 102
    assert required.issubset(set(features.columns))
    assert set(features["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(features["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert set(features["research_only"].astype(str).str.lower()) == {"true"}
    strong = features[features["pit_status"].eq("pit_strong")]
    assert (
        pd.to_datetime(strong["announce_date"], errors="coerce")
        <= pd.to_datetime(strong["first_admission_date"], errors="coerce")
    ).all()


def test_coverage_missing_fields_and_guardrails_are_explicit() -> None:
    module = _load_module()
    coverage = pd.read_csv(OUTPUT_DIR / "full_financial_statement_coverage.csv")
    missing = pd.read_csv(OUTPUT_DIR / "full_financial_statement_missing_fields.csv")
    pit_audit = pd.read_csv(OUTPUT_DIR / "full_financial_statement_pit_audit.csv")
    guardrails = json.loads((OUTPUT_DIR / "full_financial_statement_guardrails.json").read_text(encoding="utf-8"))
    report = (OUTPUT_DIR / "tech_bottleneck_full_financial_statement_source_adapter_v1_report.md").read_text(
        encoding="utf-8"
    )
    assert {"field_name", "coverage_count", "coverage_ratio", "missing_count"}.issubset(coverage.columns)
    assert {"asset_id", "field_name", "missing_reason", "recommended_follow_up"}.issubset(missing.columns)
    assert len(missing) > 0
    assert int(pit_audit.loc[pit_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) == 0
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["formal_strategy_diff_status"] == "clean"
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
    assert not module.contains_actionable_trading_language(report)
