from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.journal import build_decision_journal, write_decision_journal
from stock_research.operator_decision.outcome import build_decision_outcome_review, write_decision_outcome_review
from stock_research.operator_decision.outcome_read_model import load_decision_outcome_read_model_rows
from stock_research.operator_decision.read_model import load_decision_journal_read_model_rows


def build_p8_decision_outcome_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p7_dir = output_path / "p7"
    p8_dir = output_path / "p8"
    p7_dir.mkdir(parents=True, exist_ok=True)
    p8_dir.mkdir(parents=True, exist_ok=True)

    journal = build_decision_journal(
        review_date="2026-05-30",
        review_session_id="p8-smoke",
        reviewer_id="operator",
        source_artifact_root="outputs",
        events=_decision_input_events(),
    )
    journal_paths = write_decision_journal(journal, p7_dir)
    journal_rows = load_decision_journal_read_model_rows(journal_paths["json_path"])
    decision_events = pd.DataFrame(journal_rows["events"])

    review = build_decision_outcome_review(
        start_date="2026-05-30",
        end_date="2026-06-30",
        decision_events=decision_events,
        bars=_synthetic_bars(),
        horizons=[1, 5, 20],
        run_id="p8-smoke-outcome-2026-05-30-2026-06-30",
    )
    outcome_paths = write_decision_outcome_review(review, p8_dir)
    outcome_rows = load_decision_outcome_read_model_rows(outcome_paths["json_path"])

    outcomes_by_id = {str(row["event_id"]): row for row in review["outcomes"]}
    return {
        "p7_journal_json_path": journal_paths["json_path"],
        "p8_outcome_json_path": outcome_paths["json_path"],
        "p8_outcome_details_csv_path": outcome_paths["details_csv_path"],
        "p8_outcome_summary_csv_path": outcome_paths["summary_csv_path"],
        "p8_outcome_markdown_path": outcome_paths["markdown_path"],
        "journal_decision_count": int(journal["decision_count"]),
        "outcome_count": int(review["outcome_count"]),
        "read_model_event_count": len(outcome_rows["events"]),
        "decision_labels": [str(row["decision_label"]) for row in review["outcomes"]],
        "manual_review_required": bool(review["manual_review_required"]),
        "auto_trade_enabled": bool(review["auto_trade_enabled"]),
        "source_artifact_paths": [str(row["source_artifact_path"]) for row in outcome_rows["events"]],
        "forward_1d_returns": {
            event_id: outcomes_by_id[event_id]["forward_1d_return"]
            for event_id in sorted(outcomes_by_id)
        },
        "forward_1d_returns_by_label": {
            str(row["decision_label"]): row["forward_1d_return"]
            for row in review["outcomes"]
        },
    }


def _decision_input_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_date": "2026-05-30",
                "review_session_id": "p8-smoke",
                "reviewer_id": "operator",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "strong score",
            },
            {
                "review_date": "2026-05-30",
                "review_session_id": "p8-smoke",
                "reviewer_id": "operator",
                "asset_id": "CN:SZ:000001",
                "stock_code": "000001.SZ",
                "stock_name": "Beta",
                "decision_label": "caution",
                "evidence_artifact_id": "watchlist:2026-05-30",
                "evidence_path": "outputs/p5/watchlist.json",
                "source_context": "watchlist",
                "requires_follow_up": False,
                "follow_up_note": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "risk active",
            },
        ]
    )


def _synthetic_bars() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for asset_id, base_close in [("CN:SH:600001", 10.0), ("CN:SZ:000001", 20.0)]:
        for offset in range(0, 21):
            close = base_close + offset if asset_id == "CN:SH:600001" else base_close - offset * 0.5
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": (pd.Timestamp("2026-05-30") + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                    "close": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                }
            )
    return pd.DataFrame(rows)
