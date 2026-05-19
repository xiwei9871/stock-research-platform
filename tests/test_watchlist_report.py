from datetime import date
from decimal import Decimal
import pytest
import json
from pathlib import Path

import pandas as pd

from stock_research.reports.watchlist_report import write_watchlist_report


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
