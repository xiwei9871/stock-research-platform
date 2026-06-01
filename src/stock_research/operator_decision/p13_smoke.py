from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.p12_smoke import build_p12_shadow_watchlist_smoke
from stock_research.operator_decision.shadow_outcomes import (
    build_shadow_outcome_review,
    write_shadow_outcome_review,
)
from stock_research.operator_decision.shadow_outcomes_read_model import (
    load_shadow_outcome_read_model_rows,
)
from stock_research.operator_decision.shadow_watchlist_read_model import (
    load_shadow_watchlist_read_model_rows,
)


def build_p13_shadow_outcome_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p12_result = build_p12_shadow_watchlist_smoke(output_path)
    p13_dir = output_path / "p13"
    p13_dir.mkdir(parents=True, exist_ok=True)

    shadow_rows = load_shadow_watchlist_read_model_rows(p12_result["p12_shadow_json_path"])
    shadow_candidates = pd.DataFrame(shadow_rows["candidates"])
    review = build_shadow_outcome_review(
        review_date="2026-08-29",
        shadow_candidates=shadow_candidates,
        bars=_synthetic_bars(),
        run_id="p13-smoke-shadow-outcomes-2026-06-30",
    )
    outcome_paths = write_shadow_outcome_review(review, p13_dir)
    outcome_rows = load_shadow_outcome_read_model_rows(outcome_paths["json_path"])

    run = outcome_rows["run"]
    candidates = outcome_rows["candidates"]
    return {
        "p12_shadow_json_path": p12_result["p12_shadow_json_path"],
        "p13_shadow_outcome_json_path": outcome_paths["json_path"],
        "p13_shadow_outcome_details_csv_path": outcome_paths["details_csv_path"],
        "p13_shadow_outcome_markdown_path": outcome_paths["markdown_path"],
        "outcome_count": int(run["outcome_count"]),
        "read_model_candidate_count": len(candidates),
        "outcome_statuses": sorted({str(row["outcome_status"]) for row in candidates}),
        "source_p12_shadow_run_ids": sorted({str(row["source_p12_shadow_run_id"]) for row in candidates}),
        "source_p11_replay_run_ids": sorted({str(row["source_p11_replay_run_id"]) for row in candidates}),
        "source_p10_proposal_run_ids": sorted({str(row["source_p10_proposal_run_id"]) for row in candidates}),
        "source_p9_analytics_run_ids": sorted({str(row["source_p9_analytics_run_id"]) for row in candidates}),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }


def _synthetic_bars() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    start = pd.Timestamp("2026-06-30")
    for offset in range(0, 61):
        close = 10.0 + offset * 0.1
        rows.append(
            {
                "asset_id": "000001.SZ",
                "trade_date": (start + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                "close": close,
                "high": close + 0.2,
                "low": close - 0.2,
            }
        )
    return pd.DataFrame(rows)
