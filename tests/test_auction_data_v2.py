import numpy as np
import pandas as pd
import pytest

from stock_research.auction_data_v2 import (
    auction_enhanced_score_v2,
    build_lhb_auction_observation_detail_v2,
)


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-10-13", "2026-10-13", "2026-10-14"],
            "entry_trade_date": ["2026-10-14", "2026-10-14", "2026-10-15"],
            "ts_code": ["000001.SZ", "600000.SH", "300001.SZ"],
            "phase12a_rule_layer": ["follow_pool_core", "watch_pool", "follow_pool_core"],
            "realized_return": [0.03, -0.01, 0.02],
        }
    )


def _tdx_open() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-10-14", "2026-10-14"],
            "ts_code": ["000001.SZ", "600000.SH"],
            "open": [12.00, 9.10],
            "close": [12.00, 9.10],
            "source": ["tdx", "tdx"],
        }
    )


def _daily_close() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-10-13", "2026-10-13", "2026-10-14"],
            "ts_code": ["000001.SZ", "600000.SH", "300001.SZ"],
            "close": [11.50, 9.30, 21.0],
        }
    )


def _last_5m() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-10-13", "2026-10-13", "2026-10-14"],
            "ts_code": ["000001.SZ", "600000.SH", "300001.SZ"],
            "open": [11.45, 9.30, 0.0],   # 300001 dirty zero -> NULL, not inf
            "close": [11.50, 9.50, 21.0],
        }
    )


def test_v2_detail_uses_tdx_open_and_daily_close_and_last_5m_proxy():
    detail = build_lhb_auction_observation_detail_v2(
        trades=_trades(),
        tdx_open_bars=_tdx_open(),
        daily_closes=_daily_close(),
        last_5m_bars=_last_5m(),
    )
    by_code = detail.set_index("ts_code")

    # entry gap: 12.00 / 11.50 - 1 = +4.35%
    assert by_code.loc["000001.SZ", "entry_open_vs_signal_close"] == pytest.approx(
        12.00 / 11.50 - 1
    )
    assert by_code.loc["000001.SZ", "entry_open_source"] == "tdx"
    assert by_code.loc["000001.SZ", "signal_close_close"] == 11.50

    # strict close-call return must stay UNKNOWN — never fabricated
    assert pd.isna(by_code.loc["000001.SZ", "signal_close_auction_return"])

    # proxy is explicitly named, never aliased to close_call_return
    assert by_code.loc["000001.SZ", "signal_last_5m_return"] == pytest.approx(
        11.50 / 11.45 - 1
    )
    assert "close_call_return" not in "\n".join(
        str(c) for c in detail.columns if "last_5m" not in str(c)
    )


def test_v2_missing_inputs_preserve_unknown_semantics():
    detail = build_lhb_auction_observation_detail_v2(
        trades=_trades(),
        tdx_open_bars=_tdx_open(),
        daily_closes=_daily_close(),
        last_5m_bars=_last_5m(),
    )
    by_code = detail.set_index("ts_code")

    # 300001: no tdx open bar -> gap unknown, not zero
    assert pd.isna(by_code.loc["300001.SZ", "entry_open_vs_signal_close"])
    # dirty zero open in 14:55 bar -> NaN, not inf
    assert pd.isna(by_code.loc["300001.SZ", "signal_last_5m_return"])

    coverage = dict(zip(detail["ts_code"], detail["auction_coverage_v2"]))
    assert coverage["000001.SZ"] == "complete"
    assert coverage["300001.SZ"] != "complete"


def test_v2_score_reuses_gap_buckets_and_proxies_signal_term():
    detail = build_lhb_auction_observation_detail_v2(
        trades=_trades(),
        tdx_open_bars=_tdx_open(),
        daily_closes=_daily_close(),
        last_5m_bars=_last_5m(),
    )
    scores = auction_enhanced_score_v2(detail)
    by_code = dict(zip(detail["ts_code"], scores))

    # 000001: layer 100 + gap +10 (gt .02) +15 (gt .04) = 125
    # last_5m = 11.5/11.45-1 ≈ +0.44% -> no signal term
    assert by_code["000001.SZ"] == pytest.approx(125.0)
    # 600000: layer 10, gap = 9.10/9.30-1 < -0.02 -> -15; last_5m +5.4% -> +10
    assert by_code["600000.SH"] == pytest.approx(10 - 15 + 10)
    # 300001: layer 100, both terms unknown -> 100 (neutral, not penalized)
    assert by_code["300001.SZ"] == pytest.approx(100.0)
