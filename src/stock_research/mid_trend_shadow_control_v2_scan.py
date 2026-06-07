from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


@dataclass(frozen=True)
class ControlV2Rule:
    variant_name: str
    sell_buffer_rank: int | None = None
    freeze_replacement_limit: int | None = None


DEFAULT_RULES = [
    ControlV2Rule("baseline_max2"),
    ControlV2Rule("sell_buffer_top8", sell_buffer_rank=8),
    ControlV2Rule("sell_buffer_top10", sell_buffer_rank=10),
    ControlV2Rule("drawdown_freeze_to_1", freeze_replacement_limit=1),
    ControlV2Rule("drawdown_freeze_to_0", freeze_replacement_limit=0),
    ControlV2Rule("sell_buffer_top10_freeze_to_1", sell_buffer_rank=10, freeze_replacement_limit=1),
]


def run_mid_trend_shadow_control_v2_scan(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    top_n: int = 5,
    base_max_replacements: int = 2,
    drawdown_threshold: float = 0.08,
    drawdown_worsen_threshold: float = 0.03,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_mid_trend_shadow_control_v2_scan_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n=top_n,
        base_max_replacements=base_max_replacements,
        drawdown_threshold=drawdown_threshold,
        drawdown_worsen_threshold=drawdown_worsen_threshold,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_shadow_control_v2_scan_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n: int = 5,
    base_max_replacements: int = 2,
    drawdown_threshold: float = 0.08,
    drawdown_worsen_threshold: float = 0.03,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    max_rank = 10
    signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max_rank)["top10"]
    scoped_prices = _prices_for_shadow(prices, signals)
    results = [
        _simulate_rule(
            rule,
            signals,
            scoped_prices,
            start_date=start_date,
            end_date=end_date,
            top_n=top_n,
            base_max_replacements=base_max_replacements,
            drawdown_threshold=drawdown_threshold,
            drawdown_worsen_threshold=drawdown_worsen_threshold,
            transaction_cost_bps=transaction_cost_bps,
        )
        for rule in DEFAULT_RULES
    ]
    equity_curve = pd.concat([item["equity_curve"] for item in results], ignore_index=True)
    positions = pd.concat([item["positions"] for item in results], ignore_index=True)
    trades = pd.concat([item["trades"] for item in results], ignore_index=True)
    summary = pd.DataFrame([item["summary"] for item in results])
    summary["adjust_type"] = adjust_type
    summary = _rank_summary(summary)
    report = _render_report(summary)

    result: dict[str, Any] = {
        "summary": summary,
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_shadow_control_v2_summary.csv",
            "equity_curve": output / "mid_trend_shadow_control_v2_equity.csv",
            "positions": output / "mid_trend_shadow_control_v2_positions.csv",
            "trades": output / "mid_trend_shadow_control_v2_trades.csv",
            "report": output / "mid_trend_shadow_control_v2_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        equity_curve.to_csv(paths["equity_curve"], index=False)
        positions.to_csv(paths["positions"], index=False)
        trades.to_csv(paths["trades"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _simulate_rule(
    rule: ControlV2Rule,
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    top_n: int,
    base_max_replacements: int,
    drawdown_threshold: float,
    drawdown_worsen_threshold: float,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    normalized_signals = _normalize_signals(signals, start_date, end_date)
    close = _close_matrix(prices, start_date, end_date)
    weekly_dates = set(_weekly_signal_dates(normalized_signals, list(close.index)))
    current_weights: dict[str, float] = {}
    equity = 1.0
    high_water = 1.0
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    cost_rate = float(transaction_cost_bps) / 10000.0

    for index, trade_date in enumerate(close.index):
        if index > 0 and current_weights:
            prev_date = close.index[index - 1]
            returns = close.loc[trade_date] / close.loc[prev_date] - 1.0
            gross_return = float(
                sum(current_weights.get(asset, 0.0) * returns.get(asset, 0.0) for asset in current_weights)
            )
            equity *= 1.0 + gross_return
        else:
            gross_return = 0.0

        high_water = max(high_water, equity)
        current_drawdown = equity / high_water - 1.0 if high_water else 0.0
        is_freeze = _freeze_condition(
            equity_rows,
            current_drawdown=current_drawdown,
            drawdown_threshold=drawdown_threshold,
            drawdown_worsen_threshold=drawdown_worsen_threshold,
        )
        turnover = 0.0
        if trade_date in weekly_dates:
            max_replacements = (
                rule.freeze_replacement_limit
                if is_freeze and rule.freeze_replacement_limit is not None
                else base_max_replacements
            )
            target_assets = _target_assets(
                normalized_signals,
                trade_date=trade_date,
                current_assets=list(current_weights),
                top_n=top_n,
                max_replacements=max_replacements,
                sell_buffer_rank=rule.sell_buffer_rank,
            )
            target = _equal_weights(target_assets)
            turnover = _turnover(current_weights, target)
            trade_rows.extend(
                _trade_rows(
                    rule.variant_name,
                    trade_date,
                    current_weights,
                    target,
                    reason="weekly_rebalance_freeze" if is_freeze else "weekly_rebalance",
                    cost_rate=cost_rate,
                )
            )
            current_weights = target
            position_rows.extend(
                {
                    "variant_name": rule.variant_name,
                    "rebalance_date": trade_date,
                    "asset_id": asset,
                    "weight": weight,
                    "freeze_active": is_freeze,
                }
                for asset, weight in current_weights.items()
            )

        transaction_cost = turnover * cost_rate
        equity *= 1.0 - transaction_cost
        high_water = max(high_water, equity)
        drawdown = equity / high_water - 1.0 if high_water else 0.0
        equity_rows.append(
            {
                "variant_name": rule.variant_name,
                "date": trade_date,
                "gross_return": gross_return,
                "turnover": turnover,
                "transaction_cost": transaction_cost,
                "net_return": gross_return - transaction_cost,
                "equity": equity,
                "drawdown": drawdown,
                "holdings_count": len(current_weights),
                "freeze_active": is_freeze,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    positions = pd.DataFrame(position_rows)
    trades = pd.DataFrame(trade_rows)
    return {
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "summary": _summary_row(
            rule,
            equity_curve,
            positions=positions,
            trades=trades,
            top_n=top_n,
            transaction_cost_bps=transaction_cost_bps,
        ),
    }


def _normalize_signals(signals: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "shadow_top10_rank", "trend_r2_20_score"])
    frame = signals.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["shadow_top10_rank"] = pd.to_numeric(frame["shadow_top10_rank"], errors="coerce")
    if "trend_r2_20_score" not in frame.columns:
        frame["trend_r2_20_score"] = np.nan
    frame["trend_r2_20_score"] = pd.to_numeric(frame["trend_r2_20_score"], errors="coerce")
    return frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["trade_date", "asset_id", "shadow_top10_rank"])


def _close_matrix(prices: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].dropna(subset=["trade_date", "asset_id", "close"])
    return frame.pivot_table(index="trade_date", columns="asset_id", values="close", aggfunc="last").sort_index()


def _weekly_signal_dates(signals: pd.DataFrame, trading_dates: list[str]) -> list[str]:
    if signals.empty:
        return []
    signal_dates = set(signals["trade_date"].astype(str))
    available = [date for date in trading_dates if date in signal_dates]
    weekly = []
    seen = set()
    for date in available:
        iso = pd.Timestamp(date).isocalendar()
        key = (int(iso.year), int(iso.week))
        if key not in seen:
            weekly.append(date)
            seen.add(key)
    return weekly


def _freeze_condition(
    equity_rows: list[dict[str, Any]],
    *,
    current_drawdown: float,
    drawdown_threshold: float,
    drawdown_worsen_threshold: float,
) -> bool:
    if current_drawdown <= -abs(drawdown_threshold):
        return True
    if len(equity_rows) >= 10:
        previous = float(equity_rows[-10]["drawdown"])
        if current_drawdown < previous - abs(drawdown_worsen_threshold):
            return True
    return False


def _target_assets(
    signals: pd.DataFrame,
    *,
    trade_date: str,
    current_assets: list[str],
    top_n: int,
    max_replacements: int,
    sell_buffer_rank: int | None,
) -> list[str]:
    day = signals[signals["trade_date"].eq(trade_date)].sort_values("shadow_top10_rank")
    ordered = day["asset_id"].astype(str).tolist()
    top_assets = ordered[:top_n]
    desired = set(top_assets)
    keep = [asset for asset in current_assets if asset in desired]
    stale = [asset for asset in current_assets if asset not in desired]
    if sell_buffer_rank is not None and stale:
        buffer_assets = set(ordered[:sell_buffer_rank])
        healthy_assets = _healthy_assets(day)
        buffered = [asset for asset in stale if asset in buffer_assets and asset in healthy_assets]
        keep.extend(buffered)
        stale = [asset for asset in stale if asset not in set(buffered)]
    allowed_keep_stale = stale[max_replacements:]
    return _fill_to_top_n(keep + allowed_keep_stale, ordered, top_n)


def _healthy_assets(day: pd.DataFrame) -> set[str]:
    if "trend_r2_20_score" not in day.columns:
        return set(day["asset_id"].astype(str))
    healthy = day[pd.to_numeric(day["trend_r2_20_score"], errors="coerce").ge(60)]
    return set(healthy["asset_id"].astype(str))


def _fill_to_top_n(kept: list[str], ordered: list[str], top_n: int) -> list[str]:
    result = []
    for asset in kept + ordered:
        if asset not in result:
            result.append(asset)
        if len(result) >= top_n:
            break
    return result


def _equal_weights(assets: list[str]) -> dict[str, float]:
    if not assets:
        return {}
    weight = 1.0 / len(assets)
    return {asset: weight for asset in assets}


def _turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return float(sum(abs(float(target.get(asset, 0.0)) - float(previous.get(asset, 0.0))) for asset in assets))


def _trade_rows(
    variant_name: str,
    trade_date: str,
    previous: dict[str, float],
    target: dict[str, float],
    *,
    reason: str,
    cost_rate: float,
) -> list[dict[str, Any]]:
    rows = []
    for asset in sorted(set(previous) | set(target)):
        prev = float(previous.get(asset, 0.0))
        nxt = float(target.get(asset, 0.0))
        if abs(nxt - prev) < 1e-12:
            continue
        rows.append(
            {
                "variant_name": variant_name,
                "trade_date": trade_date,
                "asset_id": asset,
                "side": "buy" if nxt > prev else "sell",
                "previous_weight": prev,
                "target_weight": nxt,
                "delta_weight": nxt - prev,
                "turnover_contribution": abs(nxt - prev),
                "transaction_cost": abs(nxt - prev) * cost_rate,
                "reason": reason,
            }
        )
    return rows


def _summary_row(
    rule: ControlV2Rule,
    equity: pd.DataFrame,
    *,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    top_n: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    if equity.empty:
        return {"variant_name": rule.variant_name, "periods": 0}
    returns = pd.to_numeric(equity["net_return"], errors="coerce").dropna()
    periods = len(equity)
    total_return = float(equity.iloc[-1]["equity"]) - 1.0
    ann_return = (1.0 + total_return) ** (252.0 / periods) - 1.0 if total_return > -1 and periods else np.nan
    ann_vol = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else np.nan
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) else np.nan
    max_drawdown = float(pd.to_numeric(equity["drawdown"], errors="coerce").min())
    return {
        "variant_name": rule.variant_name,
        "top_n": top_n,
        "sell_buffer_rank": rule.sell_buffer_rank,
        "freeze_replacement_limit": rule.freeze_replacement_limit,
        "transaction_cost_bps": transaction_cost_bps,
        "periods": periods,
        "actual_start_date": str(equity.iloc[0]["date"]),
        "actual_end_date": str(equity.iloc[-1]["date"]),
        "final_equity": float(equity.iloc[-1]["equity"]),
        "total_return": total_return,
        "annualized_return": ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "calmar_ratio": ann_return / abs(max_drawdown) if max_drawdown < 0 else np.nan,
        "daily_win_rate": float((returns > 0).mean()) if not returns.empty else np.nan,
        "average_turnover": float(pd.to_numeric(equity["turnover"], errors="coerce").mean()),
        "total_transaction_cost": float(pd.to_numeric(equity["transaction_cost"], errors="coerce").sum()),
        "freeze_day_count": int(equity["freeze_active"].astype(bool).sum()),
        "position_rows": len(positions),
        "trade_rows": len(trades),
    }


def _rank_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    ranked = summary.copy()
    for column in ["sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown", "average_turnover"]:
        ranked[column] = pd.to_numeric(ranked.get(column), errors="coerce")
    ranked = ranked.sort_values(
        ["sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown", "average_turnover"],
        ascending=[False, False, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    ranked.insert(0, "scan_rank", range(1, len(ranked) + 1))
    return ranked


def _render_report(summary: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Shadow Control v2 Scan",
        "",
        "## 1. Scope",
        "验证卖出缓冲和回撤期冻结新买规则；不生成交易建议，不接实盘。",
        "",
        "## 2. Summary",
        summary.to_markdown(index=False) if not summary.empty else "No rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
