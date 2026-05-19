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

    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["json_path"]).exists()
    assert Path(paths["signals_csv_path"]).exists()
    assert Path(paths["must_watch_csv_path"]).exists()
