#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_candidates import build_point_in_time_candidate_snapshots
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_CANDIDATES_PATH,
    TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH,
    _extend_market_exposure,
    _load_prices,
    build_tech_bottleneck_v1_from_rank_snapshots,
)


PIT_FIELDS = [
    "revenue_exposure_bucket",
    "customer_certification_stage",
    "supplier_concentration_type",
]
PRIMARY_SOURCE_TYPES = {
    "akshare_mainbiz",
    "annual_report",
    "company_announcement",
    "investor_qa",
    "broker_report",
    "research_report",
    "news",
    "structured_report_extract",
}
EVIDENCE_MULTIPLIER_RULE_VERSION = "neutral_missing_v1"
DEFAULT_MIN_VALID_EVIDENCE_COVERAGE = 0.01


def _evidence_state_for_count(count: int) -> str:
    if count >= 3:
        return "E3_strong"
    if count == 2:
        return "E2_valid"
    if count == 1:
        return "E1_weak"
    return "unverified"


def _multiplier_for_count(count: int) -> float:
    if count >= 3:
        return 1.15
    if count == 2:
        return 1.05
    if count == 1:
        return 1.0
    return 1.0


def _finalize_evidence_audit_status(
    frame: pd.DataFrame,
    *,
    evidence_seed: pd.DataFrame,
    min_valid_evidence_coverage: float,
) -> pd.DataFrame:
    result = frame.copy()
    result["bucket_rule_version"] = EVIDENCE_MULTIPLIER_RULE_VERSION
    result["evidence_coverage_ratio"] = (
        float((pd.to_numeric(result["source_backed_field_count"], errors="coerce").fillna(0) > 0).mean())
        if not result.empty
        else 0.0
    )
    if evidence_seed.empty:
        result["evidence_confidence_multiplier"] = 1.0
        result["evidence_state"] = "unverified"
        result["evidence_audit_status"] = "degraded_no_pit_evidence"
        return result
    if float(result["evidence_coverage_ratio"].iloc[0] if not result.empty else 0.0) < min_valid_evidence_coverage:
        result["evidence_confidence_multiplier"] = 1.0
        result["evidence_state"] = "unverified"
        result["evidence_audit_status"] = "degraded_low_pit_evidence_coverage"
        return result
    result["evidence_audit_status"] = "active_pit_evidence"
    return result


