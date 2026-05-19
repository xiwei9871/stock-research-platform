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
            }
        ]
    )

    paths = write_watchlist_report(frame, output_dir=tmp_path)

    assert Path(paths["markdown_path"]).name == "watchlist_report_2026-05-20_core.md"
    assert Path(paths["json_path"]).name == "watchlist_report_2026-05-20_core.json"
    assert Path(paths["signals_csv_path"]).name == "watchlist_signals_2026-05-20_core.csv"
    assert Path(paths["must_watch_csv_path"]).name == "must_watch_2026-05-20_core.csv"

    json_rows = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert json_rows[0]["signal_tags"] == "[\"candidate\", \"must_watch\"]"
    assert json_rows[0]["risk_tags"] == "[]"
    assert json_rows[0]["reason_json"] == "{\"score_rank\": 1}"

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "## Must Watch" in markdown
    assert "## Candidate" in markdown
    assert "## Risk Excluded" in markdown
