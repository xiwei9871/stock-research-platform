from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


MARKET_STATE_COLUMNS = [
    "trade_date",
    "index_id",
    "close",
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "ma20",
    "ma60",
    "drawdown_20d",
    "amount_ratio_5_20",
    "market_state",
    "risk_level",
    "entry_allowed",
]


def load_market_state_bars(
    start_date: str,
    end_date: str,
    index_id: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT
            trade_date,
            index_id,
            close,
            amount
        FROM market.index_daily_bar
        WHERE index_id = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date
    """
    params = [index_id, start_date, end_date]
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def calc_market_state(
    index_bars: pd.DataFrame,
    trade_date: str,
    index_id: str,
) -> dict[str, Any]:
    if index_bars.empty:
        return _empty_state(trade_date, index_id)

    frame = index_bars.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame = frame[frame["index_id"] == index_id].sort_values("trade_date")
    frame = frame[frame["trade_date"] <= _iso_date(trade_date)].copy()
    if frame.empty:
        return _empty_state(trade_date, index_id)

    close = frame["close"]
    amount = frame["amount"]
    frame["ret_5d"] = close.pct_change(5)
    frame["ret_20d"] = close.pct_change(20)
    frame["ret_60d"] = close.pct_change(60)
    frame["ma20"] = close.rolling(20).mean()
    frame["ma60"] = close.rolling(60).mean()
    frame["drawdown_20d"] = close / close.rolling(20).max() - 1.0
    frame["amount_ratio_5_20"] = amount.rolling(5).mean() / amount.rolling(20).mean()

    latest = frame.iloc[-1].to_dict()
    market_state = _classify_market_state(latest)
    risk_level = _classify_risk(latest, market_state)
    latest["market_state"] = market_state
    latest["risk_level"] = risk_level
    latest["entry_allowed"] = market_state != "defensive" and risk_level != "high"
    return {column: latest.get(column) for column in MARKET_STATE_COLUMNS}


def write_market_state_report(
    state: dict[str, Any],
    output_dir: str | Path = "reports/market_state",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    trade_date = _iso_date(state["trade_date"])
    index_id = str(state["index_id"])
    stem = f"market_state_{trade_date}_{index_id}"
    markdown_path = output_path / f"{stem}.md"
    csv_path = output_path / f"{stem}.csv"

    normalized = _normalize_state(state)
    pd.DataFrame([normalized], columns=MARKET_STATE_COLUMNS).to_csv(csv_path, index=False)
    markdown_path.write_text(_render_markdown(normalized), encoding="utf-8")
    return {"markdown_path": markdown_path, "csv_path": csv_path}


def _classify_market_state(row: dict[str, Any]) -> str:
    close = _float_or_none(row.get("close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    ret20 = _float_or_none(row.get("ret_20d"))
    drawdown = _float_or_none(row.get("drawdown_20d"))
    if close is None or ma20 is None or ma60 is None or ret20 is None:
        return "neutral"
    if drawdown is not None and drawdown <= -0.08:
        return "defensive"
    if close > ma20 > ma60 and ret20 > 0:
        return "bullish"
    if close < ma60 and ret20 < 0:
        return "defensive"
    return "neutral"


def _classify_risk(row: dict[str, Any], market_state: str) -> str:
    drawdown = _float_or_none(row.get("drawdown_20d"))
    amount_ratio = _float_or_none(row.get("amount_ratio_5_20"))
    if market_state == "defensive" or (drawdown is not None and drawdown <= -0.08):
        return "high"
    if amount_ratio is not None and amount_ratio < 0.75:
        return "medium"
    return "low"


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = {column: state.get(column) for column in MARKET_STATE_COLUMNS}
    normalized["trade_date"] = _iso_date(normalized["trade_date"])
    normalized["index_id"] = str(normalized["index_id"])
    normalized["entry_allowed"] = bool(normalized["entry_allowed"])
    return normalized


def _render_markdown(state: dict[str, Any]) -> str:
    lines = [
        f"# {state['trade_date']} Market State",
        "",
        f"- Index: `{state['index_id']}`",
        f"- State: `{state['market_state']}`",
        f"- Risk: `{state['risk_level']}`",
        f"- Entry allowed: `{state['entry_allowed']}`",
        "- 市场状态只作为过滤器，不构成交易指令。",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Close | {_format_number(state.get('close'))} |",
        f"| Ret 5D | {_format_pct(state.get('ret_5d'))} |",
        f"| Ret 20D | {_format_pct(state.get('ret_20d'))} |",
        f"| Ret 60D | {_format_pct(state.get('ret_60d'))} |",
        f"| MA20 | {_format_number(state.get('ma20'))} |",
        f"| MA60 | {_format_number(state.get('ma60'))} |",
        f"| Drawdown 20D | {_format_pct(state.get('drawdown_20d'))} |",
        f"| Amount 5/20 | {_format_number(state.get('amount_ratio_5_20'))} |",
    ]
    return "\n".join(lines) + "\n"


def _empty_state(trade_date: str, index_id: str) -> dict[str, Any]:
    return {
        "trade_date": _iso_date(trade_date),
        "index_id": index_id,
        "market_state": "neutral",
        "risk_level": "unknown",
        "entry_allowed": False,
    } | {column: None for column in MARKET_STATE_COLUMNS if column not in {"trade_date", "index_id", "market_state", "risk_level", "entry_allowed"}}


def _float_or_none(value: object) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _format_pct(value: object) -> str:
    number = _float_or_none(value)
    if number is None:
        return ""
    return f"{number * 100:.2f}%"


def _format_number(value: object) -> str:
    number = _float_or_none(value)
    if number is None:
        return ""
    return f"{number:.2f}"


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
