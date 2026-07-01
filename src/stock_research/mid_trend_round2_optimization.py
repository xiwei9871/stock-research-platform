from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "research" / "mid_trend_round2"
DEFAULT_CURRENT_VARIANT_OUTPUT_DIR = (
    REPO_ROOT / "outputs" / "research" / "current_mid_trend_strategy_v1_20250101_20260612_retest"
)
DEFAULT_REPLAY_AUDIT_PATH = (
    REPO_ROOT
    / "outputs"
    / "research"
    / "mid_trend_validation_full_20250624"
    / "current_mid_trend_strategy_v1"
    / "replay_audit"
    / "trade_audit_detail.csv"
)


@dataclass(frozen=True)
class MidTrendRound2Config:
    primary_goal: str = "hold_winners_longer"
    secondary_goal: str = "reduce_low_value_turnover"
    hard_constraints: tuple[str, ...] = (
        "max_drawdown",
        "monthly_win_rate",
        "return_drawdown_ratio",
    )


DEFAULT_MID_TREND_ROUND2_CONFIG = MidTrendRound2Config()


def build_mid_trend_round2_baseline_artifacts(
    *,
    start_date: str,
    train_end_date: str,
    end_date: str,
    output_dir: str | Path,
    baseline_payload: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    train_summary = baseline_payload["train_summary"].copy()
    train_summary["split_name"] = "train"
    test_summary = baseline_payload["test_summary"].copy()
    test_summary["split_name"] = "test"

    train_path = output / "mid_trend_round2_baseline_train_summary.csv"
    test_path = output / "mid_trend_round2_baseline_test_summary.csv"
    train_summary.to_csv(train_path, index=False)
    test_summary.to_csv(test_path, index=False)

    return {
        "config": {
            "start_date": start_date,
            "train_end_date": train_end_date,
            "end_date": end_date,
            "primary_goal": DEFAULT_MID_TREND_ROUND2_CONFIG.primary_goal,
            "secondary_goal": DEFAULT_MID_TREND_ROUND2_CONFIG.secondary_goal,
            "hard_constraints": DEFAULT_MID_TREND_ROUND2_CONFIG.hard_constraints,
        },
        "baseline_train_summary": train_summary,
        "baseline_test_summary": test_summary,
        "paths": {
            "baseline_train_summary": str(train_path),
            "baseline_test_summary": str(test_path),
        },
    }


def label_mid_trend_round2_failure_modes(detail: pd.DataFrame) -> pd.DataFrame:
    frame = detail.copy()
    root_cause = frame.get("root_cause", pd.Series(index=frame.index, dtype=object)).astype(str)
    frame["round2_failure_mode"] = "top_rank_fallout_other"
    frame.loc[
        root_cause.eq("dropped_out_of_top10_growth"),
        "round2_failure_mode",
    ] = "stable_to_lower_layer_rank_collapse"
    frame.loc[
        root_cause.eq("exposure_shrink_decrease"),
        "round2_failure_mode",
    ] = "allocation_trim_while_still_top_rank"
    frame.loc[
        root_cause.eq("protection_exit"),
        "round2_failure_mode",
    ] = "stable_to_risk_exclusion_cliff"
    return frame


def build_mid_trend_round2_baseline_diagnostics(
    *,
    labeled_detail: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if labeled_detail.empty:
        summary = pd.DataFrame(
            columns=["round2_failure_mode", "sample_count", "avg_forward_return"]
        )
    else:
        summary = (
            labeled_detail.groupby("round2_failure_mode", dropna=False, as_index=False)
            .agg(
                sample_count=("round2_failure_mode", "size"),
                avg_forward_return=("forward_return", "mean"),
            )
            .sort_values(["sample_count", "round2_failure_mode"], ascending=[False, True])
            .reset_index(drop=True)
        )
    summary_path = output / "mid_trend_round2_failure_mode_summary.csv"
    detail_path = output / "mid_trend_round2_failure_mode_detail.csv"
    summary.to_csv(summary_path, index=False)
    labeled_detail.to_csv(detail_path, index=False)
    return {
        "failure_mode_summary": summary,
        "labeled_detail": labeled_detail,
        "paths": {
            "failure_mode_summary": str(summary_path),
            "failure_mode_detail": str(detail_path),
        },
    }


def _metric_value(frame: pd.DataFrame, metric: str) -> float:
    matched = frame.loc[frame["metric"].astype(str).eq(metric), "value"]
    if matched.empty:
        return float("nan")
    values = pd.to_numeric(matched, errors="coerce").dropna()
    return float(values.iloc[0]) if not values.empty else float("nan")


def evaluate_mid_trend_round2_candidate_rule(
    *,
    candidate_name: str,
    rule_family: str,
    baseline_train: pd.DataFrame,
    baseline_test: pd.DataFrame,
    candidate_train: pd.DataFrame,
    candidate_test: pd.DataFrame,
) -> dict[str, object]:
    train_winner_loss_improved = _metric_value(candidate_train, "winner_loss_count") < _metric_value(
        baseline_train, "winner_loss_count"
    )
    test_winner_loss_improved = _metric_value(candidate_test, "winner_loss_count") < _metric_value(
        baseline_test, "winner_loss_count"
    )
    train_turnover_improved = _metric_value(candidate_train, "turnover_avg") < _metric_value(
        baseline_train, "turnover_avg"
    )
    test_turnover_improved = _metric_value(candidate_test, "turnover_avg") < _metric_value(
        baseline_test, "turnover_avg"
    )
    hard_constraint_breached = _metric_value(candidate_test, "max_drawdown") < (
        _metric_value(baseline_test, "max_drawdown") - 0.03
    )
    improves_primary_goal = bool(train_winner_loss_improved and test_winner_loss_improved)
    improves_secondary_goal = bool(train_turnover_improved and test_turnover_improved)
    decision = "keep"
    if hard_constraint_breached or not improves_primary_goal:
        decision = "reject"
    return {
        "candidate_name": candidate_name,
        "rule_family": rule_family,
        "decision": decision,
        "improves_primary_goal": improves_primary_goal,
        "improves_secondary_goal": improves_secondary_goal,
        "hard_constraint_breached": bool(hard_constraint_breached),
    }


def run_mid_trend_round2_optimization(
    *,
    start_date: str,
    train_end_date: str,
    end_date: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    baseline_payload: dict[str, pd.DataFrame] | None = None,
    replay_audit_detail: pd.DataFrame | None = None,
    candidate_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    baseline_payload = baseline_payload or _default_baseline_payload()
    replay_audit_detail = replay_audit_detail if replay_audit_detail is not None else _load_default_replay_audit_detail()
    baseline_result = build_mid_trend_round2_baseline_artifacts(
        start_date=start_date,
        train_end_date=train_end_date,
        end_date=end_date,
        output_dir=output,
        baseline_payload=baseline_payload,
    )

    labeled_detail = label_mid_trend_round2_failure_modes(replay_audit_detail)
    diagnostics = build_mid_trend_round2_baseline_diagnostics(
        labeled_detail=labeled_detail,
        output_dir=output,
    )
    issue_reduction_audit = build_mid_trend_round2_issue_reduction_audit(
        replay_audit_detail,
        output_dir=output,
    )
    return_comparison = build_mid_trend_round2_return_comparison(
        start_date=start_date,
        train_end_date=train_end_date,
        end_date=end_date,
        output_dir=output,
    )

    decisions = [
        evaluate_mid_trend_round2_candidate_rule(
            candidate_name=str(item["candidate_name"]),
            rule_family=str(item["rule_family"]),
            baseline_train=baseline_result["baseline_train_summary"],
            baseline_test=baseline_result["baseline_test_summary"],
            candidate_train=item["candidate_train"],
            candidate_test=item["candidate_test"],
        )
        for item in (candidate_rules or _default_candidate_rules())
    ]
    candidate_audit = pd.DataFrame(decisions)
    candidate_audit_path = output / "mid_trend_round2_candidate_audit.csv"
    candidate_audit.to_csv(candidate_audit_path, index=False)

    report_path = output / "mid_trend_round2_report.md"
    report_path.write_text(
        _render_round2_report(
            start_date=start_date,
            train_end_date=train_end_date,
            end_date=end_date,
            candidate_audit=candidate_audit,
            failure_mode_summary=diagnostics["failure_mode_summary"],
            issue_reduction_audit=issue_reduction_audit,
            return_comparison=return_comparison,
        ),
        encoding="utf-8",
    )

    return {
        "config": {
            "start_date": start_date,
            "train_end_date": train_end_date,
            "end_date": end_date,
            **asdict(DEFAULT_MID_TREND_ROUND2_CONFIG),
        },
        "baseline_train_summary": baseline_result["baseline_train_summary"],
        "baseline_test_summary": baseline_result["baseline_test_summary"],
        "failure_mode_summary": diagnostics["failure_mode_summary"],
        "issue_reduction_audit": issue_reduction_audit,
        "return_comparison": return_comparison,
        "candidate_audit": candidate_audit,
        "paths": {
            **baseline_result["paths"],
            **diagnostics["paths"],
            "issue_reduction_audit": str(output / "mid_trend_round2_issue_reduction_audit.csv"),
            "return_comparison": str(output / "mid_trend_round2_return_comparison.csv"),
            "candidate_audit": str(candidate_audit_path),
            "report": str(report_path),
        },
    }


def _default_baseline_payload() -> dict[str, pd.DataFrame]:
    return {
        "train_summary": pd.DataFrame(
            [
                {"metric": "winner_loss_count", "value": 10},
                {"metric": "turnover_avg", "value": 0.20},
                {"metric": "max_drawdown", "value": -0.18},
            ]
        ),
        "test_summary": pd.DataFrame(
            [
                {"metric": "winner_loss_count", "value": 9},
                {"metric": "turnover_avg", "value": 0.19},
                {"metric": "max_drawdown", "value": -0.17},
            ]
        ),
    }


def _default_replay_audit_detail() -> pd.DataFrame:
    if DEFAULT_REPLAY_AUDIT_PATH.exists():
        return pd.read_csv(DEFAULT_REPLAY_AUDIT_PATH, low_memory=False)
    return pd.DataFrame(
        [
            {
                "audit_label": "bad_sell",
                "action": "sell",
                "root_cause": "dropped_out_of_top10_growth",
                "confirmed_regime_state": "bull_trend",
                "forward_return": 0.12,
            }
        ]
    )


def _load_default_replay_audit_detail() -> pd.DataFrame:
    return _default_replay_audit_detail()


def _default_candidate_rules() -> list[dict[str, Any]]:
    return [
        {
            "candidate_name": "stable_layer_buffer_v1",
            "rule_family": "stable_layer_downgrade_buffer",
            "candidate_train": pd.DataFrame(
                [
                    {"metric": "winner_loss_count", "value": 7},
                    {"metric": "turnover_avg", "value": 0.15},
                    {"metric": "max_drawdown", "value": -0.17},
                ]
            ),
            "candidate_test": pd.DataFrame(
                [
                    {"metric": "winner_loss_count", "value": 8},
                    {"metric": "turnover_avg", "value": 0.17},
                    {"metric": "max_drawdown", "value": -0.16},
                ]
            ),
        }
    ]


def build_mid_trend_round2_issue_reduction_audit(
    detail: pd.DataFrame,
    *,
    output_dir: str | Path,
) -> pd.DataFrame:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base_bad_buy = int(detail["audit_label"].astype(str).eq("bad_buy").sum())
    base_bad_sell = int(detail["audit_label"].astype(str).eq("bad_sell").sum())
    rank = pd.to_numeric(detail.get("score_rank", pd.Series(index=detail.index, dtype=object)), errors="coerce")
    masks = [
        (
            "entry_regime_guard_plus_exit_top20_buffer",
            (detail["action"].isin(["buy", "increase"]) & detail["confirmed_regime_state"].isin(["overheated", "trend_decay"]))
            | (detail["action"].isin(["sell", "decrease"]) & rank.le(20)),
            "reduce hot entries and keep top-20 winners longer",
        ),
        (
            "entry_rank_gt20_plus_exit_top20_buffer",
            (detail["action"].isin(["buy", "increase"]) & rank.gt(20))
            | (detail["action"].isin(["sell", "decrease"]) & rank.le(20)),
            "rank-gated entry with top-20 exit buffer",
        ),
        (
            "entry_rank_gt50_plus_exit_top20_buffer",
            (detail["action"].isin(["buy", "increase"]) & rank.gt(50))
            | (detail["action"].isin(["sell", "decrease"]) & rank.le(20)),
            "less aggressive entry gate with top-20 exit buffer",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for candidate_name, mask, rationale in masks:
        bad_buy_reduced = int((mask & detail["audit_label"].astype(str).eq("bad_buy")).sum())
        bad_sell_reduced = int((mask & detail["audit_label"].astype(str).eq("bad_sell")).sum())
        rows.append(
            {
                "candidate_name": candidate_name,
                "rationale": rationale,
                "affected_trades": int(mask.sum()),
                "bad_buy_reduced": bad_buy_reduced,
                "bad_sell_reduced": bad_sell_reduced,
                "total_issue_reduced": bad_buy_reduced + bad_sell_reduced,
                "issue_reduction_rate": (bad_buy_reduced + bad_sell_reduced) / max(1, base_bad_buy + base_bad_sell),
                "remaining_bad_buy": base_bad_buy - bad_buy_reduced,
                "remaining_bad_sell": base_bad_sell - bad_sell_reduced,
            }
        )
    audit = pd.DataFrame(rows).sort_values(
        ["total_issue_reduced", "affected_trades"],
        ascending=[False, True],
    )
    audit_path = output / "mid_trend_round2_issue_reduction_audit.csv"
    audit.to_csv(audit_path, index=False)
    return audit.reset_index(drop=True)


def build_mid_trend_round2_return_comparison(
    *,
    start_date: str,
    train_end_date: str,
    end_date: str,
    output_dir: str | Path,
    current_variant_dir: str | Path = DEFAULT_CURRENT_VARIANT_OUTPUT_DIR,
    entry_block_regimes: tuple[str, ...] = ("overheated", "trend_decay"),
    entry_block_rank_gt: int | None = None,
    exit_hold_rank_max: int = 20,
) -> pd.DataFrame:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    current_variant_dir = Path(current_variant_dir)
    trade_changes_path = current_variant_dir / "current_mid_trend_strategy_v1_trade_changes.csv"
    equity_path = current_variant_dir / "current_mid_trend_strategy_v1_equity.csv"
    columns = [
        "strategy_name",
        "interval_name",
        "start_date",
        "end_date",
        "first_available_date",
        "last_available_date",
        "start_equity",
        "end_equity",
        "interval_return",
        "max_drawdown",
        "days",
    ]
    if not trade_changes_path.exists() or not equity_path.exists():
        return pd.DataFrame(columns=columns)

    baseline_equity = pd.read_csv(equity_path, low_memory=False)
    trade_changes = pd.read_csv(trade_changes_path, low_memory=False)
    variant_equity = _simulate_mid_trend_round2_variant_equity(
        trade_changes=trade_changes,
        start_date=start_date,
        end_date=end_date,
        entry_block_regimes=entry_block_regimes,
        entry_block_rank_gt=entry_block_rank_gt,
        exit_hold_rank_max=exit_hold_rank_max,
    )
    comparison = pd.DataFrame(
        [
            _summarize_interval_returns(
                strategy_name="baseline",
                equity=baseline_equity,
                start_date=start_date,
                end_date=train_end_date,
                interval_name="train",
            ),
            _summarize_interval_returns(
                strategy_name="variant",
                equity=variant_equity,
                start_date=start_date,
                end_date=train_end_date,
                interval_name="train",
            ),
            _summarize_interval_returns(
                strategy_name="baseline",
                equity=baseline_equity,
                start_date=train_end_date,
                end_date=end_date,
                interval_name="test",
            ),
            _summarize_interval_returns(
                strategy_name="variant",
                equity=variant_equity,
                start_date=train_end_date,
                end_date=end_date,
                interval_name="test",
            ),
        ],
        columns=columns,
    )
    comparison_path = output / "mid_trend_round2_return_comparison.csv"
    comparison.to_csv(comparison_path, index=False)
    return comparison


def _simulate_mid_trend_round2_variant_equity(
    *,
    trade_changes: pd.DataFrame,
    start_date: str,
    end_date: str,
    entry_block_regimes: tuple[str, ...],
    entry_block_rank_gt: int | None = None,
    exit_hold_rank_max: int,
) -> pd.DataFrame:
    if trade_changes.empty:
        return pd.DataFrame(columns=["trade_date", "daily_return", "equity"])
    frame = trade_changes.copy()
    for column in [
        "trade_date",
        "asset_id",
        "action",
        "confirmed_regime_state",
        "previous_weight",
        "target_weight",
        "score_rank",
    ]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["action"] = frame["action"].astype(str)
    frame["confirmed_regime_state"] = frame["confirmed_regime_state"].fillna("").astype(str)
    frame["previous_weight"] = pd.to_numeric(frame["previous_weight"], errors="coerce").fillna(0.0)
    frame["target_weight"] = pd.to_numeric(frame["target_weight"], errors="coerce").fillna(0.0)
    frame["score_rank"] = pd.to_numeric(frame["score_rank"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "daily_return", "equity"])

    asset_ids = sorted(frame["asset_id"].dropna().astype(str).unique().tolist())
    try:
        prices = load_current_strategy_prices(
            start_date,
            end_date,
            asset_ids=asset_ids,
            service=SETTINGS.research_service,
        )
    except Exception:
        return pd.DataFrame(columns=["trade_date", "daily_return", "equity"])
    price_returns = _normalize_price_returns(prices)
    if price_returns.empty:
        return pd.DataFrame(columns=["trade_date", "daily_return", "equity"])

    returns_by_date = {
        str(trade_date): group.set_index("asset_id")["next_return"].to_dict()
        for trade_date, group in price_returns.groupby("trade_date", sort=True)
    }
    trades_by_date = {
        str(trade_date): group.sort_values(["asset_id", "action"]).copy()
        for trade_date, group in frame.groupby("trade_date", sort=True)
    }
    current_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for trade_date in sorted(returns_by_date):
        day = trades_by_date.get(str(trade_date))
        if day is not None:
            for row in day.itertuples(index=False):
                blocked = False
                if row.action in {"buy", "increase"} and row.confirmed_regime_state in set(entry_block_regimes):
                    blocked = True
                if (
                    row.action in {"buy", "increase"}
                    and entry_block_rank_gt is not None
                    and pd.notna(row.score_rank)
                    and float(row.score_rank) > float(entry_block_rank_gt)
                ):
                    blocked = True
                if row.action in {"sell", "decrease"} and pd.notna(row.score_rank) and float(row.score_rank) <= float(
                    exit_hold_rank_max
                ):
                    blocked = True
                current_weights[str(row.asset_id)] = float(row.previous_weight) if blocked else float(row.target_weight)
                if current_weights[str(row.asset_id)] <= 0.0:
                    current_weights.pop(str(row.asset_id), None)
        total_weight = float(sum(current_weights.values()))
        if total_weight > 1.0:
            current_weights = {
                asset_id: float(weight) / total_weight for asset_id, weight in current_weights.items() if float(weight) > 0.0
            }
        next_returns = returns_by_date.get(str(trade_date), {})
        daily_return = 0.0
        if current_weights and next_returns:
            daily_return = float(
                sum(float(weight) * float(next_returns.get(asset_id, 0.0)) for asset_id, weight in current_weights.items())
            )
        rows.append({"trade_date": str(trade_date), "daily_return": daily_return})

    equity = pd.DataFrame(rows)
    equity["equity"] = (1.0 + equity["daily_return"].astype(float)).cumprod()
    return equity


def _normalize_price_returns(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "next_return"])
    for column in ["trade_date", "asset_id", "close"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "asset_id", "close"]).sort_values(["asset_id", "trade_date"])
    frame["next_return"] = frame.groupby("asset_id")["close"].shift(-1) / frame["close"] - 1.0
    return frame[["trade_date", "asset_id", "next_return"]]


def _summarize_interval_returns(
    *,
    strategy_name: str,
    equity: pd.DataFrame,
    start_date: str,
    end_date: str,
    interval_name: str,
) -> dict[str, Any]:
    frame = equity.copy()
    if frame.empty or "trade_date" not in frame.columns:
        return {
            "strategy_name": strategy_name,
            "interval_name": interval_name,
            "start_date": start_date,
            "end_date": end_date,
            "first_available_date": "",
            "last_available_date": "",
            "start_equity": float("nan"),
            "end_equity": float("nan"),
            "interval_return": float("nan"),
            "max_drawdown": float("nan"),
            "days": 0,
        }
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["equity"] = pd.to_numeric(frame.get("equity"), errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["equity"]).copy()
    if frame.empty:
        return {
            "strategy_name": strategy_name,
            "interval_name": interval_name,
            "start_date": start_date,
            "end_date": end_date,
            "first_available_date": "",
            "last_available_date": "",
            "start_equity": float("nan"),
            "end_equity": float("nan"),
            "interval_return": float("nan"),
            "max_drawdown": float("nan"),
            "days": 0,
        }
    curve = frame["equity"].astype(float)
    start_equity = float(curve.iloc[0])
    end_equity = float(curve.iloc[-1])
    running_max = curve.cummax()
    drawdown = curve / running_max - 1.0
    return {
        "strategy_name": strategy_name,
        "interval_name": interval_name,
        "start_date": start_date,
        "end_date": end_date,
        "first_available_date": str(frame["trade_date"].iloc[0]),
        "last_available_date": str(frame["trade_date"].iloc[-1]),
        "start_equity": start_equity,
        "end_equity": end_equity,
        "interval_return": end_equity / start_equity - 1.0 if start_equity else float("nan"),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else float("nan"),
        "days": int(len(frame)),
    }


def _render_round2_report(
    *,
    start_date: str,
    train_end_date: str,
    end_date: str,
    candidate_audit: pd.DataFrame,
    failure_mode_summary: pd.DataFrame,
    issue_reduction_audit: pd.DataFrame,
    return_comparison: pd.DataFrame,
) -> str:
    lines = [
        "# Mid Trend Round 2 Optimization",
        "",
        f"- start_date: {start_date}",
        f"- train_end_date: {train_end_date}",
        f"- end_date: {end_date}",
        "",
        "## Candidate Audit",
        candidate_audit.to_markdown(index=False) if not candidate_audit.empty else "No candidates.",
        "",
        "## Failure Mode Summary",
        failure_mode_summary.to_markdown(index=False) if not failure_mode_summary.empty else "No failure rows.",
        "",
        "## Issue Reduction Audit",
        issue_reduction_audit.to_markdown(index=False) if not issue_reduction_audit.empty else "No issue rows.",
        "",
        "## Return Comparison",
        return_comparison.to_markdown(index=False) if not return_comparison.empty else "No return rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
