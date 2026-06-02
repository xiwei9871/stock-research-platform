from datetime import date
from decimal import Decimal
import pytest
import json
from pathlib import Path

import pandas as pd

from stock_research.reports.watchlist_report import (
    write_watchlist_diagnostics_report,
    write_watchlist_report,
)


def test_write_watchlist_report_writes_markdown_json_csv_and_must_watch(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate", "must_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            },
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "B",
                "priority": 20,
                "signal_score": 55.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": ["risk_excluded"],
                "must_watch": False,
                "reason_json": {"score_rank": None},
                "output_version": "v1",
            }
        ]
    )

    paths = write_watchlist_report(frame, output_dir=tmp_path)

    assert Path(paths["markdown_path"]).name == "watchlist_report_2026-05-20_core.md"
    assert Path(paths["json_path"]).name == "watchlist_report_2026-05-20_core.json"
    assert Path(paths["signals_csv_path"]).name == "watchlist_signals_2026-05-20_core.csv"
    assert Path(paths["must_watch_csv_path"]).name == "must_watch_2026-05-20_core.csv"
    assert Path(paths["signals_csv_path"]).exists()
    assert Path(paths["must_watch_csv_path"]).exists()

    json_rows = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert json_rows[0]["signal_tags"] == "[\"candidate\", \"must_watch\"]"
    assert json_rows[0]["risk_tags"] == "[]"
    assert json_rows[0]["reason_json"] == "{\"score_rank\": 1}"
    assert json_rows[1]["signal_tags"] == "[\"candidate\"]"
    assert json_rows[1]["risk_tags"] == "[\"risk_excluded\"]"
    assert json_rows[1]["reason_json"] == "{\"score_rank\": null}"

    must_watch_rows = pd.read_csv(Path(paths["must_watch_csv_path"]))
    assert len(must_watch_rows) == 1
    assert bool(must_watch_rows.iloc[0]["must_watch"]) is True

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "## Must Watch" in markdown
    assert "## Candidate" in markdown
    assert "## Risk Excluded" in markdown
    must_watch_section = markdown.split("## Candidate")[0]
    candidate_section = markdown.split("## Candidate")[1].split("## Risk Excluded")[0]
    risk_section = markdown.split("## Risk Excluded")[1]
    assert "A" in must_watch_section
    assert "B" not in must_watch_section
    assert "B" not in candidate_section
    assert "B" in risk_section


def test_write_watchlist_report_normalizes_typed_values_and_validates_identity(tmp_path):
    typed_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": date(2026, 5, 20),
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": Decimal("10"),
                "signal_score": Decimal("88.5"),
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": Decimal("1")},
                "output_version": "v1",
            }
        ]
    )

    paths = write_watchlist_report(typed_frame, output_dir=tmp_path)
    json_rows = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))

    assert json_rows[0]["trade_date"] == "2026-05-20"
    assert json_rows[0]["priority"] == 10
    assert json_rows[0]["signal_score"] == 88.5
    assert json_rows[0]["signal_tags"] == "[\"candidate\"]"
    assert json_rows[0]["risk_tags"] == "[]"
    assert json_rows[0]["reason_json"] == "{\"score_rank\": 1}"

    with pytest.raises(ValueError, match="empty"):
        write_watchlist_report(pd.DataFrame(), output_dir=tmp_path)

    mixed_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            },
            {
                "watchlist_id": "alt",
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "B",
                "priority": 20,
                "signal_score": 55.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": [],
                "must_watch": False,
                "reason_json": {"score_rank": None},
                "output_version": "v1",
            },
        ]
    )

    with pytest.raises(ValueError, match="watchlist_id"):
        write_watchlist_report(mixed_frame, output_dir=tmp_path)

    missing_identity_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            },
            {
                "watchlist_id": None,
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "B",
                "priority": 20,
                "signal_score": 55.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": [],
                "must_watch": False,
                "reason_json": {"score_rank": None},
                "output_version": "v1",
            },
        ]
    )

    with pytest.raises(ValueError, match="watchlist_id"):
        write_watchlist_report(missing_identity_frame, output_dir=tmp_path)


