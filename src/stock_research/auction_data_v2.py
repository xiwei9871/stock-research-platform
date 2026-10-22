"""Research-only v2 auction observation adapter (isolated path).

Data sources:
- Entry open auction: TDX ``open_call`` bars (``source='tdx'``,
  single 09:25 match price).
- Signal close price: raw daily close (verified identical to the raw
  15:00 5-minute bar close; kept as its own input so semantics stay clear).
- ``signal_last_5m_return``: last raw 5-minute bar open->close move.
  This is a tail-movement PROXY covering ~14:55-15:00 (mixing ~2 minutes
  of continuous trading with the 14:57-15:00 closing call). It is never
  named or treated as the strict ``signal_close_auction_return``.
- Close-auction-exclusive quantities (true call-auction return, auction
  volume/orders) are NOT reconstructible from 5-minute bars: they stay
  NULL/unknown and are never zero-filled.

PIT: signal-day 15:00 close data is only usable for decisions made after
the close is actually available (i.e. entry-day decisions onward).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from stock_research.auction_data import (
    LHB_RULE_LAYER_BASE_SCORE,
    safe_divide,
)


def _normalize_dates(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d")
    return out


def build_lhb_auction_observation_detail_v2(
    *,
    trades: pd.DataFrame,
    tdx_open_bars: pd.DataFrame,
    daily_closes: pd.DataFrame,
    last_5m_bars: pd.DataFrame,
) -> pd.DataFrame:
    """Merge v2 auction observations onto LHB trades.

    Inputs are plain frames keyed by (trade_date, ts_code):
    - ``tdx_open_bars``: open, close, source for entry-day TDX open_call.
    - ``daily_closes``: raw close for signal day.
    - ``last_5m_bars``: open, close of the raw 15:00 5-minute bar.
    """

    detail = trades.copy()
    if detail.empty:
        return detail
    detail = _normalize_dates(detail, ["trade_date", "entry_trade_date"])

    if not tdx_open_bars.empty:
        entry = _normalize_dates(tdx_open_bars, ["trade_date"]).rename(
            columns={
                "trade_date": "entry_open_trade_date",
                "open": "entry_open_open",
                "close": "entry_open_close",
                "source": "entry_open_source",
            }
        )
        detail = detail.merge(
            entry,
            left_on=["entry_trade_date", "ts_code"],
            right_on=["entry_open_trade_date", "ts_code"],
            how="left",
        )
    else:
        detail["entry_open_open"] = pd.NA
        detail["entry_open_close"] = pd.NA
        detail["entry_open_source"] = pd.NA

    if not daily_closes.empty:
        closes = _normalize_dates(daily_closes, ["trade_date"]).rename(
            columns={
                "trade_date": "signal_close_trade_date",
                "close": "signal_close_close",
            }
        )[["signal_close_trade_date", "ts_code", "signal_close_close"]]
        detail = detail.merge(
            closes,
            left_on=["trade_date", "ts_code"],
            right_on=["signal_close_trade_date", "ts_code"],
            how="left",
        )
    else:
        detail["signal_close_close"] = pd.NA

    if not last_5m_bars.empty:
        tail = _normalize_dates(last_5m_bars, ["trade_date"]).rename(
            columns={
                "trade_date": "signal_last_5m_trade_date",
                "open": "signal_last_5m_open",
                "close": "signal_last_5m_close",
            }
        )[["signal_last_5m_trade_date", "ts_code",
           "signal_last_5m_open", "signal_last_5m_close"]]
        detail = detail.merge(
            tail,
            left_on=["trade_date", "ts_code"],
            right_on=["signal_last_5m_trade_date", "ts_code"],
            how="left",
        )
    else:
        detail["signal_last_5m_open"] = pd.NA
        detail["signal_last_5m_close"] = pd.NA

    detail["entry_open_auction_return"] = safe_divide(
        detail["entry_open_close"], detail["entry_open_open"]
    )
    detail["entry_open_vs_signal_close"] = safe_divide(
        detail["entry_open_close"], detail["signal_close_close"]
    )
    tail_open = pd.to_numeric(detail["signal_last_5m_open"], errors="coerce")
    tail_close = pd.to_numeric(detail["signal_last_5m_close"], errors="coerce")
    detail["signal_last_5m_return"] = (tail_close / tail_open - 1.0).where(
        tail_open.gt(0)
    )
    # True close-call return is not reconstructible: keep it unknown.
    detail["signal_close_auction_return"] = pd.NA
    detail["signal_close_source"] = "daily_close_raw"
    detail["signal_last_5m_source"] = detail["signal_last_5m_return"].notna().map(
        {True: "stock_minute_bar_5min_raw", False: None}
    )

    has_entry = detail["entry_open_close"].notna()
    has_signal = detail["signal_close_close"].notna()
    has_tail = detail["signal_last_5m_return"].notna()
    detail["auction_coverage_v2"] = "missing"
    detail.loc[has_signal & ~has_entry, "auction_coverage_v2"] = "signal_only"
    detail.loc[has_entry & ~has_signal, "auction_coverage_v2"] = "entry_only"
    detail.loc[has_signal & has_entry & ~has_tail, "auction_coverage_v2"] = "no_tail_bar"
    detail.loc[has_signal & has_entry & has_tail, "auction_coverage_v2"] = "complete"
    return detail


def auction_enhanced_score_v2(frame: pd.DataFrame) -> pd.Series:
    """v2 score: identical buckets, signal term on ``signal_last_5m_return``.

    The proxy term is intentionally evaluated with the same thresholds so
    v1/v2 diffs isolate the data-source change rather than a rule change.
    """

    layer_score = frame["phase12a_rule_layer"].map(LHB_RULE_LAYER_BASE_SCORE).fillna(0.0)
    gap = pd.to_numeric(frame["entry_open_vs_signal_close"], errors="coerce").fillna(0.0)
    signal_tail = pd.to_numeric(
        frame["signal_last_5m_return"], errors="coerce"
    ).fillna(0.0)
    score = layer_score.copy()
    score += gap.gt(0.02).astype(float) * 10.0
    score += gap.gt(0.04).astype(float) * 15.0
    score += gap.gt(0.06).astype(float) * 25.0
    score += gap.lt(-0.02).astype(float) * -15.0
    score += signal_tail.gt(0.02).astype(float) * 10.0
    score += signal_tail.lt(-0.005).astype(float) * -10.0
    return score


def load_tdx_open_call_bars(
    *,
    conn: Any,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    from stock_research.db import fetch_all

    if not ts_codes:
        return pd.DataFrame()
    rows = fetch_all(
        conn,
        """
        SELECT trade_date::text AS trade_date, ts_code, open, close, source
        FROM market.stock_auction_bar
        WHERE auction_phase = 'open_call'
          AND source = 'tdx'
          AND ts_code = ANY(%s)
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, ts_code
        """,
        [ts_codes, start_date, end_date],
    )
    return pd.DataFrame(rows)


def load_raw_daily_closes(
    *,
    conn: Any,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    from stock_research.db import fetch_all

    if not ts_codes:
        return pd.DataFrame()
    rows = fetch_all(
        conn,
        """
        SELECT d.trade_date::text AS trade_date, a.ts_code, d.close
        FROM market_daily_bar AS d
        JOIN core.asset_master AS a ON a.asset_id = d.asset_id
        WHERE d.adjust_type = 'raw'
          AND a.ts_code = ANY(%s)
          AND d.trade_date BETWEEN %s AND %s
        ORDER BY d.trade_date, a.ts_code
        """,
        [ts_codes, start_date, end_date],
    )
    return pd.DataFrame(rows)


def load_last_5m_bars(
    *,
    conn: Any,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Raw 15:00 5-minute bar per (trade_date, ts_code).

    The bar's window is 14:55-15:00: it mixes continuous trading with the
    closing call auction, so it is a proxy input, never close-call data.
    """

    from stock_research.db import fetch_all

    if not ts_codes:
        return pd.DataFrame()
    rows = fetch_all(
        conn,
        """
        SELECT m.trade_date::text AS trade_date, a.ts_code, m.open, m.close
        FROM market.stock_minute_bar AS m
        JOIN core.asset_master AS a ON a.asset_id = m.asset_id
        WHERE m.freq = '5min'
          AND m.adjust_type = 'raw'
          AND m.trade_time::time = '15:00:00'
          AND a.ts_code = ANY(%s)
          AND m.trade_date BETWEEN %s AND %s
        ORDER BY m.trade_date, a.ts_code
        """,
        [ts_codes, start_date, end_date],
    )
    return pd.DataFrame(rows)
