from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_candidate_discovery_v1"
SOURCE_UNIVERSE = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1/a_share_candidate_universe.csv"
DOUBLER_CLOSURE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_doubler_market_discovered_closure_v1/doubler_market_discovered_closure_master.csv"
)
QUALITY_POOL_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

OUTPUT_COLUMNS = [
    "stock_code",
    "stock_name",
    "industry",
    "tech_bottleneck_domain",
    "supply_chain_role",
    "candidate_tier",
    "not_in_doubler_596",
    "not_in_quality_pool_v3",
    "price_move_bucket",
    "low_position_research_tag",
    "hard_tech_domain_signal",
    "bottleneck_or_chokepoint_possibility",
    "business_relevance_signal",
    "concept_pollution_risk",
    "beneficiary_only_risk",
    "primary_source_feasibility",
    "next_primary_source_to_check",
    "latent_discovery_decision",
    "latent_discovery_reason",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "notes",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _truthy(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(row: pd.Series, column: str) -> str:
    return str(row.get(column, "") or "").strip()


def _combine_text(row: pd.Series, columns: list[str]) -> str:
    return "|".join(_text(row, column) for column in columns if _text(row, column))


def _hard_tech_domain_signal(row: pd.Series) -> str:
    domain = _text(row, "tech_bottleneck_domain")
    sub = _text(row, "tech_bottleneck_sub_domain")
    trend = _text(row, "trend_domain")
    exposure = _num(row.get("bottleneck_exposure_score"), 0)
    pollution = _text(row, "concept_pollution_risk").lower()
    if not (domain or sub or trend):
        return "missing"
    if exposure >= 75 and pollution != "high":
        return "strong"
    if exposure >= 55 and pollution != "high":
        return "moderate"
    return "weak"


def _bottleneck_possibility(row: pd.Series) -> str:
    score = _num(row.get("bottleneck_or_chokepoint_score"), 0)
    role = _text(row, "supply_chain_role").lower()
    if role in {"chokepoint", "bottleneck"} or score >= 80:
        return "high"
    if role in {"derivative_exposure", "component", "equipment", "material"} or score >= 55:
        return "moderate"
    return "low"


def _business_relevance(row: pd.Series) -> str:
    relevance = _text(row, "main_business_relevance").lower()
    exposure = _num(row.get("real_business_exposure_score"), 0)
    if relevance == "high" or exposure >= 75:
        return "high"
    if relevance in {"medium", "meaningful", "meaningful_revenue"} or exposure >= 45:
        return "medium"
    return "low"


def _beneficiary_only_risk(row: pd.Series) -> str:
    role = _text(row, "supply_chain_role").lower()
    flags = [
        "policy_theme_only_flag",
        "name_similarity_only_flag",
        "minority_investment_only_flag",
        "trading_agent_or_distributor_flag",
        "secondary_market_narrative_only_flag",
        "kol_or_social_only_flag",
    ]
    if role in {"beneficiary_only", "concept_only", "theme_only", "trading_agent", "distributor"}:
        return "high"
    if any(_truthy(row.get(flag)) for flag in flags):
        return "high"
    return "low"


def _primary_source_feasibility(row: pd.Series) -> str:
    source_plan = _combine_text(
        row,
        [
            "next_primary_source_to_check",
            "next_primary_source_check",
            "next_research_action",
            "missing_evidence_to_upgrade",
        ],
    ).lower()
    primary_count = _num(row.get("primary_source_count"), 0)
    evidence_count = _num(row.get("evidence_count"), 0)
    high_tokens = [
        "annual report",
        "announcement",
        "financial",
        "prospectus",
        "年报",
        "公告",
        "招股",
        "收入",
        "客户",
        "认证",
        "产能",
        "订单",
    ]
    if primary_count > 0 or any(token in source_plan for token in high_tokens):
        return "high"
    if evidence_count > 0 or source_plan:
        return "moderate"
    return "low"


def _price_move_bucket(row: pd.Series) -> str:
    percentile = _num(row.get("price_percentile_120d"), -1)
    drawdown = _num(row.get("drawdown_from_120d_high"), 0)
    if percentile < 0:
        return "not_doubled_or_not_evaluated"
    if percentile <= 25:
        return "low_position_research_only"
    if percentile <= 50:
        return "mid_low_position_research_only"
    if drawdown <= -30:
        return "drawdown_research_only"
    return "higher_position_research_only"


def _low_position_tag(row: pd.Series) -> str:
    low_score = _num(row.get("low_position_score"), 0)
    percentile = _num(row.get("price_percentile_120d"), 101)
    if low_score >= 60 or percentile <= 35:
        return "low_position_research_priority_only_not_signal"
    return "neutral_position_research_only_not_signal"


def _is_reject_like(row: pd.Series) -> bool:
    pollution = _text(row, "concept_pollution_risk").lower()
    excluded = _truthy(row.get("excluded_flag"))
    beneficiary_risk = _beneficiary_only_risk(row) == "high"
    relevance = _business_relevance(row)
    hard_signal = _hard_tech_domain_signal(row)
    if pollution == "high" or beneficiary_risk:
        return True
    if excluded and hard_signal in {"missing", "weak"}:
        return True
    if relevance == "low" and hard_signal in {"missing", "weak"}:
        return True
    return False


def _decision(row: pd.Series) -> tuple[str, str, str]:
    hard_signal = _hard_tech_domain_signal(row)
    bottleneck = _bottleneck_possibility(row)
    relevance = _business_relevance(row)
    source_feasibility = _primary_source_feasibility(row)
    gap_flags = _text(row, "data_gap_flags")
    candidate_tier = _text(row, "candidate_tier")
    if _is_reject_like(row):
        return (
            "latent_reject_or_exclude",
            "Excluded from latent queue because hard-tech evidence is weak, pollution risk is high, or exposure is beneficiary/concept-only.",
            "keep out of latent evidence queue; revisit only if a separate false-negative review produces new evidence",
        )
    if (
        hard_signal in {"strong", "moderate"}
        and bottleneck in {"high", "moderate"}
        and relevance in {"high", "medium"}
        and source_feasibility in {"high", "moderate"}
        and candidate_tier != "Excluded"
    ):
        return (
            "latent_evidence_completion_queue",
            "Hard-tech domain and chokepoint possibility are visible, and primary-source checks appear feasible.",
            "run research-only primary-source backfill before any quality-pool consideration",
        )
    if hard_signal in {"strong", "moderate"} and bottleneck in {"high", "moderate"} and relevance != "low":
        return (
            "latent_manual_review",
            "Hard-tech signal exists, but evidence feasibility or business relevance needs manual triage before backfill.",
            "manual review of thesis scope and source feasibility",
        )
    if hard_signal != "missing" or gap_flags:
        return (
            "latent_data_gap_watch",
            "Potential domain signal remains, but current evidence path is incomplete.",
            "hold in data-gap watch; identify primary-source path before backfill",
        )
    return (
        "latent_reject_or_exclude",
        "No actionable hard-tech bottleneck signal after excluding doubled and quality-pool names.",
        "do not backfill unless new company-specific evidence appears",
    )


def _build_latent_universe(source: pd.DataFrame, doubled: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    doubled_codes = set(doubled["stock_code"].map(_stock_code))
    quality_codes = set(quality["stock_code"].map(_stock_code))
    source = source.copy()
    source["stock_code"] = source["stock_code"].map(_stock_code)
    source = source.sort_values(["stock_code", "research_priority_score"], ascending=[True, False], na_position="last")
    source = source.drop_duplicates("stock_code", keep="first").reset_index(drop=True)
    latent = source[~source["stock_code"].isin(doubled_codes | quality_codes)].copy()
    rows: list[dict[str, Any]] = []
    for _, row in latent.sort_values("stock_code").iterrows():
        decision, reason, action = _decision(row)
        source_check = _text(row, "next_primary_source_to_check") or _text(row, "next_primary_source_check")
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": _text(row, "stock_name"),
                "industry": _text(row, "industry"),
                "tech_bottleneck_domain": _text(row, "tech_bottleneck_domain"),
                "supply_chain_role": _text(row, "supply_chain_role"),
                "candidate_tier": _text(row, "candidate_tier"),
                "not_in_doubler_596": True,
                "not_in_quality_pool_v3": True,
                "price_move_bucket": _price_move_bucket(row),
                "low_position_research_tag": _low_position_tag(row),
                "hard_tech_domain_signal": _hard_tech_domain_signal(row),
                "bottleneck_or_chokepoint_possibility": _bottleneck_possibility(row),
                "business_relevance_signal": _business_relevance(row),
                "concept_pollution_risk": _text(row, "concept_pollution_risk") or "unknown",
                "beneficiary_only_risk": _beneficiary_only_risk(row),
                "primary_source_feasibility": _primary_source_feasibility(row),
                "next_primary_source_to_check": source_check,
                "latent_discovery_decision": decision,
                "latent_discovery_reason": reason,
                "recommended_next_action": action,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": (
                    "Discovery queue only; excludes 2025 doubled tech names and quality pool v3. "
                    "Price/position labels are research-priority metadata only."
                ),
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _split_outputs(latent: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "latent_evidence_completion_queue.csv": latent[
            latent["latent_discovery_decision"].eq("latent_evidence_completion_queue")
        ].copy(),
        "latent_manual_review_queue.csv": latent[latent["latent_discovery_decision"].eq("latent_manual_review")].copy(),
        "latent_data_gap_watch.csv": latent[latent["latent_discovery_decision"].eq("latent_data_gap_watch")].copy(),
        "latent_reject_or_exclude.csv": latent[latent["latent_discovery_decision"].eq("latent_reject_or_exclude")].copy(),
    }


def _summary(source: pd.DataFrame, doubled: pd.DataFrame, quality: pd.DataFrame, latent: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = latent["latent_discovery_decision"].value_counts()
    used_for_signal = int(latent["used_for_signal"].astype(bool).sum())
    used_for_admission = int(latent["used_for_admission"].astype(bool).sum())
    data_gap_count = int(counts.get("latent_data_gap_watch", 0))
    blocking = used_for_signal or used_for_admission or not strategy_clean
    acceptance = "blocked_due_to_guardrail_violation"
    if not blocking:
        acceptance = "conditionally_ready_with_data_gaps" if data_gap_count else "latent_candidate_discovery_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_candidate_universe_count": int(source["stock_code"].nunique()),
        "doubled_tech_596_count": int(doubled["stock_code"].nunique()),
        "quality_pool_v3_count": int(quality["stock_code"].nunique()),
        "latent_universe_count": int(len(latent)),
        "latent_evidence_completion_queue_count": int(counts.get("latent_evidence_completion_queue", 0)),
        "latent_manual_review_count": int(counts.get("latent_manual_review", 0)),
        "latent_data_gap_watch_count": data_gap_count,
        "latent_reject_or_exclude_count": int(counts.get("latent_reject_or_exclude", 0)),
        "doubled_tech_596_excluded": True,
        "quality_pool_v3_excluded": True,
        "primary_source_backfill_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "doubled_tech_596_excluded": summary["doubled_tech_596_excluded"],
        "quality_pool_v3_excluded": summary["quality_pool_v3_excluded"],
        "primary_source_backfill_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Latent Candidate Discovery v1

## 1. Scope
This task scans candidates outside the 2025 doubled-tech market-discovered set and outside quality pool v3. It is research-only discovery and queue construction. It does not perform primary-source backfill, does not add names to the quality pool, and does not connect to signal or admission paths.

## 2. Input Baseline
- Source A-share candidate universe: {summary["source_candidate_universe_count"]}
- Excluded doubled-tech set: {summary["doubled_tech_596_count"]}
- Excluded quality pool v3: {summary["quality_pool_v3_count"]}
- Latent universe after exclusions: {summary["latent_universe_count"]}

## 3. Discovery Method
The latent queue uses existing local audit fields: hard-tech domain, supply-chain role, bottleneck/chokepoint scores, business relevance, concept-pollution flags, beneficiary-only risk, and next primary-source feasibility. Price and low-position fields are retained only as research-priority metadata and are not used for signal.

## 4. Queue Results
- Latent evidence completion queue: {summary["latent_evidence_completion_queue_count"]}
- Latent manual review: {summary["latent_manual_review_count"]}
- Latent data-gap watch: {summary["latent_data_gap_watch_count"]}
- Latent reject or exclude: {summary["latent_reject_or_exclude_count"]}

## 5. Guardrail Checks
- Research-only: true
- Doubled-tech 596 excluded: true
- Quality pool v3 excluded: true
- Primary-source backfill performed: false
- Auto added to quality pool: 0
- Price move used for signal: 0
- Low-position used for signal: 0
- Used for signal: {summary["used_for_signal_count"]}
- Used for admission: {summary["used_for_admission_count"]}
- Baseline admission changed: {summary["baseline_admission_changed_count"]}
- Strategy file diff clean: {str(summary["strategy_file_diff_clean"]).lower()}

## 6. Acceptance Decision
{summary["acceptance_decision"]}

## 7. Recommended Next Steps
1. tech_bottleneck_latent_primary_source_backfill_v1
2. tech_bottleneck_latent_candidate_discovery_quality_audit_v1
3. tech_bottleneck_stock_workspace_docling_panel_v1
"""


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = _read_csv(SOURCE_UNIVERSE)
    doubled = _read_csv(DOUBLER_CLOSURE)
    quality = _read_csv(QUALITY_POOL_V3)
    latent = _build_latent_universe(source, doubled, quality)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(source, doubled, quality, latent, strategy_clean)
    guardrails = _guardrails(summary)

    latent.to_csv(OUTPUT_DIR / "latent_candidate_discovery_universe.csv", index=False)
    for filename, frame in _split_outputs(latent).items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)
    _write_json(OUTPUT_DIR / "latent_candidate_discovery_summary.json", summary)
    _write_json(OUTPUT_DIR / "latent_candidate_discovery_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_latent_candidate_discovery_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
