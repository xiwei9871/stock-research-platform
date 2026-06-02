import json
from pathlib import Path

import pandas as pd

from stock_research import research_snapshot_export


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_export_research_snapshot_writes_dataset_csvs_and_manifest(tmp_path, monkeypatch):
    conn = object()
    calls = []

    def fake_fetch_all(opened, sql, params):
        calls.append((sql, params))
        if "FROM market_daily_bar" in sql:
            return [
                {
                    "asset_id": "CN:SH:600000",
                    "trade_date": "2026-05-12",
                    "adjust_type": "hfq",
                    "close": 10,
                }
            ]
        if "FROM label_snapshot" in sql:
            return [{"asset_id": "CN:SH:600000", "trade_date": "2026-05-12", "horizon": 5}]
        if "FROM factor.factor_daily" in sql:
            return [
                {
                    "asset_id": "CN:SH:600000",
                    "trade_date": "2026-05-12",
                    "factor_name": "ret_5",
                    "calc_version": "v1",
                }
            ]
        if "FROM factor.stock_score_daily" in sql:
            return [
                {
                    "asset_id": "CN:SH:600000",
                    "trade_date": "2026-05-12",
                    "score_version": "manual_v1",
                    "rank": 1,
                }
            ]
        if "FROM factor.factor_approval" in sql:
            return [{"factor_name": "ret_5", "score_version": "manual_v1", "status": "approved"}]
        raise AssertionError(sql)

    monkeypatch.setattr(research_snapshot_export, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(research_snapshot_export, "fetch_all", fake_fetch_all)

    result = research_snapshot_export.export_research_snapshot(
        start_date="2026-05-12",
        end_date="2026-05-12",
        output_dir=tmp_path,
        score_version="manual_v1",
    )

    assert result["row_counts"] == {
        "market_daily_bar": 1,
        "label_snapshot": 1,
        "factor_daily": 1,
        "stock_score_daily": 1,
        "factor_approval": 1,
    }
    assert (tmp_path / "market_daily_bar.csv").exists()
    assert (tmp_path / "label_snapshot.csv").exists()
    assert (tmp_path / "factor_daily.csv").exists()
    assert pd.read_csv(tmp_path / "stock_score_daily.csv").iloc[0]["rank"] == 1

    manifest = json.loads(Path(tmp_path / "manifest.json").read_text())
    assert manifest["start_date"] == "2026-05-12"
    assert manifest["end_date"] == "2026-05-12"
    assert manifest["score_version"] == "manual_v1"
    assert manifest["row_counts"]["factor_approval"] == 1
    assert all(params[0] == "2026-05-12" for _, params in calls[:4])


def test_export_research_snapshot_rejects_invalid_date_window(tmp_path):
    try:
        research_snapshot_export.export_research_snapshot(
            start_date="2026-05-13",
            end_date="2026-05-12",
            output_dir=tmp_path,
        )
    except ValueError as exc:
        assert "start_date must be <= end_date" in str(exc)
    else:
        raise AssertionError("expected ValueError")