def _load_base_source(path: Path, *, end_date: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False).copy()
    frame["candidate_trade_date"] = frame.get("candidate_trade_date", frame["first_hit_date"])
    frame["filter_decision"] = "pass"
    if "fundamental_trade_date" in frame.columns:
        fundamental_dates = pd.to_datetime(frame["fundamental_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        frame["financial_as_of_date"] = fundamental_dates.fillna(frame["first_hit_date"].astype(str))
    else:
        frame["financial_as_of_date"] = frame["first_hit_date"]
    if "technical_as_of_date" not in frame.columns:
        frame["technical_as_of_date"] = frame["first_hit_date"]
    frame["source_latest_trade_date"] = end_date
    frame["data_as_of_date"] = end_date
    frame["generated_trade_date"] = end_date
    frame["candidate_source_mode"] = "legacy_static_seed_daily_pit_research_replay"
    return frame


def _normalize_evidence_seed(path: Path) -> pd.DataFrame:
    seed = pd.read_csv(path, low_memory=False).copy()
    for column in ["asset_id", "field", "source_type", "source_date", "supports_value", "evidence_tier"]:
        if column not in seed.columns:
            seed[column] = ""
    seed["asset_id"] = seed["asset_id"].fillna("").astype(str)
    seed["field"] = seed["field"].fillna("").astype(str).replace(
        {"supplier_concentration_evidence": "supplier_concentration_type"}
    )
    seed["source_type"] = seed["source_type"].fillna("").astype(str).str.lower()
    seed["source_date"] = pd.to_datetime(seed["source_date"].astype(str).str[:10], errors="coerce").dt.strftime("%Y-%m-%d")
    seed = seed[
        seed["asset_id"].ne("")
        & seed["field"].isin(PIT_FIELDS)
        & seed["source_date"].notna()
        & seed["source_type"].isin(PRIMARY_SOURCE_TYPES)
    ].copy()
    return seed.drop_duplicates(subset=["asset_id", "field", "source_date", "source_type", "source_path"], keep="first")


def _build_pit_multiplier(
    *,
    base_snapshots: pd.DataFrame,
    evidence_seed: pd.DataFrame,
    output_path: Path,
    min_valid_evidence_coverage: float = DEFAULT_MIN_VALID_EVIDENCE_COVERAGE,
) -> pd.DataFrame:
    assets = base_snapshots[["trade_date", "asset_id"]].drop_duplicates().copy()
    if evidence_seed.empty:
        assets["source_backed_field_count"] = 0
        assets["artifact_only_or_missing_field_count"] = len(PIT_FIELDS)
        assets["evidence_confidence_multiplier"] = 1.0
        assets["latest_evidence_date"] = ""
        assets["has_revenue_evidence"] = False
        assets["has_customer_evidence"] = False
        assets["has_supplier_evidence"] = False
        assets = _finalize_evidence_audit_status(
            assets,
            evidence_seed=evidence_seed,
            min_valid_evidence_coverage=min_valid_evidence_coverage,
        )
        assets.to_csv(output_path, index=False)
        return assets

    rows: list[dict[str, Any]] = []
    seed_by_asset = {asset: group.copy() for asset, group in evidence_seed.groupby("asset_id", sort=False)}
    for asset_id, dates in assets.groupby("asset_id", sort=False):
        ev = seed_by_asset.get(str(asset_id))
        for trade_date in dates["trade_date"].astype(str).tolist():
            if ev is None or ev.empty:
                fields: set[str] = set()
                latest = ""
            else:
                available = ev[ev["source_date"].astype(str).le(trade_date)]
                fields = set(available["field"].dropna().astype(str).tolist())
                latest = str(available["source_date"].max()) if not available.empty else ""
            count = len(fields)
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "source_backed_field_count": count,
                    "artifact_only_or_missing_field_count": max(0, 3 - count),
                    "evidence_confidence_multiplier": _multiplier_for_count(count),
                    "evidence_state": _evidence_state_for_count(count),
                    "latest_evidence_date": latest,
                    "has_revenue_evidence": "revenue_exposure_bucket" in fields,
                    "has_customer_evidence": "customer_certification_stage" in fields,
                    "has_supplier_evidence": "supplier_concentration_type" in fields,
                }
            )
    result = _finalize_evidence_audit_status(
        pd.DataFrame(rows),
        evidence_seed=evidence_seed,
        min_valid_evidence_coverage=min_valid_evidence_coverage,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def _apply_multiplier(
    *,
    base_snapshots: pd.DataFrame,
    pit_multiplier: pd.DataFrame,
    run_id: str,
    output_path: Path,
) -> pd.DataFrame:
    multiplier_columns = [
        column
        for column in [
            "trade_date",
            "asset_id",
            "evidence_confidence_multiplier",
            "source_backed_field_count",
            "evidence_state",
            "evidence_audit_status",
            "evidence_coverage_ratio",
            "bucket_rule_version",
        ]
        if column in pit_multiplier.columns
    ]
    frame = base_snapshots.merge(
        pit_multiplier[multiplier_columns],
        on=["trade_date", "asset_id"],
        how="left",
    )
    frame["evidence_confidence_multiplier"] = pd.to_numeric(
        frame["evidence_confidence_multiplier"], errors="coerce"
    ).fillna(1.0)
    frame["source_backed_field_count"] = pd.to_numeric(frame["source_backed_field_count"], errors="coerce").fillna(0)
    if "evidence_state" not in frame.columns:
        frame["evidence_state"] = "unverified"
    if "evidence_audit_status" not in frame.columns:
        frame["evidence_audit_status"] = "unavailable"
    if "bucket_rule_version" not in frame.columns:
        frame["bucket_rule_version"] = EVIDENCE_MULTIPLIER_RULE_VERSION
    frame["raw_bottleneck_score"] = frame["bottleneck_score"]
    frame["bottleneck_score"] = frame["bottleneck_score"] * frame["evidence_confidence_multiplier"]
    frame["run_id"] = run_id
    frame = frame.sort_values(
        ["trade_date", "bottleneck_score", "hit_count_as_of_date", "asset_id"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    frame["bottleneck_rank"] = frame.groupby("trade_date").cumcount() + 1
    frame["is_top5"] = frame["bottleneck_rank"] <= 5
    columns = [
        "trade_date",
        "asset_id",
        "stock_name",
        "first_hit_date",
        "candidate_as_of_date",
        "hit_count_as_of_date",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
        "financial_as_of_date",
        "technical_as_of_date",
        "data_as_of_date",
        "filter_decision",
        "filter_reason",
        "bottleneck_score",
        "bottleneck_rank",
        "is_top5",
        "engine_version",
        "run_id",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path.with_name(output_path.stem + "_diagnostic.csv"), index=False)
    frame[columns].to_csv(output_path, index=False)
    return frame[columns]


def _run_strategy(
    *,
    name: str,
    snapshots: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    output_dir: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    strategy = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=snapshots,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
        rebalance_frequency="biweekly",
        transaction_cost_bps=20.0,
        max_position_weight=0.2,
        adjust_type="hfq",
    )
    directory = output_dir / name
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(strategy["equity_curve"]).to_csv(directory / "strategy_tech_bottleneck_equity.csv", index=False)
    pd.DataFrame(strategy["positions"]).to_csv(directory / "strategy_tech_bottleneck_positions.csv", index=False)
    pd.DataFrame(strategy["trades"]).to_csv(directory / "strategy_tech_bottleneck_trades.csv", index=False)
    pd.DataFrame([strategy["summary"]]).to_csv(directory / "summary.csv", index=False)
    row = dict(strategy["summary"])
    row["variant"] = name
    row["trade_rows"] = len(strategy["trades"])
    row["position_rows"] = len(strategy["positions"])
    return row


def _top5_change(old: pd.DataFrame, new: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    old_sets = (
        old[old["bottleneck_rank"].le(5)]
        .groupby("trade_date")["asset_id"]
        .apply(lambda values: "|".join(sorted(values.astype(str))))
        .rename("old_top5")
    )
    new_sets = (
        new[new["bottleneck_rank"].le(5)]
        .groupby("trade_date")["asset_id"]
        .apply(lambda values: "|".join(sorted(values.astype(str))))
        .rename("new_top5")
    )
    frame = pd.concat([old_sets, new_sets], axis=1).reset_index()
    frame["top5_changed"] = frame["old_top5"] != frame["new_top5"]
    frame.to_csv(output_path, index=False)
    return frame


def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_source = _load_base_source(Path(args.base_candidates_path), end_date=args.end_date)
    base_source.to_csv(output_dir / "base_candidate_source_replay.csv", index=False)
    asset_ids = sorted(base_source["asset_id"].dropna().astype(str).unique())
    prices = _load_prices(
        start_date=args.start_date,
        end_date=args.end_date,
        adjust_type="hfq",
        asset_ids=asset_ids,
        service=SETTINGS.research_service,
    )
    # Use first day with both price and candidate coverage.
    base_snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=base_source,
        prices=prices,
        start_date=args.start_date,
        end_date=args.end_date,
        run_id="tech-bottleneck-official-baseline-static-seed",
    )
    replay_start = str(base_snapshots["trade_date"].min())
    prices = prices[prices["trade_date"].astype(str).between(replay_start, args.end_date)].copy()
    market_exposure = pd.read_csv(args.market_exposure_path, low_memory=False)
    market_exposure = _extend_market_exposure(market_exposure, end_date=args.end_date)
    base_snapshots.to_csv(output_dir / "official_baseline_daily_candidate_snapshots.csv", index=False)

    old_seed = _normalize_evidence_seed(Path(args.old_evidence_seed_path))
    new_seed = _normalize_evidence_seed(Path(args.new_evidence_seed_path))
    old_seed.to_csv(output_dir / "old_evidence_seed_pit_usable.csv", index=False)
    new_seed.to_csv(output_dir / "new_evidence_seed_pit_usable.csv", index=False)

    old_pit = _build_pit_multiplier(
        base_snapshots=base_snapshots,
        evidence_seed=old_seed,
        output_path=output_dir / "old_pit_daily_evidence_multiplier.csv",
        min_valid_evidence_coverage=args.min_valid_evidence_coverage,
    )
    new_pit = _build_pit_multiplier(
        base_snapshots=base_snapshots,
        evidence_seed=new_seed,
        output_path=output_dir / "pit_daily_evidence_multiplier.csv",
        min_valid_evidence_coverage=args.min_valid_evidence_coverage,
    )
    old_adjusted = _apply_multiplier(
        base_snapshots=base_snapshots,
        pit_multiplier=old_pit,
        run_id="tech-bottleneck-pit-old-evidence-replay",
        output_path=output_dir / "old_pit_evidence_adjusted_daily_candidate_snapshots.csv",
    )
    new_adjusted = _apply_multiplier(
        base_snapshots=base_snapshots,
        pit_multiplier=new_pit,
        run_id="tech-bottleneck-pit-new-evidence-replay",
        output_path=output_dir / "pit_evidence_adjusted_daily_candidate_snapshots.csv",
    )

    rows = [
        _run_strategy(
            name="official_v1_baseline_static_seed",
            snapshots=base_snapshots,
            prices=prices,
            market_exposure=market_exposure,
            output_dir=output_dir,
            start_date=replay_start,
            end_date=args.end_date,
        ),
        _run_strategy(
            name="pit_replay_old_evidence",
            snapshots=old_adjusted,
            prices=prices,
            market_exposure=market_exposure,
            output_dir=output_dir,
            start_date=replay_start,
            end_date=args.end_date,
        ),
        _run_strategy(
            name="pit_replay_after_new_reports",
            snapshots=new_adjusted,
            prices=prices,
            market_exposure=market_exposure,
            output_dir=output_dir,
            start_date=replay_start,
            end_date=args.end_date,
        ),
    ]
    comparison = pd.DataFrame(rows)
    comparison["requested_start_date"] = args.start_date
    comparison["actual_replay_start_date"] = replay_start
    comparison["end_date"] = args.end_date
    comparison.to_csv(output_dir / "baseline_vs_pit_evidence_replay.csv", index=False)

    change = _top5_change(old_adjusted, new_adjusted, output_dir / "pit_top5_change_old_vs_new_by_trade_date.csv")
    audit = new_pit.copy()
    audit["lookahead_violation"] = (
        audit["latest_evidence_date"].fillna("").astype(str).ne("")
        & (audit["latest_evidence_date"].astype(str) > audit["trade_date"].astype(str))
    )
    audit_summary = pd.DataFrame(
        [
            {"metric": "pit_multiplier_rows", "value": len(new_pit)},
            {"metric": "old_pit_usable_evidence_rows", "value": len(old_seed)},
            {"metric": "new_pit_usable_evidence_rows", "value": len(new_seed)},
            {
                "metric": "old_pit_evidence_coverage_ratio",
                "value": float(old_pit["evidence_coverage_ratio"].iloc[0]) if not old_pit.empty else 0.0,
            },
            {
                "metric": "new_pit_evidence_coverage_ratio",
                "value": float(new_pit["evidence_coverage_ratio"].iloc[0]) if not new_pit.empty else 0.0,
            },
            {
                "metric": "old_evidence_audit_status",
                "value": str(old_pit["evidence_audit_status"].iloc[0]) if not old_pit.empty else "unavailable",
            },
            {
                "metric": "new_evidence_audit_status",
                "value": str(new_pit["evidence_audit_status"].iloc[0]) if not new_pit.empty else "unavailable",
            },
            {"metric": "evidence_multiplier_rule_version", "value": EVIDENCE_MULTIPLIER_RULE_VERSION},
            {"metric": "min_valid_evidence_coverage", "value": float(args.min_valid_evidence_coverage)},
            {"metric": "lookahead_violation_rows", "value": int(audit["lookahead_violation"].sum())},
            {"metric": "top5_changed_days_old_vs_new", "value": int(change["top5_changed"].sum())},
            {"metric": "trade_days", "value": len(change)},
        ]
    )
    audit_summary.to_csv(output_dir / "pit_evidence_no_lookahead_audit.csv", index=False)

    old_row = comparison[comparison["variant"].eq("pit_replay_old_evidence")].iloc[0]
    new_row = comparison[comparison["variant"].eq("pit_replay_after_new_reports")].iloc[0]
    total_delta = float(new_row.get("total_return", 0.0)) - float(old_row.get("total_return", 0.0))
    dd_delta = float(new_row.get("max_drawdown", 0.0)) - float(old_row.get("max_drawdown", 0.0))
    lines = [
        "# Tech Bottleneck PIT Evidence Replay",
        "",
        f"Requested window: {args.start_date} to {args.end_date}",
        f"Actual replay start: {replay_start}",
        "",
        "## No-Lookahead Control",
        "- Evidence rows are usable only when `source_date <= trade_date`.",
        f"- Evidence multiplier rule version: `{EVIDENCE_MULTIPLIER_RULE_VERSION}`.",
        f"- Minimum active evidence coverage: {float(args.min_valid_evidence_coverage):.4f}.",
        f"- Lookahead violation rows: {int(audit['lookahead_violation'].sum())}",
        f"- New PIT usable evidence rows: {len(new_seed)}",
        f"- Old PIT evidence coverage ratio: {float(old_pit['evidence_coverage_ratio'].iloc[0]) if not old_pit.empty else 0.0:.6f}",
        f"- New PIT evidence coverage ratio: {float(new_pit['evidence_coverage_ratio'].iloc[0]) if not new_pit.empty else 0.0:.6f}",
        f"- Old evidence audit status: {str(old_pit['evidence_audit_status'].iloc[0]) if not old_pit.empty else 'unavailable'}",
        f"- New evidence audit status: {str(new_pit['evidence_audit_status'].iloc[0]) if not new_pit.empty else 'unavailable'}",
        "",
        "## Baseline vs PIT Replay",
        comparison.to_markdown(index=False),
        "",
        "## Old vs New PIT Evidence",
        f"- New minus old PIT total_return: {total_delta}",
        f"- New minus old PIT max_drawdown: {dd_delta}",
        f"- Top5 changed days: {int(change['top5_changed'].sum())} / {len(change)}",
        "",
        "## Interpretation",
        "- This is a research-only PIT replay, not a trading-rule change.",
        "- Missing or invalid PIT evidence is neutralized to multiplier `1.0` and flagged instead of being punished as `0.6`.",
        "- If PIT new evidence improves total_return versus PIT old evidence without worse drawdown, evidence timing is potentially useful.",
        "- If it underperforms, report evidence should remain a review/attribution input until interaction rules are identified.",
    ]
    (output_dir / "final_interpretation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output_dir)
    print(comparison.to_string(index=False))
    print(audit_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run research-only Tech Bottleneck PIT evidence replay.")
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default="2026-06-29")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-candidates-path", default=str(TECH_BOTTLENECK_V1_CANDIDATES_PATH))
    parser.add_argument("--market-exposure-path", default=str(TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH))
    parser.add_argument(
        "--old-evidence-seed-path",
        default="outputs/research/tech_bottleneck_source_backed_refresh_20260619/serenity_source_backed_evidence_long.csv",
    )
    parser.add_argument(
        "--new-evidence-seed-path",
        default="outputs/research/tech_bottleneck_report_refresh_replay_20250101_20260629/combined_source_backed_evidence_seed.csv",
    )
    parser.add_argument(
        "--min-valid-evidence-coverage",
        type=float,
        default=DEFAULT_MIN_VALID_EVIDENCE_COVERAGE,
        help="Neutralize PIT evidence multipliers when positive PIT evidence coverage is below this ratio.",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
