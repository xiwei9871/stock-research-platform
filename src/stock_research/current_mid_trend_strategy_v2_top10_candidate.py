from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices
from stock_research.current_mid_trend_strategy_v1 import (
    _build_holding_summary,
    _build_industry_exposure,
    _period_summary,
)
from stock_research.market_style_switch_v1 import _filter_date_range
from stock_research.midtrend_topn_pool_reentry_sweep import (
    TopNPoolVariantConfig,
    _build_end_return_lookup,
    _build_enriched_funnel,
    _build_growth_rank_frame,
    _build_price_state,
    _run_topn_pool_variant,
)

DEFAULT_REGIME_PATH = (
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260612_retest/"
    "market_regime_confirmation_daily.csv"
)
DEFAULT_FUNNEL_DETAIL_PATH = (
    "outputs/research/mid_trend_watch_funnel_20250101_20260612_retest/"
    "mid_trend_watch_funnel_detail.csv"
)


def build_current_mid_trend_strategy_v2_top10_candidate_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    enriched_funnel = _build_enriched_funnel(funnel, start_date=start_date, end_date=end_date)
    growth_all = _build_growth_rank_frame(enriched_funnel, start_date=start_date, end_date=end_date)
    price_state = _build_price_state(prices)
    end_return_lookup = _build_end_return_lookup(prices)
    result = _run_topn_pool_variant(
        regime=regime,
        funnel=enriched_funnel,
        growth_all=growth_all,
        prices=prices,
        price_state=price_state,
        end_return_lookup=end_return_lookup,
        start_date=start_date,
        end_date=end_date,
        config=TopNPoolVariantConfig(
            variant_name="current_mid_trend_strategy_v2_top10_candidate",
            final_top_n=10,
            candidate_pool_size=10,
        ),
    )
    result["holding_summary"] = _build_holding_summary(result["holdings"], _filter_date_range(regime, start_date, end_date))
    result["annual"] = _period_summary(result["equity"], "Y")
    result["quarterly"] = _period_summary(result["equity"], "Q")
    result["industry_exposure"] = _build_industry_exposure(result["holdings"])
    result["protection_events"] = result["holdings"][result["holdings"]["protection_reason"].astype(str).ne("")].copy()
    if output_dir is not None:
        paths = _write_top10_outputs(output_dir, result)
    else:
        paths = {}
    result["paths"] = paths
    result["top_n"] = 10
    return result


def run_current_mid_trend_strategy_v2_top10_candidate_backtest(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    regime = pd.read_csv(regime_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    asset_ids = sorted(funnel["asset_id"].dropna().astype(str).unique().tolist())
    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=asset_ids,
        adjust_type=adjust_type,
    )
    return build_current_mid_trend_strategy_v2_top10_candidate_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def _write_top10_outputs(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    prefix = "current_mid_trend_strategy_v2_top10_candidate"
    paths = {
        "equity": output / f"{prefix}_equity.csv",
        "summary": output / f"{prefix}_summary.csv",
        "holdings": output / f"{prefix}_daily_holdings.csv",
        "trades": output / f"{prefix}_trade_changes.csv",
        "holding_summary": output / f"{prefix}_daily_holding_summary.csv",
        "annual": output / f"{prefix}_annual_summary.csv",
        "quarterly": output / f"{prefix}_quarterly_summary.csv",
        "industry_exposure": output / f"{prefix}_industry_exposure.csv",
        "protection_events": output / f"{prefix}_protection_events.csv",
        "params": output / f"{prefix}_run_params.csv",
        "report": output / f"{prefix}_report.md",
    }
    result["equity"].to_csv(paths["equity"], index=False)
    result["summary"].to_csv(paths["summary"], index=False)
    result["holdings"].to_csv(paths["holdings"], index=False)
    result["trades"].to_csv(paths["trades"], index=False)
    result["holding_summary"].to_csv(paths["holding_summary"], index=False)
    result["annual"].to_csv(paths["annual"], index=False)
    result["quarterly"].to_csv(paths["quarterly"], index=False)
    result["industry_exposure"].to_csv(paths["industry_exposure"], index=False)
    result["protection_events"].to_csv(paths["protection_events"], index=False)
    pd.DataFrame(
        [
            {"key": "strategy", "value": prefix},
            {"key": "start_date", "value": result["holdings"]["trade_date"].min() if not result["holdings"].empty else ""},
            {"key": "end_date", "value": result["holdings"]["trade_date"].max() if not result["holdings"].empty else ""},
            {"key": "top_n", "value": 10},
            {"key": "stock_protection_variant", "value": "C2_atr2p5_rank20"},
        ]
    ).to_csv(paths["params"], index=False)
    paths["report"].write_text(
        "\n".join(
            [
                "# Current Mid Trend Strategy V2 Top10 Candidate",
                "",
                "- final_top_n: 10",
                "- candidate_pool_size: 10",
                "- protection: C2_atr2p5_rank20",
                "",
                result["summary"].to_markdown(index=False) if not result["summary"].empty else "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return paths
