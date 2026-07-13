from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_enriched_research_selection_quality_validation_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_enriched_research_selection_quality_validation.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_enriched_research_selection_quality_validation", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_variant_definitions_include_baseline_source_and_combined_variants() -> None:
    definitions = pd.read_csv(OUTPUT_DIR / "enriched_selection_variant_definitions.csv")
    variants = set(definitions["variant_name"])

    assert "baseline_standard_watchlist" in variants
    assert "announcement_supported" in variants
    assert "fundamental_supported" in variants
    assert "baostock_valuation_supported" in variants
    assert "fully_enriched_supported" in variants
    assert "high_quality_review_candidates" in variants
    assert definitions["research_use_only"].astype(bool).all()
    assert not definitions["used_for_signal"].astype(bool).any()
    assert not definitions["required_conditions"].str.contains("forward_return", na=False).any()


def test_candidate_events_are_research_only_and_have_ex_post_warning() -> None:
    events = pd.read_csv(OUTPUT_DIR / "enriched_selection_candidate_events.csv")

    assert not events.empty
    assert not events["used_for_signal"].astype(bool).any()
    assert "ex_post_quality_grouping" in set(events["validation_mode"])
    assert events["ex_post_grouping_warning"].str.contains("ex-post", case=False, na=False).any()


def test_forward_return_uses_only_required_horizons_and_is_not_signal_input() -> None:
    forward = pd.read_csv(OUTPUT_DIR / "enriched_selection_forward_return_30_60_90_120.csv")

    assert set(forward["horizon"]).issubset({"30d", "60d", "90d", "120d"})
    assert {"30d", "60d", "90d", "120d"}.issubset(set(forward["horizon"]))
    assert not forward["used_for_signal"].astype(bool).any()


def test_source_ablation_is_conservative_and_has_no_trading_language() -> None:
    module = _load_module()
    ablation = pd.read_csv(OUTPUT_DIR / "enriched_selection_source_ablation_summary.csv")

    assert not ablation.empty
    assert ablation["interpretation"].str.contains("ex-post", case=False, na=False).any()
    assert not module.contains_actionable_trading_language(ablation.to_csv(index=False))


def test_small_sample_variants_are_marked_and_audit_is_clean() -> None:
    summary = pd.read_csv(OUTPUT_DIR / "enriched_selection_variant_summary.csv")
    audit = pd.read_csv(OUTPUT_DIR / "enriched_selection_quality_audit.csv")
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert summary["sample_quality_warning"].isin(["sample_too_small", "not_enough_to_conclude"]).any()
    assert int(lookup["lookahead violation rows"]) == 0
    assert int(lookup["trading language hit count"]) == 0
    assert str(lookup["ex_post_grouping_warning"]).lower() in {"true", "1"}


def test_outputs_have_no_trading_language_and_report_mentions_strategy_status() -> None:
    module = _load_module()
    report = (OUTPUT_DIR / "enriched_research_selection_quality_validation_v1.md").read_text(encoding="utf-8")

    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
    assert "无法仅靠 `git diff` 完整证明" in report