def test_write_watchlist_diagnostics_report_writes_grouped_markdown_and_csvs(tmp_path):
    full_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_name": "Alpha",
                "watch_group": "risk_watch",
                "watch_priority": 0,
                "event_structure": "a_kill_failure",
                "dragon_trade_date": "2026-05-20",
                "entry_window_v2": "overheat_avoid",
                "case_event_date": "2026-05-19",
                "case_event_type": "peak",
                "lhb_event_date": "2026-05-18",
                "lhb_risk_level": "high",
                "market_regime": "bullish",
                "market_risk_level": "low",
                "industry_name": "Tech",
                "mainline_flag": True,
                "diagnostic_reason": "risk_watch:a_kill_failure",
                "risk_note": "dragon_risk_high",
                "opportunity_note": "",
            },
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "B",
                "stock_name": "Beta",
                "watch_group": "opportunity_watch",
                "watch_priority": 1,
                "event_structure": "second_wave_candidate",
                "dragon_trade_date": "2026-05-20",
                "entry_window_v2": "low_congestion_opportunity",
                "market_regime": "bullish",
                "market_risk_level": "low",
                "industry_name": "AI",
                "mainline_flag": False,
                "diagnostic_reason": "opportunity_watch:second_wave_candidate",
                "risk_note": "",
                "opportunity_note": "second_wave_candidate",
            },
        ]
    )
    must_watch_frame = full_frame.iloc[[0, 1]].copy()

    paths = write_watchlist_diagnostics_report(
        full_rows=full_frame,
        must_watch_rows=must_watch_frame,
        output_dir=tmp_path,
    )

    assert Path(paths["markdown_path"]).name == "watchlist_diagnostics_2026-05-20_core_v1.md"
    assert Path(paths["full_csv_path"]).name == "watchlist_diagnostics_2026-05-20_core_v1.csv"
    assert Path(paths["must_watch_csv_path"]).name == "watchlist_diagnostics_must_watch_2026-05-20_core_v1.csv"

    diagnostics_rows = pd.read_csv(Path(paths["full_csv_path"]))
    assert list(diagnostics_rows["asset_id"]) == ["A", "B"]

    must_watch_rows = pd.read_csv(Path(paths["must_watch_csv_path"]))
    assert list(must_watch_rows["asset_id"]) == ["A", "B"]

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "## Risk Watch" in markdown
    assert "## Opportunity Watch" in markdown
    assert "Alpha" in markdown
    assert "Beta" in markdown
    assert "2026-05-20 / overheat_avoid" in markdown
    assert "2026-05-19 / peak" in markdown
    assert "2026-05-18 / high" in markdown
    assert "bullish / low" in markdown
    assert "Tech / mainline" in markdown


def test_write_watchlist_diagnostics_report_escapes_markdown_cells(tmp_path):
    full_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_name": "Alpha|One\nLine2",
                "watch_group": "risk_watch",
                "watch_priority": 0,
                "event_structure": "break|then\nreversal",
                "diagnostic_reason": "reason|one\nline2",
                "risk_note": "risk|flag\nwarn",
                "opportunity_note": "",
            }
        ]
    )

    paths = write_watchlist_diagnostics_report(
        full_rows=full_frame,
        must_watch_rows=full_frame.copy(),
        output_dir=tmp_path,
    )

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "Alpha\\|One<br>Line2" in markdown
    assert "break\\|then<br>reversal" in markdown
    assert "reason\\|one<br>line2" in markdown
    assert "risk\\|flag<br>warn" in markdown


def test_write_watchlist_diagnostics_report_groups_high_odds_burst_separately(tmp_path):
    full_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "diagnostics",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_name": "Alpha",
                "watch_group": "high_odds_burst_watch",
                "watch_priority": 50,
                "event_structure": "trend_continuation_candidate",
                "diagnostic_reason": "high_odds_burst_watch:trend_continuation_candidate",
                "risk_note": "high_odds_burst",
                "opportunity_note": "",
            }
        ]
    )

    paths = write_watchlist_diagnostics_report(
        full_rows=full_frame,
        must_watch_rows=full_frame.copy(),
        output_dir=tmp_path,
    )

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    high_odds_section = markdown.split("## High Odds Burst")[1].split("## Opportunity Watch")[0]
    risk_section = markdown.split("## Risk Watch")[1].split("## High Odds Burst")[0]
    assert "Alpha" in high_odds_section
    assert "Alpha" not in risk_section


def test_write_watchlist_diagnostics_report_validates_matching_identity_fields(tmp_path):
    diagnostics_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": ["risk_excluded"],
                "must_watch": True,
                "watch_group": "risk_watch",
            }
        ]
    )
    must_watch_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "alt",
                "trade_date": "2026-05-21",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": ["risk_excluded"],
                "must_watch": True,
                "watch_group": "risk_watch",
            }
        ]
    )

    with pytest.raises(ValueError, match="trade_date.*watchlist_id"):
        write_watchlist_diagnostics_report(
            full_rows=diagnostics_frame,
            must_watch_rows=must_watch_frame,
            output_dir=tmp_path,
        )


def test_write_watchlist_diagnostics_report_allows_empty_must_watch_rows(tmp_path):
    diagnostics_frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate"],
                "risk_tags": ["risk_excluded"],
                "must_watch": True,
                "watch_group": "risk_watch",
            }
        ]
    )
    must_watch_frame = pd.DataFrame(columns=diagnostics_frame.columns)

    paths = write_watchlist_diagnostics_report(
        full_rows=diagnostics_frame,
        must_watch_rows=must_watch_frame,
        output_dir=tmp_path,
    )

    assert Path(paths["full_csv_path"]).exists()
    assert Path(paths["must_watch_csv_path"]).exists()


def test_write_watchlist_diagnostics_report_allows_empty_full_rows_with_explicit_identity(tmp_path):
    empty_columns = [
        "watchlist_id",
        "trade_date",
        "asset_id",
        "stock_name",
        "watch_group",
        "watch_priority",
        "event_structure",
        "diagnostic_reason",
        "risk_note",
        "opportunity_note",
    ]
    full_rows = pd.DataFrame(columns=empty_columns)
    must_watch_rows = pd.DataFrame(columns=empty_columns)

    paths = write_watchlist_diagnostics_report(
        full_rows=full_rows,
        must_watch_rows=must_watch_rows,
        output_dir=tmp_path,
        trade_date="2026-05-20",
        watchlist_id="diagnostics",
    )

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "Watchlist Diagnostics 2026-05-20" in markdown
    assert "No rows." in markdown
