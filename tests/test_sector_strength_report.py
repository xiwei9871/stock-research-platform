import pandas as pd
import pytest

import stock_research.reports.sector_strength_report as sector_strength_report
from stock_research.reports.sector_strength_report import (
    calc_sector_strength,
    load_sector_strength_bars,
    write_sector_strength_report,
)


def _sector_bars() -> pd.DataFrame:
    rows = []
    for index in range(21):
        trade_date = f"2026-01-{index + 1:02d}"
        rows.extend(
            [
                {
                    "trade_date": trade_date,
                    "industry_system": "csrc",
                    "industry_code": "T",
                    "industry_name": "Tech",
                    "close": 100.0 + index * 2.0,
                    "amount": 1000.0 + index * 20.0,
                },
                {
                    "trade_date": trade_date,
                    "industry_system": "csrc",
                    "industry_code": "B",
                    "industry_name": "Bank",
                    "close": 100.0 + index * 0.5,
                    "amount": 1000.0,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_calc_sector_strength_ranks_latest_industries():
    result = calc_sector_strength(_sector_bars(), trade_date="2026-01-21", top_n=2)

    assert list(result["industry_code"]) == ["T", "B"]
    tech = result.iloc[0]
    assert tech["trade_date"] == "2026-01-21"
    assert tech["industry_name"] == "Tech"
    assert tech["ret_5d"] == pytest.approx(140.0 / 130.0 - 1.0)
    assert tech["ret_20d"] == pytest.approx(140.0 / 100.0 - 1.0)
    assert tech["amount_ratio_5_20"] > 1.0
    assert tech["strength_rank"] == 1
    assert tech["strength_score"] > result.iloc[1]["strength_score"]


def test_write_sector_strength_report_outputs_markdown_and_csv(tmp_path):
    strength = calc_sector_strength(_sector_bars(), trade_date="2026-01-21", top_n=2)

    paths = write_sector_strength_report(
        strength,
        trade_date="2026-01-21",
        industry_system="csrc",
        output_dir=tmp_path,
    )

    markdown_path = tmp_path / "sector_strength_2026-01-21_csrc.md"
    csv_path = tmp_path / "sector_strength_2026-01-21_csrc.csv"
    assert paths == {"markdown_path": markdown_path, "csv_path": csv_path}
    assert markdown_path.exists()
    assert csv_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 2026-01-21 Sector Strength" in markdown
    assert "Tech" in markdown
    assert "仅作为研究观察，不构成交易指令。" in markdown
    csv = pd.read_csv(csv_path)
    assert list(csv["industry_code"]) == ["T", "B"]


def test_load_sector_strength_bars_queries_industry_daily_bar(monkeypatch):
    calls = {}

    class _Connection:
        pass

    class _Context:
        def __enter__(self):
            calls["service"] = "stock_research"
            return _Connection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["requested_service"] = service
        return _Context()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = list(params)
        return [
            {
                "trade_date": "2026-01-21",
                "industry_system": "csrc",
                "industry_code": "T",
                "industry_name": "Tech",
                "close": 140.0,
                "amount": 1400.0,
            }
        ]

    monkeypatch.setattr(sector_strength_report, "connect", fake_connect)
    monkeypatch.setattr(sector_strength_report, "fetch_all", fake_fetch_all)

    result = load_sector_strength_bars(
        start_date="2026-01-01",
        end_date="2026-01-21",
        industry_system="csrc",
    )

    assert calls["requested_service"] == "stock_research"
    assert "FROM market.industry_daily_bar" in calls["sql"]
    assert "industry_system = %s" in calls["sql"]
    assert calls["params"] == ["csrc", "2026-01-01", "2026-01-21"]
    assert result.iloc[0]["industry_name"] == "Tech"
