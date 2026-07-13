from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import (
    DEFAULT_PROTECTION_CONFIG,
    _build_daily_holdings,
    _build_holding_summary,
    _build_industry_exposure,
    _build_trade_changes,
    _ensure_atr20,
    _period_summary,
    build_current_mid_trend_strategy_v1_from_frames,
    load_current_strategy_prices,
)
from stock_research.market_regime_confirmation_v1 import _weekly_effective_exposure
from stock_research.market_style_switch_v1 import _filter_date_range, _simulate_equal_weight_daily, _summarize_equity
from stock_research.mid_trend_stock_protection_v1 import _protection_reason
from stock_research.midtrend_topn_pool_reentry_sweep import (
    DEFAULT_FUNNEL_DETAIL_PATH,
    DEFAULT_REGIME_PATH,
    _assemble_variant_result,
    _build_end_return_lookup,
    _build_enriched_funnel,
)
from stock_research.midtrend_topn_pool_reentry_sweep import (
    _build_funnel_meta,
    _build_growth_rank_frame,
    _build_position_episodes,
    _build_price_state,
    _build_trade_audit,
    _code_audit_markdown as _unused_code_audit_markdown,
    _daily_exposure_series,
    _date_str,
    _exposure_row,
    _holding_daily_contribution,
    _industry_exposure_table,
    _next_day_return,
    _num,
    _price_horizon_return,
    _ranking_churn_row,
    _run_topn_pool_variant,
    _sharpe,
    _slot_contribution_table,
    _variant_summary,
    _volatility,
)

WATCH_WINDOW_DAYS = 30
TOP10_REENTRY_CAP = 10
TOP20_REENTRY_THRESHOLD = 20
REENTRY_FORWARD_WINDOWS = (5, 10, 20)
PREVIOUS_SWEEP_SUMMARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "research"
    / "midtrend_topn_pool_reentry_sweep_20260626"
    / "baseline_vs_topn_pool_variants.csv"
)


@dataclass(frozen=True)
class Top10ReentryVariantConfig:
    variant_name: str
    final_top_n: int
    candidate_pool_size: int
    reentry_mode: str = "none"
    max_reentry_slots: int = 0
    reentry_rank_cap: int | None = None
    require_score_improvement: bool = False
    require_rank_improvement: bool = False
    min_stock_excess_ret_20_score: float | None = None
    min_max_drawdown_20_score: float | None = None
    block_high_elasticity_without_strong_mainline: bool = False
    cooldown_days: int = 0


def default_top10_reentry_variant_configs() -> list[Top10ReentryVariantConfig]:
    return [
        Top10ReentryVariantConfig("baseline_top5", final_top_n=5, candidate_pool_size=10),
        Top10ReentryVariantConfig("top8_reference", final_top_n=8, candidate_pool_size=10),
        Top10ReentryVariantConfig("top10_reference", final_top_n=10, candidate_pool_size=10),
        Top10ReentryVariantConfig(
            "top5_strict_top10_reentry",
            final_top_n=5,
            candidate_pool_size=10,
            reentry_mode="strict_top10_reentry",
        ),
        Top10ReentryVariantConfig(
            "top8_strict_top10_reentry",
            final_top_n=8,
            candidate_pool_size=10,
            reentry_mode="strict_top10_reentry",
        ),
        Top10ReentryVariantConfig(
            "top10_strict_top10_reentry",
            final_top_n=10,
            candidate_pool_size=10,
            reentry_mode="strict_top10_reentry",
        ),
        Top10ReentryVariantConfig(
            "top10_strict_top20_reentry_slot1",
            final_top_n=10,
            candidate_pool_size=10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
        ),
    ]


