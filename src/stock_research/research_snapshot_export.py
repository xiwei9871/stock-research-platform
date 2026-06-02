import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


@dataclass(frozen=True)
class SnapshotDataset:
    name: str
    filename: str
    sql: str
    columns: list[str]
    params: tuple[str, ...]


SNAPSHOT_DATASETS = [
    SnapshotDataset(
        name="market_daily_bar",
        filename="market_daily_bar.csv",
        sql="""
        SELECT asset_id, trade_date, open, high, low, close, preclose, volume, amount,
               turnover_rate, pct_chg, trade_status, is_st, adjust_type, source, updated_at
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id, adjust_type
        """,
        columns=[
            "asset_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "turnover_rate",
            "pct_chg",
            "trade_status",
            "is_st",
            "adjust_type",
            "source",
            "updated_at",
        ],
        params=("start_date", "end_date"),
    ),
    SnapshotDataset(
        name="label_snapshot",
        filename="label_snapshot.csv",
        sql="""
        SELECT asset_id, trade_date, label_set, label_version, horizon, label_name,
               label_value, computed_at
        FROM label_snapshot
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id, label_set, label_version, horizon, label_name
        """,
        columns=[
            "asset_id",
            "trade_date",
            "label_set",
            "label_version",
            "horizon",
            "label_name",
            "label_value",
            "computed_at",
        ],
        params=("start_date", "end_date"),
    ),
    SnapshotDataset(
        name="factor_daily",
        filename="factor_daily.csv",
        sql="""
        SELECT trade_date, asset_id, factor_name, factor_group, factor_value,
               calc_version, source, source_data_version, computed_at
        FROM factor.factor_daily
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id, factor_name, calc_version
        """,
        columns=[
            "trade_date",
            "asset_id",
            "factor_name",
            "factor_group",
            "factor_value",
            "calc_version",
            "source",
            "source_data_version",
            "computed_at",
        ],
        params=("start_date", "end_date"),
    ),
    SnapshotDataset(
        name="stock_score_daily",
        filename="stock_score_daily.csv",
        sql="""
        SELECT trade_date, asset_id, rank, score_total, score_version, score_components,
               calc_version, source_data_version, computed_at
        FROM factor.stock_score_daily
        WHERE trade_date BETWEEN %s AND %s
          AND score_version = %s
        ORDER BY trade_date, score_version, rank, asset_id
        """,
        columns=[
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_version",
            "score_components",
            "calc_version",
            "source_data_version",
            "computed_at",
        ],
        params=("start_date", "end_date", "score_version"),
    ),
    SnapshotDataset(
        name="factor_approval",
        filename="factor_approval.csv",
        sql="""
        SELECT factor_name, calc_version, score_version, status, reason, eval_run_id, approved_at
        FROM factor.factor_approval
        WHERE score_version = %s
        ORDER BY score_version, factor_name, calc_version
        """,
        columns=[
            "factor_name",
            "calc_version",
            "score_version",
            "status",
            "reason",
            "eval_run_id",
            "approved_at",
        ],
        params=("score_version",),
    ),
]


def export_research_snapshot(
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    score_version: str = "manual_v1",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be <= end_date")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "score_version": score_version,
    }
    row_counts = {}
    files = {}

    with connect(service) as conn:
        for dataset in SNAPSHOT_DATASETS:
            rows = fetch_all(conn, dataset.sql, [context[key] for key in dataset.params])
            frame = pd.DataFrame(rows).reindex(columns=dataset.columns)
            path = output_path / dataset.filename
            frame.to_csv(path, index=False)
            row_counts[dataset.name] = int(len(frame))
            files[dataset.name] = str(path)

    manifest = {
        **context,
        "row_counts": row_counts,
        "files": files,
    }
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path)}
