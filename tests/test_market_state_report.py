import pandas as pd
import pytest

import stock_research.reports.market_state_report as market_state_report
from stock_research.reports.market_state_report import (
    calc_market_state,
    load_market_state_bars,
    write_market_state_report,
)


def _index_bars() -> pd.DataFrame:
    rows = []
    for index, trade_date in enumerate(pd.date_range("2026-01-01", periods=61, freq="D")):
        rows.append(
            {
                "trade_date": trade_date.date().isoformat(),
                "index_id": "CSI300",
                "close": 100.0 + index,
                "amount": 1000.0 + index * 10.0,
            }
        )
    return pd.DataFrame(rows)


def test_calc_market_state_classifies_bullish_index_context():
    result = calc_market_state(
        _index_bars(),
        trade_date="2026-03-02",
        index_id="CSI300",
    )

    assert result["trade_date"] == "2026-03-02"
    assert result["index_id"] == "CSI300"
    assert result["ret_20d"] == pytest.approx(160.0 / 140.0 - 1.0)
    assert result["ma20"] == pytest.approx(sum(range(141, 161)) / 20)
    assert result["market_state"] == "bullish"
    assert result["risk_level"] == "low"
    assert result["entry_allowed"] is True


def test_write_market_state_report_outputs_markdown_and_csv(tmp_path):
    state = calc_market_state(_index_bars(), trade_date="2026-03-02", index_id="CSI300")

    paths = write_market_state_report(state, output_dir=tmp_path)

    markdown_path = tmp_path / "market_state_2026-03-02_CSI300.md"
    csv_path = tmp_path / "market_state_2026-03-02_CSI300.csv"
    assert paths == {"markdown_path": markdown_path, "csv_path": csv_path}
    assert markdown_path.exists()
    assert csv_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 2026-03-02 Market State" in markdown
    assert "bullish" in markdown
    assert "市场状态只作为过滤器，不构成交易指令。" in markdown
    csv = pd.read_csv(csv_path)
    assert csv.iloc[0]["market_state"] == "bullish"


def test_load_market_state_bars_queries_index_daily_bar(monkeypatch):
    calls = {}

    class _Connection:
        pass

    class _Context:
        def __enter__(self):
            return _Connection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["service"] = service
        return _Context()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = list(params)
        return [
            {
                "trade_date": "2026-03-02",
                "index_id": "CSI300",
                "close": 160.0,
                "amount": 1600.0,
            }
        ]

    monkeypatch.setattr(market_state_report, "connect", fake_connect)
    monkeypatch.setattr(market_state_report, "fetch_all", fake_fetch_all)

    result = load_market_state_bars(
        start_date="2026-01-01",
        end_date="2026-03-02",
        index_id="CSI300",
    )

    assert calls["service"] == "stock_research"
    assert "FROM market.index_daily_bar" in calls["sql"]
    assert "index_id = %s" in calls["sql"]
    assert calls["params"] == ["CSI300", "2026-01-01", "2026-03-02"]
    assert result.iloc[0]["close"] == 160.0