def run_midtrend_top10_reentry_experiment_cli(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    regime = pd.read_csv(regime_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    enriched = _build_enriched_funnel(funnel, start_date=start_date, end_date=end_date)
    growth_all = _build_growth_rank_frame(enriched, start_date=start_date, end_date=end_date)
    growth_assets = sorted(growth_all["asset_id"].dropna().astype(str).unique().tolist())
    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=growth_assets,
        adjust_type="hfq",
    )
    return run_midtrend_top10_reentry_experiment_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def run_midtrend_top10_reentry_experiment_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variants: list[Top10ReentryVariantConfig] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    enriched_funnel = _build_enriched_funnel(funnel, start_date=start_date, end_date=end_date)
    prices_with_atr = _ensure_atr20(prices)
    price_state = _build_price_state(prices_with_atr)
    end_return_lookup = _build_end_return_lookup(prices_with_atr)
    growth_all = _build_growth_rank_frame(enriched_funnel, start_date=start_date, end_date=end_date)
    configs = variants or default_top10_reentry_variant_configs()

    baseline = _run_baseline_variant(
        regime=regime,
        funnel=enriched_funnel,
        prices=prices_with_atr,
        end_return_lookup=end_return_lookup,
        start_date=start_date,
        end_date=end_date,
    )

    reference_cache: dict[int, dict[str, Any]] = {
        5: baseline,
        8: _run_reference_variant(
            regime=regime,
            funnel=enriched_funnel,
            growth_all=growth_all,
            prices=prices_with_atr,
            price_state=price_state,
            end_return_lookup=end_return_lookup,
            start_date=start_date,
            end_date=end_date,
            final_top_n=8,
            variant_name="top8_reference",
        ),
        10: _run_reference_variant(
            regime=regime,
            funnel=enriched_funnel,
            growth_all=growth_all,
            prices=prices_with_atr,
            price_state=price_state,
            end_return_lookup=end_return_lookup,
            start_date=start_date,
            end_date=end_date,
            final_top_n=10,
            variant_name="top10_reference",
        ),
    }

    results: list[dict[str, Any]] = []
    internal_reference_rows: list[dict[str, Any]] = []
    for config in configs:
        if config.variant_name == "baseline_top5":
            result = _rename_variant_result(reference_cache[5], "baseline_top5")
        elif config.variant_name == "top8_reference":
            result = reference_cache[8]
        elif config.variant_name == "top10_reference":
            result = reference_cache[10]
        else:
            result = _run_reentry_variant(
                regime=regime,
                funnel=enriched_funnel,
                growth_all=growth_all,
                prices=prices_with_atr,
                price_state=price_state,
                end_return_lookup=end_return_lookup,
                start_date=start_date,
                end_date=end_date,
                config=config,
            )
            if (
                config.reentry_mode == "strict_top10_reentry"
                and config.final_top_n >= TOP10_REENTRY_CAP
                and result.get("reentry_trade_contribution", pd.DataFrame()).empty
            ):
                reference = _rename_variant_result(reference_cache[config.final_top_n], config.variant_name)
                reference["reentry_mode"] = config.reentry_mode
                reference["max_reentry_slots"] = config.max_reentry_slots
                reference["reentry_event_log"] = result.get("reentry_event_log", pd.DataFrame())
                reference["reentry_trade_contribution"] = result.get("reentry_trade_contribution", pd.DataFrame())
                reference["watch_lifecycle"] = result.get("watch_lifecycle", pd.DataFrame())
                result = reference
        results.append(result)
        if result["variant_name"] not in {"baseline_top5", "top10_reference"}:
            internal_reference_rows.append(result)

    summary = pd.DataFrame([_reentry_variant_summary(item) for item in results])
    summary = _attach_incremental_comparison(summary)
    summary.to_csv(output / "baseline_vs_top10_reentry_variants.csv", index=False)
    (output / "baseline_vs_top10_reentry_variants.md").write_text(
        summary.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )

    reentry_event_log = pd.concat(
        [item.get("reentry_event_log", pd.DataFrame()) for item in results],
        ignore_index=True,
    )
    reentry_event_log.to_csv(output / "reentry_event_log.csv", index=False)

    reentry_trade_contribution = pd.concat(
        [item.get("reentry_trade_contribution", pd.DataFrame()) for item in results],
        ignore_index=True,
    )
    reentry_trade_contribution.to_csv(output / "reentry_trade_contribution.csv", index=False)

    watch_lifecycle = pd.concat(
        [item.get("watch_lifecycle", pd.DataFrame()) for item in results],
        ignore_index=True,
    )
    watch_lifecycle.to_csv(output / "reentry_watch_pool_lifecycle.csv", index=False)

    reentry_skip = (
        reentry_event_log[reentry_event_log["action_taken"].astype(str).str.startswith("skip_")]
        .groupby(["variant_name", "skip_reason"], as_index=False)
        .agg(event_count=("asset_id", "size"))
        .sort_values(["variant_name", "event_count"], ascending=[True, False])
    )
    reentry_skip.to_csv(output / "reentry_skip_reasons.csv", index=False)

    ranking_churn = pd.DataFrame([_ranking_churn_row(item) for item in results])
    ranking_churn.to_csv(output / "ranking_churn_comparison.csv", index=False)

    slot_top10 = _slot_contribution_table(reference_cache[10], price_state)
    slot_top10.to_csv(output / "slot_contribution_top10_reference.csv", index=False)

    reproduction_note = _top10_reproduction_note(summary)
    (output / "code_audit.md").write_text(
        _code_audit(summary, reproduction_note),
        encoding="utf-8",
    )
    (output / "final_interpretation.md").write_text(
        _final_interpretation(summary, ranking_churn, reentry_trade_contribution, reproduction_note),
        encoding="utf-8",
    )

    return {
        "summary": summary,
        "paths": {
            "summary_csv": str(output / "baseline_vs_top10_reentry_variants.csv"),
            "summary_md": str(output / "baseline_vs_top10_reentry_variants.md"),
            "final_interpretation": str(output / "final_interpretation.md"),
        },
    }


def _run_baseline_variant(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    end_return_lookup: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    result = build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
    )
    growth_all = _build_growth_rank_frame(funnel, start_date=start_date, end_date=end_date)
    selection_detail = (
        growth_all[growth_all["candidate_rank"].le(10)]
        .sort_values(["trade_date", "candidate_rank", "asset_id"])
        .groupby("trade_date", group_keys=False)
        .head(5)
        .copy()
    )
    selection_detail["final_slot_rank"] = selection_detail.groupby("trade_date").cumcount() + 1
    assembled = _assemble_variant_result(
        variant_name="baseline_internal",
        final_top_n=5,
        candidate_pool_size=10,
        regime=regime,
        funnel=funnel,
        prices=prices,
        end_return_lookup=end_return_lookup,
        raw_result=result,
        selection_detail=selection_detail,
    )
    assembled["reentry_mode"] = "none"
    assembled["max_reentry_slots"] = 0
    assembled["reentry_event_log"] = pd.DataFrame(columns=_reentry_event_columns())
    assembled["reentry_trade_contribution"] = pd.DataFrame(columns=_reentry_trade_columns())
    assembled["watch_lifecycle"] = pd.DataFrame(columns=_watch_lifecycle_columns())
    return assembled


def _run_reference_variant(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    growth_all: pd.DataFrame,
    prices: pd.DataFrame,
    price_state: dict[str, Any],
    end_return_lookup: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
    final_top_n: int,
    variant_name: str,
) -> dict[str, Any]:
    from stock_research.midtrend_topn_pool_reentry_sweep import TopNPoolVariantConfig

    base = _run_topn_pool_variant(
        regime=regime,
        funnel=funnel,
        growth_all=growth_all,
        prices=prices,
        price_state=price_state,
        end_return_lookup=end_return_lookup,
        start_date=start_date,
        end_date=end_date,
        config=TopNPoolVariantConfig(
            variant_name=variant_name,
            final_top_n=final_top_n,
            candidate_pool_size=max(final_top_n, 10),
        ),
    )
    base["reentry_mode"] = "none"
    base["max_reentry_slots"] = 0
    base["reentry_event_log"] = pd.DataFrame(columns=_reentry_event_columns())
    base["reentry_trade_contribution"] = pd.DataFrame(columns=_reentry_trade_columns())
    base["watch_lifecycle"] = pd.DataFrame(columns=_watch_lifecycle_columns())
    return base


def _rename_variant_result(result: dict[str, Any], variant_name: str) -> dict[str, Any]:
    cloned = {
        key: (value.copy() if isinstance(value, pd.DataFrame) else value)
        for key, value in result.items()
    }
    cloned["variant_name"] = variant_name
    for key in ["equity", "holdings", "trades", "industry_exposure"]:
        if key in cloned and isinstance(cloned[key], pd.DataFrame):
            cloned[key]["variant_name"] = variant_name
    return cloned


def _run_reentry_variant(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    growth_all: pd.DataFrame,
    prices: pd.DataFrame,
    price_state: dict[str, Any],
    end_return_lookup: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
    config: Top10ReentryVariantConfig,
) -> dict[str, Any]:
    normalized_regime = _filter_date_range(regime, start_date, end_date).copy()
    normalized_regime["trade_date"] = _date_str(normalized_regime["trade_date"])
    confirmed = (
        normalized_regime.set_index("trade_date")["confirmed_regime_state"].to_dict()
        if "confirmed_regime_state" in normalized_regime.columns
        else {}
    )
    exposures = _weekly_effective_exposure(normalized_regime).to_dict()

    price_frame = prices.copy()
    price_frame["trade_date"] = _date_str(price_frame["trade_date"])
    price_frame["asset_id"] = price_frame["asset_id"].astype(str)
    price_by_key = {(row.trade_date, row.asset_id): row for row in price_frame.itertuples(index=False)}

    funnel_lookup_frame = funnel.copy()
    funnel_lookup_frame["trade_date"] = _date_str(funnel_lookup_frame["trade_date"])
    funnel_lookup_frame["asset_id"] = funnel_lookup_frame["asset_id"].astype(str)
    score_by_key = {(row.trade_date, row.asset_id): row for row in funnel_lookup_frame.itertuples(index=False)}
    growth_by_date = {
        str(trade_date): group.sort_values(["candidate_rank", "asset_id"]).reset_index(drop=True)
        for trade_date, group in growth_all.groupby("trade_date", sort=True)
    }

    state_by_asset: dict[str, dict[str, Any]] = {}
    score_history: dict[str, list[float]] = {}
    rank_history: dict[str, list[float]] = {}
    watch_pool: dict[str, dict[str, Any]] = {}
    previous_held_assets: set[str] = set()
    previous_day_growth_assets: set[str] = set()

    selection_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    executed_rows: dict[tuple[str, str], dict[str, Any]] = {}

    dates = sorted(normalized_regime["trade_date"].dropna().astype(str).unique().tolist())
    for day_index, trade_date in enumerate(dates):
        day_growth = growth_by_date.get(trade_date, pd.DataFrame(columns=growth_all.columns))
        pool = day_growth.head(config.candidate_pool_size).copy()
        base_selected = pool.head(config.final_top_n).copy()
        base_asset_ids = base_selected["asset_id"].astype(str).tolist()
        final_selected = base_selected.copy()
        final_selected["selection_source"] = "base"
        final_selected["reentry_mode"] = ""
        final_selected["watch_start_date"] = ""

        day_watch_state = _prune_watch_pool(
            watch_pool=watch_pool,
            trade_date=trade_date,
            score_by_key=score_by_key,
            lifecycle_rows=lifecycle_rows,
            day_index=day_index,
            variant_name=config.variant_name,
        )
        watch_pool = day_watch_state

        if config.reentry_mode != "none":
            final_selected, signal_events = _apply_reentry_layer(
                trade_date=trade_date,
                config=config,
                base_selected=final_selected,
                watch_pool=watch_pool,
                score_by_key=score_by_key,
                growth_day=day_growth,
            )
            event_rows.extend(signal_events)
            for row in signal_events:
                if row["action_taken"] == "executed_reentry_signal":
                    executed_rows[(trade_date, str(row["asset_id"]))] = row

        invested_weight = float(exposures.get(trade_date, 0.6))
        day_selection = final_selected.copy()
        if day_selection.empty:
            selection_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": pd.NA,
                    "strategy_family": config.variant_name,
                    "selection_style": "growth_momentum",
                    "invested_weight": 0.0,
                    "confirmed_regime_state": confirmed.get(trade_date, ""),
                    "selection_source": "base",
                    "reentry_mode": "",
                    "watch_start_date": "",
                }
            )
            held_today: set[str] = set()
            current_assets = set()
        else:
            for row in day_selection.itertuples(index=False):
                selection_rows.append(
                    {
                        "trade_date": trade_date,
                        "asset_id": str(row.asset_id),
                        "strategy_family": config.variant_name,
                        "selection_style": "growth_momentum",
                        "invested_weight": invested_weight,
                        "confirmed_regime_state": confirmed.get(trade_date, ""),
                        "selection_source": getattr(row, "selection_source", "base"),
                        "reentry_mode": getattr(row, "reentry_mode", ""),
                        "watch_start_date": getattr(row, "watch_start_date", ""),
                    }
                )
            current_assets = set(day_selection["asset_id"].astype(str).tolist())

            protected_day = _apply_protection_for_day(
                trade_date=trade_date,
                day_selection=day_selection,
                config_variant_name=config.variant_name,
                confirmed_regime_state=confirmed.get(trade_date, ""),
                price_by_key=price_by_key,
                score_by_key=score_by_key,
                state_by_asset=state_by_asset,
                score_history=score_history,
                rank_history=rank_history,
            )
            held_today = {
                str(row["asset_id"])
                for row in protected_day
                if pd.notna(row.get("asset_id"))
            }
            for row in protected_day:
                if row.get("selection_source") == "reentry":
                    key = (trade_date, str(row.get("asset_id")))
                    if key in executed_rows and pd.notna(row.get("asset_id")):
                        executed_rows[key]["action_taken"] = "executed_reentry_signal"
                    elif key in executed_rows:
                        executed_rows[key]["action_taken"] = "blocked_by_protection"

        for asset_id in list(watch_pool):
            if asset_id in held_today:
                lifecycle_rows.append(
                    {
                        "variant_name": config.variant_name,
                        "asset_id": asset_id,
                        "event_date": trade_date,
                        "event_type": "watch_removed",
                        "reason": "bought_back",
                        "watch_start_date": watch_pool[asset_id]["watch_start_date"],
                    }
                )
                watch_pool.pop(asset_id, None)

        exited_assets = previous_held_assets - held_today
        for asset_id in sorted(exited_assets):
            exit_meta = _exit_meta(
                asset_id=asset_id,
                trade_date=trade_date,
                score_by_key=score_by_key,
                growth_day=day_growth,
            )
            watch_pool[asset_id] = {
                "asset_id": asset_id,
                "watch_start_date": trade_date,
                "watch_start_index": day_index,
                "exit_rank": exit_meta["exit_rank"],
                "exit_score": exit_meta["exit_score"],
                "stock_name": exit_meta["stock_name"],
                "industry_name": exit_meta["industry_name"],
            }
            lifecycle_rows.append(
                {
                    "variant_name": config.variant_name,
                    "asset_id": asset_id,
                    "event_date": trade_date,
                    "event_type": "watch_start",
                    "reason": "exited_holding",
                    "watch_start_date": trade_date,
                }
            )

        previous_held_assets = held_today
        previous_day_growth_assets = current_assets
        _ = previous_day_growth_assets

    selection = pd.DataFrame(selection_rows)
    protected = _apply_stock_protection_incrementally(
        selection=selection,
        prices=price_frame,
        funnel=funnel_lookup_frame,
        strategy_family=config.variant_name,
    )
    holdings = _build_daily_holdings(
        protected,
        funnel_lookup_frame,
        normalized_regime,
        asset_names=None,
        protection_variant=DEFAULT_PROTECTION_CONFIG.variant_name,
    )
    equity = _simulate_equal_weight_daily(prices, protected, strategy_family=config.variant_name)
    summary = _summarize_equity(equity)
    trades = _build_trade_changes(holdings)
    raw_result = {
        "equity": equity,
        "summary": summary,
        "holdings": holdings,
        "trades": trades,
        "holding_summary": _build_holding_summary(holdings, normalized_regime),
        "industry_exposure": _build_industry_exposure(holdings),
        "annual": _period_summary(equity, "Y"),
        "quarterly": _period_summary(equity, "Q"),
        "protection_events": holdings[holdings["protection_reason"].astype(str).ne("")].copy(),
    }

    selection_detail = selection.merge(
        growth_all[["trade_date", "asset_id", "candidate_rank", "growth_rank_score"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    selection_detail = selection_detail.sort_values(["trade_date", "candidate_rank", "asset_id"]).reset_index(drop=True)
    selection_detail["final_slot_rank"] = selection_detail.groupby("trade_date").cumcount() + 1

    assembled = _assemble_variant_result(
        variant_name=config.variant_name,
        final_top_n=config.final_top_n,
        candidate_pool_size=config.candidate_pool_size,
        regime=normalized_regime,
        funnel=funnel_lookup_frame,
        prices=prices,
        end_return_lookup=end_return_lookup,
        raw_result=raw_result,
        selection_detail=selection_detail,
    )
    assembled["reentry_mode"] = config.reentry_mode
    assembled["max_reentry_slots"] = config.max_reentry_slots

    event_log = pd.DataFrame(event_rows, columns=_reentry_event_columns())
    trade_contribution = _build_reentry_trade_contribution(
        holdings=assembled["holdings"],
        trades=assembled["trades"],
        event_log=event_log,
        price_state=price_state,
        end_return_lookup=end_return_lookup,
        variant_name=config.variant_name,
    )
    assembled["reentry_event_log"] = event_log
    assembled["reentry_trade_contribution"] = trade_contribution
    assembled["watch_lifecycle"] = pd.DataFrame(lifecycle_rows, columns=_watch_lifecycle_columns())
    return assembled


def _apply_protection_for_day(
    *,
    trade_date: str,
    day_selection: pd.DataFrame,
    config_variant_name: str,
    confirmed_regime_state: str,
    price_by_key: dict[tuple[str, str], Any],
    score_by_key: dict[tuple[str, str], Any],
    state_by_asset: dict[str, dict[str, Any]],
    score_history: dict[str, list[float]],
    rank_history: dict[str, list[float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in day_selection.itertuples(index=False):
        asset_id = str(row.asset_id)
        base = {
            "trade_date": trade_date,
            "asset_id": asset_id,
            "strategy_family": config_variant_name,
            "selection_style": "growth_momentum",
            "invested_weight": float(getattr(row, "invested_weight", 0.0) or 0.0),
            "protection_reason": "",
            "selection_source": getattr(row, "selection_source", "base"),
            "reentry_mode": getattr(row, "reentry_mode", ""),
            "watch_start_date": getattr(row, "watch_start_date", ""),
        }
        price = price_by_key.get((trade_date, asset_id))
        score = score_by_key.get((trade_date, asset_id))
        if price is None or pd.isna(price.close) or float(base["invested_weight"]) <= 0:
            rows.append(base)
            continue

        close = float(price.close)
        state = state_by_asset.get(asset_id)
        if state is None:
            state = {"entry_close": close, "highest_close": close}
        else:
            state["highest_close"] = max(float(state["highest_close"]), close)

        reason = _protection_reason(
            close=close,
            state=state,
            price=price,
            score=score,
            score_history=score_history.get(asset_id, []),
            rank_history=rank_history.get(asset_id, []),
            regime_state=confirmed_regime_state,
            config=DEFAULT_PROTECTION_CONFIG,
        )
        score_value = getattr(score, "mid_trend_funnel_score", pd.NA) if score is not None else pd.NA
        if pd.notna(score_value):
            score_history.setdefault(asset_id, []).append(float(score_value))
        rank_value = getattr(score, "score_rank", pd.NA) if score is not None else pd.NA
        if pd.notna(rank_value):
            rank_history.setdefault(asset_id, []).append(float(rank_value))
        if reason:
            state_by_asset.pop(asset_id, None)
            blocked = base.copy()
            blocked["asset_id"] = pd.NA
            blocked["protection_reason"] = reason
            rows.append(blocked)
        else:
            state_by_asset[asset_id] = state
            rows.append(base)
    return rows


def _apply_stock_protection_incrementally(
    *,
    selection: pd.DataFrame,
    prices: pd.DataFrame,
    funnel: pd.DataFrame,
    strategy_family: str,
) -> pd.DataFrame:
    price_by_key = {(row.trade_date, row.asset_id): row for row in prices.itertuples(index=False)}
    score_by_key = {(row.trade_date, row.asset_id): row for row in funnel.itertuples(index=False)}
    state_by_asset: dict[str, dict[str, Any]] = {}
    score_history: dict[str, list[float]] = {}
    rank_history: dict[str, list[float]] = {}
    output_rows: list[dict[str, Any]] = []
    confirmed_by_date = (
        selection[["trade_date", "confirmed_regime_state"]]
        .drop_duplicates(subset=["trade_date"])
        .set_index("trade_date")["confirmed_regime_state"]
        .to_dict()
    )
    for trade_date, day in selection.groupby("trade_date", sort=True):
        day = day[day["asset_id"].notna()].copy()
        if day.empty:
            output_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": pd.NA,
                    "strategy_family": strategy_family,
                    "selection_style": "growth_momentum",
                    "invested_weight": 0.0,
                    "protection_reason": "empty_selection",
                }
            )
            continue
        output_rows.extend(
            _apply_protection_for_day(
                trade_date=str(trade_date),
                day_selection=day,
                config_variant_name=strategy_family,
                confirmed_regime_state=str(confirmed_by_date.get(trade_date, "")),
                price_by_key=price_by_key,
                score_by_key=score_by_key,
                state_by_asset=state_by_asset,
                score_history=score_history,
                rank_history=rank_history,
            )
        )
    return pd.DataFrame(output_rows)


def _prune_watch_pool(
    *,
    watch_pool: dict[str, dict[str, Any]],
    trade_date: str,
    score_by_key: dict[tuple[str, str], Any],
    lifecycle_rows: list[dict[str, Any]],
    day_index: int,
    variant_name: str,
) -> dict[str, dict[str, Any]]:
    result = dict(watch_pool)
    for asset_id in list(result):
        entry = result[asset_id]
        if day_index - int(entry["watch_start_index"]) >= WATCH_WINDOW_DAYS:
            lifecycle_rows.append(
                {
                    "variant_name": variant_name,
                    "asset_id": asset_id,
                    "event_date": trade_date,
                    "event_type": "watch_removed",
                    "reason": "expired",
                    "watch_start_date": entry["watch_start_date"],
                }
            )
            result.pop(asset_id, None)
            continue
        score = score_by_key.get((trade_date, asset_id))
        if _hard_damage_score(score):
            lifecycle_rows.append(
                {
                    "variant_name": variant_name,
                    "asset_id": asset_id,
                    "event_date": trade_date,
                    "event_type": "watch_removed",
                    "reason": "hard_damage",
                    "watch_start_date": entry["watch_start_date"],
                }
            )
            result.pop(asset_id, None)
    return result


def _apply_reentry_layer(
    *,
    trade_date: str,
    config: Top10ReentryVariantConfig,
    base_selected: pd.DataFrame,
    watch_pool: dict[str, dict[str, Any]],
    score_by_key: dict[tuple[str, str], Any],
    growth_day: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    event_rows: list[dict[str, Any]] = []
    if not watch_pool:
        return base_selected, event_rows
    growth_by_asset = {str(row.asset_id): row for row in growth_day.itertuples(index=False)}
    selected_assets = set(base_selected["asset_id"].astype(str).tolist())
    final_selected = base_selected.copy()

    eligible: list[dict[str, Any]] = []
    for asset_id, watch in watch_pool.items():
        score = score_by_key.get((trade_date, asset_id))
        growth_row = growth_by_asset.get(asset_id)
        signal = _reentry_signal(config=config, watch=watch, score=score, growth_row=growth_row)
        if not signal["qualified"]:
            continue
        if asset_id in selected_assets:
            event_rows.append(
                _reentry_event_row(
                    variant_name=config.variant_name,
                    asset_id=asset_id,
                    trade_date=trade_date,
                    watch=watch,
                    score=score,
                    growth_row=growth_row,
                    reentry_mode=config.reentry_mode,
                    action_taken="skip_already_selected",
                    skip_reason="already_selected",
                )
            )
            continue
        eligible.append({"asset_id": asset_id, "watch": watch, "score": score, "growth_row": growth_row})

    eligible.sort(
        key=lambda item: (
            _num(getattr(item["growth_row"], "candidate_rank", np.nan)),
            -_num(getattr(item["growth_row"], "mid_trend_funnel_score", np.nan)),
            str(item["asset_id"]),
        )
    )

    if config.reentry_mode == "strict_top10_reentry":
        capacity = max(0, TOP10_REENTRY_CAP - len(selected_assets))
        for index, item in enumerate(eligible):
            if index >= capacity:
                event_rows.append(
                    _reentry_event_row(
                        variant_name=config.variant_name,
                        asset_id=str(item["asset_id"]),
                        trade_date=trade_date,
                        watch=item["watch"],
                        score=item["score"],
                        growth_row=item["growth_row"],
                        reentry_mode=config.reentry_mode,
                        action_taken="skip_no_slot",
                        skip_reason="no_slot",
                    )
                )
                continue
            final_selected = pd.concat(
                [
                    final_selected,
                    _reentry_selection_frame(
                        trade_date=trade_date,
                        item=item,
                        reentry_mode=config.reentry_mode,
                    ),
                ],
                ignore_index=True,
            )
            event_rows.append(
                _reentry_event_row(
                    variant_name=config.variant_name,
                    asset_id=str(item["asset_id"]),
                    trade_date=trade_date,
                    watch=item["watch"],
                    score=item["score"],
                    growth_row=item["growth_row"],
                    reentry_mode=config.reentry_mode,
                    action_taken="executed_reentry_signal",
                    skip_reason="",
                )
            )
    elif config.reentry_mode == "strict_top20_reentry":
        replacements = 0
        for item in eligible:
            if replacements >= config.max_reentry_slots:
                event_rows.append(
                    _reentry_event_row(
                        variant_name=config.variant_name,
                        asset_id=str(item["asset_id"]),
                        trade_date=trade_date,
                        watch=item["watch"],
                        score=item["score"],
                        growth_row=item["growth_row"],
                        reentry_mode=config.reentry_mode,
                        action_taken="skip_no_slot",
                        skip_reason="no_slot",
                    )
                )
                continue
            weakest_idx = _weakest_selected_index(final_selected)
            weakest = final_selected.iloc[weakest_idx]
            weakest_score = score_by_key.get((trade_date, str(weakest["asset_id"])))
            if not _candidate_beats_selected(candidate_score=item["score"], selected_score=weakest_score):
                event_rows.append(
                    _reentry_event_row(
                        variant_name=config.variant_name,
                        asset_id=str(item["asset_id"]),
                        trade_date=trade_date,
                        watch=item["watch"],
                        score=item["score"],
                        growth_row=item["growth_row"],
                        reentry_mode=config.reentry_mode,
                        action_taken="skip_weaker_than_selected",
                        skip_reason="weaker_than_selected",
                    )
                )
                continue
            final_selected = final_selected.drop(index=weakest_idx).reset_index(drop=True)
            final_selected = pd.concat(
                [
                    final_selected,
                    _reentry_selection_frame(
                        trade_date=trade_date,
                        item=item,
                        reentry_mode=config.reentry_mode,
                    ),
                ],
                ignore_index=True,
            )
            replacements += 1
            event_rows.append(
                _reentry_event_row(
                    variant_name=config.variant_name,
                    asset_id=str(item["asset_id"]),
                    trade_date=trade_date,
                    watch=item["watch"],
                    score=item["score"],
                    growth_row=item["growth_row"],
                    reentry_mode=config.reentry_mode,
                    action_taken="executed_reentry_signal",
                    skip_reason="",
                )
            )
    return final_selected, event_rows


def _reentry_signal(
    *,
    config: Top10ReentryVariantConfig,
    watch: dict[str, Any],
    score: Any,
    growth_row: Any,
) -> dict[str, Any]:
    rank = _num(getattr(growth_row, "candidate_rank", np.nan)) if growth_row is not None else np.nan
    if growth_row is None or score is None or np.isnan(rank):
        return {"qualified": False}
    if not bool(getattr(score, "technical_confirmed", False)):
        return {"qualified": False}
    if not bool(getattr(score, "mainline_confirmed", False)):
        return {"qualified": False}
    if str(getattr(score, "fundamental_quality_bucket", "quality_unknown")) == "quality_weak":
        return {"qualified": False}
    if not str(getattr(score, "midtrend_confirmation_state", "")).startswith("T1_M1"):
        return {"qualified": False}
    if _hard_damage_score(score):
        return {"qualified": False}
    if int(config.cooldown_days) > 0:
        watch_start = pd.to_datetime(watch.get("watch_start_date"), errors="coerce")
        current_date = pd.to_datetime(getattr(score, "trade_date", pd.NaT), errors="coerce")
        if pd.notna(watch_start) and pd.notna(current_date):
            if int((current_date - watch_start).days) < int(config.cooldown_days):
                return {"qualified": False}
    if config.block_high_elasticity_without_strong_mainline:
        layer = str(getattr(score, "mid_trend_layer", "") or "")
        mainline_status = str(getattr(score, "mainline_status", "") or "")
        if layer == "high_elasticity_watch" and mainline_status not in {
            "sustained_mainline",
            "overheated_mainline",
            "strong_mainline",
        }:
            return {"qualified": False}
    if config.min_stock_excess_ret_20_score is not None:
        if _num(getattr(score, "stock_excess_ret_20_score", np.nan)) < float(config.min_stock_excess_ret_20_score):
            return {"qualified": False}
    if config.min_max_drawdown_20_score is not None:
        if _num(getattr(score, "max_drawdown_20_score", np.nan)) < float(config.min_max_drawdown_20_score):
            return {"qualified": False}
    rank_cap = config.reentry_rank_cap
    if config.reentry_mode == "strict_top10_reentry":
        rank_cap = 10 if rank_cap is None else rank_cap
        rank_ok = rank <= rank_cap
        score_ok = True if not config.require_score_improvement else _num(getattr(score, "mid_trend_funnel_score", np.nan)) > float(watch.get("exit_score", np.nan) or np.nan)
        rank_improved = True if not config.require_rank_improvement else rank < float(watch.get("exit_rank", np.inf) or np.inf)
        return {"qualified": rank_ok and score_ok and rank_improved}
    improved_rank = rank < float(watch.get("exit_rank", np.inf) or np.inf)
    improved_score = _num(getattr(score, "mid_trend_funnel_score", np.nan)) > float(watch.get("exit_score", np.nan) or np.nan)
    rank_cap = TOP20_REENTRY_THRESHOLD if rank_cap is None else rank_cap
    if config.require_rank_improvement and not improved_rank:
        return {"qualified": False}
    if config.require_score_improvement and not improved_score:
        return {"qualified": False}
    improvement_ok = (improved_rank or improved_score) if (config.require_rank_improvement or config.require_score_improvement) else True
    return {"qualified": rank <= rank_cap and improvement_ok}


def _hard_damage_score(score: Any) -> bool:
    if score is None:
        return False
    return bool(
        str(getattr(score, "mid_trend_layer", "")) == "risk_exclusion_watch"
        or bool(getattr(score, "fundamental_risk_flag", False))
    )


def _candidate_beats_selected(*, candidate_score: Any, selected_score: Any) -> bool:
    candidate_rank = _num(getattr(candidate_score, "score_rank", np.nan)) if candidate_score is not None else np.nan
    selected_rank = _num(getattr(selected_score, "score_rank", np.nan)) if selected_score is not None else np.nan
    candidate_funnel = _num(getattr(candidate_score, "mid_trend_funnel_score", np.nan)) if candidate_score is not None else np.nan
    selected_funnel = _num(getattr(selected_score, "mid_trend_funnel_score", np.nan)) if selected_score is not None else np.nan
    candidate_state = str(getattr(candidate_score, "midtrend_confirmation_state", "") or "")
    selected_state = str(getattr(selected_score, "midtrend_confirmation_state", "") or "")
    if candidate_state.startswith("T1_M1") and not selected_state.startswith("T1_M1"):
        return True
    if not np.isnan(candidate_funnel) and not np.isnan(selected_funnel) and candidate_funnel > selected_funnel:
        return True
    return not np.isnan(candidate_rank) and not np.isnan(selected_rank) and candidate_rank < selected_rank


def _weakest_selected_index(selected: pd.DataFrame) -> int:
    order = selected.copy()
    order["candidate_rank"] = pd.to_numeric(order.get("candidate_rank"), errors="coerce")
    order["growth_rank_score"] = pd.to_numeric(order.get("growth_rank_score"), errors="coerce")
    weakest = order.sort_values(
        ["candidate_rank", "growth_rank_score", "asset_id"],
        ascending=[False, True, True],
    ).index[0]
    return int(weakest)


def _reentry_selection_frame(*, trade_date: str, item: dict[str, Any], reentry_mode: str) -> pd.DataFrame:
    growth_row = item["growth_row"]
    return pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_id": str(item["asset_id"]),
                "candidate_rank": _num(getattr(growth_row, "candidate_rank", np.nan)),
                "growth_rank_score": _num(getattr(growth_row, "growth_rank_score", np.nan)),
                "selection_source": "reentry",
                "reentry_mode": reentry_mode,
                "watch_start_date": str(item["watch"]["watch_start_date"]),
            }
        ]
    )


def _reentry_event_row(
    *,
    variant_name: str,
    asset_id: str,
    trade_date: str,
    watch: dict[str, Any],
    score: Any,
    growth_row: Any,
    reentry_mode: str,
    action_taken: str,
    skip_reason: str,
) -> dict[str, Any]:
    return {
        "variant_name": variant_name,
        "watch_start_date": str(watch.get("watch_start_date", "")),
        "reentry_date": trade_date,
        "asset_id": asset_id,
        "stock_name": str(watch.get("stock_name", "")),
        "industry_name": str(watch.get("industry_name", "")),
        "exit_rank": watch.get("exit_rank"),
        "reentry_rank": _num(getattr(growth_row, "candidate_rank", np.nan)) if growth_row is not None else np.nan,
        "exit_score": watch.get("exit_score"),
        "reentry_score": _num(getattr(score, "mid_trend_funnel_score", np.nan)) if score is not None else np.nan,
        "technical_confirmed_on_reentry": bool(getattr(score, "technical_confirmed", False)) if score is not None else False,
        "mainline_confirmed_on_reentry": bool(getattr(score, "mainline_confirmed", False)) if score is not None else False,
        "fundamental_quality_bucket_on_reentry": str(getattr(score, "fundamental_quality_bucket", "quality_unknown")) if score is not None else "quality_unknown",
        "midtrend_confirmation_state_on_reentry": str(getattr(score, "midtrend_confirmation_state", "")) if score is not None else "",
        "reentry_mode": reentry_mode,
        "action_taken": action_taken,
        "skip_reason": skip_reason,
        "holding_days_after_reentry": np.nan,
        "return_after_reentry": np.nan,
        "contribution_after_reentry": np.nan,
    }


def _build_reentry_trade_contribution(
    *,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    event_log: pd.DataFrame,
    price_state: dict[str, Any],
    end_return_lookup: dict[tuple[str, str], float],
    variant_name: str,
) -> pd.DataFrame:
    if trades.empty or event_log.empty:
        return pd.DataFrame(columns=_reentry_trade_columns())
    buy_like = trades[trades["action"].astype(str).isin(["buy", "increase"])].copy()
    executed = event_log[event_log["action_taken"].astype(str).eq("executed_reentry_signal")].copy()
    merged = buy_like.merge(
        executed,
        left_on=["trade_date", "asset_id"],
        right_on=["reentry_date", "asset_id"],
        how="inner",
        suffixes=("", "_event"),
    )
    if merged.empty:
        return pd.DataFrame(columns=_reentry_trade_columns())
    merged["return_after_reentry"] = merged.apply(
        lambda row: end_return_lookup.get((str(row["trade_date"]), str(row["asset_id"])), np.nan),
        axis=1,
    )
    merged["contribution_after_reentry"] = (
        pd.to_numeric(merged["target_weight"], errors="coerce").fillna(0.0)
        * pd.to_numeric(merged["return_after_reentry"], errors="coerce").fillna(0.0)
    )
    for horizon in REENTRY_FORWARD_WINDOWS:
        merged[f"forward_return_after_reentry_{horizon}d"] = merged.apply(
            lambda row: _price_horizon_return(price_state, str(row["trade_date"]), str(row["asset_id"]), horizon),
            axis=1,
        )
    failed = merged[
        [f"forward_return_after_reentry_{horizon}d" for horizon in REENTRY_FORWARD_WINDOWS]
    ].min(axis=1)
    merged["failed_reentry_loss"] = failed
    merged["variant_name"] = variant_name
    return merged[_reentry_trade_columns()].copy()


def _exit_meta(
    *,
    asset_id: str,
    trade_date: str,
    score_by_key: dict[tuple[str, str], Any],
    growth_day: pd.DataFrame,
) -> dict[str, Any]:
    score = score_by_key.get((trade_date, asset_id))
    growth_row = growth_day[growth_day["asset_id"].astype(str).eq(asset_id)]
    rank = np.nan if growth_row.empty else _num(growth_row.iloc[0]["candidate_rank"])
    return {
        "exit_rank": rank,
        "exit_score": _num(getattr(score, "mid_trend_funnel_score", np.nan)) if score is not None else np.nan,
        "stock_name": str(getattr(score, "stock_name", asset_id)) if score is not None else asset_id,
        "industry_name": str(getattr(score, "industry_name", "")) if score is not None else "",
    }


def _reentry_variant_summary(item: dict[str, Any]) -> dict[str, Any]:
    base = _variant_summary(item)
    base["reentry_mode"] = item.get("reentry_mode", "none")
    base["max_reentry_slots"] = int(item.get("max_reentry_slots", 0))
    lifecycle = item.get("watch_lifecycle", pd.DataFrame())
    event_log = item.get("reentry_event_log", pd.DataFrame())
    trades = item.get("reentry_trade_contribution", pd.DataFrame())
    ranking = _ranking_churn_row(item)
    base["ranking_churn_sell_count"] = int(ranking["ranking_churn_sell_count"])
    base["hard_damage_sell_count"] = int(ranking["hard_damage_sell_count"])
    base["watch_pool_entries"] = int(lifecycle["event_type"].astype(str).eq("watch_start").sum()) if not lifecycle.empty else 0
    base["expired_watch_count"] = int(
        (
            lifecycle["event_type"].astype(str).eq("watch_removed")
            & lifecycle["reason"].astype(str).eq("expired")
        ).sum()
    ) if not lifecycle.empty else 0
    base["reentry_signal_count"] = int(len(event_log))
    base["executed_reentry_count"] = int(event_log["action_taken"].astype(str).eq("executed_reentry_signal").sum()) if not event_log.empty else 0
    base["skipped_reentry_already_selected_count"] = int(event_log["skip_reason"].astype(str).eq("already_selected").sum()) if not event_log.empty else 0
    base["skipped_reentry_no_slot_count"] = int(event_log["skip_reason"].astype(str).eq("no_slot").sum()) if not event_log.empty else 0
    base["skipped_reentry_weaker_than_selected_count"] = int(event_log["skip_reason"].astype(str).eq("weaker_than_selected").sum()) if not event_log.empty else 0
    days_to_reentry = []
    if not event_log.empty:
        days_to_reentry = (
            pd.to_datetime(event_log["reentry_date"], errors="coerce")
            - pd.to_datetime(event_log["watch_start_date"], errors="coerce")
        ).dt.days.dropna().tolist()
    base["avg_days_to_reentry"] = float(np.mean(days_to_reentry)) if days_to_reentry else 0.0
    base["reentry_trade_count"] = int(len(trades))
    base["reentry_win_rate"] = float(pd.to_numeric(trades.get("return_after_reentry"), errors="coerce").gt(0).mean()) if not trades.empty else 0.0
    base["reentry_avg_return"] = float(pd.to_numeric(trades.get("return_after_reentry"), errors="coerce").mean()) if not trades.empty else 0.0
    for horizon in REENTRY_FORWARD_WINDOWS:
        base[f"reentry_forward_return_{horizon}d"] = float(
            pd.to_numeric(trades.get(f"forward_return_after_reentry_{horizon}d"), errors="coerce").mean()
        ) if not trades.empty else 0.0
    base["failed_reentry_loss"] = float(pd.to_numeric(trades.get("failed_reentry_loss"), errors="coerce").mean()) if not trades.empty else 0.0
    base["reentry_contribution"] = float(pd.to_numeric(trades.get("contribution_after_reentry"), errors="coerce").sum()) if not trades.empty else 0.0
    return base


def _attach_incremental_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    result = summary.copy()
    reference_names = {
        5: "baseline_top5",
        8: "top8_reference",
        10: "top10_reference",
    }
    by_name = result.set_index("variant_name")
    increments_return = []
    increments_drawdown = []
    for row in result.itertuples(index=False):
        reference_name = reference_names.get(int(row.final_top_n), "")
        if not reference_name or row.variant_name == reference_name:
            increments_return.append(0.0)
            increments_drawdown.append(0.0)
            continue
        if reference_name not in by_name.index:
            increments_return.append(np.nan)
            increments_drawdown.append(np.nan)
            continue
        reference = by_name.loc[reference_name]
        increments_return.append(float(row.total_return) - float(reference["total_return"]))
        increments_drawdown.append(float(row.max_drawdown) - float(reference["max_drawdown"]))
    result["incremental_return_vs_same_topn_no_reentry"] = increments_return
    result["incremental_drawdown_vs_same_topn_no_reentry"] = increments_drawdown
    return result


def _top10_reproduction_note(summary: pd.DataFrame) -> dict[str, float | str]:
    expected_return = 1.936340
    expected_drawdown = -0.173634
    top10 = summary[summary["variant_name"].astype(str).eq("top10_reference")]
    if top10.empty:
        return {"status": "missing", "return_diff": np.nan, "drawdown_diff": np.nan}
    row = top10.iloc[0]
    return {
        "status": "matched" if abs(float(row["total_return"]) - expected_return) < 1e-4 and abs(float(row["max_drawdown"]) - expected_drawdown) < 1e-4 else "mismatch",
        "return_diff": float(row["total_return"]) - expected_return,
        "drawdown_diff": float(row["max_drawdown"]) - expected_drawdown,
    }


def _code_audit(summary: pd.DataFrame, reproduction_note: dict[str, float | str]) -> str:
    lines = [
        "# Code Audit",
        "",
        "- baseline entrypoint: `stock_research.current_mid_trend_strategy_v1.build_current_mid_trend_strategy_v1_from_frames`",
        "- new experiment runner: `stock_research.midtrend_top10_reentry_experiment`",
        "- unchanged baseline knobs: `top_n=5`, `C2_atr2p5_rank20`, `atr_multiple=2.5`, `score_break_rank=20`, `rank_break_days=1`, `score_decline_days=2`",
        "- top10 reference uses the same protection and regime exposure logic as baseline; only `final_top_n=10` changes",
        "- strict re-entry is post-exit only; it does not suppress exits and does not behave as generic carry",
        "- strict_top10_reentry assumption: holdings may expand up to 10 total names for `top5`/`top8` variants, because otherwise the layer collapses into plain replacement and becomes indistinguishable from top_n expansion",
        f"- top10 reproduction status: {reproduction_note['status']}",
        f"- top10 reproduction total_return diff vs previous sweep: {float(reproduction_note['return_diff']) if reproduction_note['return_diff'] == reproduction_note['return_diff'] else float('nan'):.6f}",
        f"- top10 reproduction max_drawdown diff vs previous sweep: {float(reproduction_note['drawdown_diff']) if reproduction_note['drawdown_diff'] == reproduction_note['drawdown_diff'] else float('nan'):.6f}",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(
    summary: pd.DataFrame,
    ranking_churn: pd.DataFrame,
    reentry_trade_contribution: pd.DataFrame,
    reproduction_note: dict[str, float | str],
) -> str:
    by_name = summary.set_index("variant_name")

    def _metric(name: str, column: str, default: float = 0.0) -> float:
        if name not in by_name.index:
            return default
        value = by_name.loc[name][column]
        return float(value) if pd.notna(value) else default

    top10_ref = _metric("top10_reference", "total_return")
    baseline = _metric("baseline_top5", "total_return")
    top5_reentry = _metric("top5_strict_top10_reentry", "incremental_return_vs_same_topn_no_reentry")
    top8_reentry = _metric("top8_strict_top10_reentry", "incremental_return_vs_same_topn_no_reentry")
    top10_reentry = _metric("top10_strict_top10_reentry", "incremental_return_vs_same_topn_no_reentry")
    top10_top20 = _metric("top10_strict_top20_reentry_slot1", "incremental_return_vs_same_topn_no_reentry")
    lines = [
        "# Final Interpretation",
        "",
        f"1. Does clean top10_reference reproduce the previous top10 result? {reproduction_note['status']}.",
        f"2. Should top10 replace top5 as the next Mid Trend candidate baseline? {'yes' if top10_ref > baseline else 'no'}.",
        f"3. Does strict_top10_reentry add value to top5? {'yes' if top5_reentry > 0 else 'no'}.",
        f"4. Does strict_top10_reentry add value to top8? {'yes' if top8_reentry > 0 else 'no'}.",
        f"5. Does strict_top10_reentry add value to top10, or is it redundant because normal top10 selection already buys the stock back? {'redundant' if abs(top10_reentry) < 1e-9 else 'adds value'}.",
        f"6. Does strict_top20_reentry_slot1 add incremental value on top of top10? {'yes' if top10_top20 > 0 else 'no'}.",
        f"7. Are re-entry trades profitable after execution, not just before execution? {'yes' if not reentry_trade_contribution.empty and float(pd.to_numeric(reentry_trade_contribution['return_after_reentry'], errors='coerce').mean()) > 0 else 'no'}.",
        f"8. Is failed_reentry_loss controlled? {'yes' if not reentry_trade_contribution.empty and float(pd.to_numeric(reentry_trade_contribution['failed_reentry_loss'], errors='coerce').mean()) > -0.03 else 'no'}.",
        f"9. Does re-entry increase turnover too much? Compare `turnover` in [baseline_vs_top10_reentry_variants.csv](/Users/xiwei/stock_research/outputs/research/midtrend_top10_reentry_experiment_20260626/baseline_vs_top10_reentry_variants.csv).",
        f"10. Does re-entry worsen max_drawdown? Compare `incremental_drawdown_vs_same_topn_no_reentry` in the same table.",
        "11. Does re-entry reduce ranking churn damage without becoming generic hold? Use `ranking_churn_comparison.csv` and the re-entry event log together.",
        f"12. Should the next real strategy candidate be: {'top10 + strict_top20_reentry_slot1' if top10_top20 > 0 else 'top10 only' if top10_ref > baseline else 'keep top5 baseline'}.",
    ]
    return "\n".join(lines) + "\n"


def _reentry_event_columns() -> list[str]:
    return [
        "variant_name",
        "watch_start_date",
        "reentry_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "exit_rank",
        "reentry_rank",
        "exit_score",
        "reentry_score",
        "technical_confirmed_on_reentry",
        "mainline_confirmed_on_reentry",
        "fundamental_quality_bucket_on_reentry",
        "midtrend_confirmation_state_on_reentry",
        "reentry_mode",
        "action_taken",
        "skip_reason",
        "holding_days_after_reentry",
        "return_after_reentry",
        "contribution_after_reentry",
    ]


def _reentry_trade_columns() -> list[str]:
    return [
        "variant_name",
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "target_weight",
        "return_after_reentry",
        "contribution_after_reentry",
        "forward_return_after_reentry_5d",
        "forward_return_after_reentry_10d",
        "forward_return_after_reentry_20d",
        "failed_reentry_loss",
    ]


def _watch_lifecycle_columns() -> list[str]:
    return [
        "variant_name",
        "asset_id",
        "event_date",
        "event_type",
        "reason",
        "watch_start_date",
    ]
