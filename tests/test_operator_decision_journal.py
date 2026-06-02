import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.journal import (
    DECISION_JOURNAL_COLUMNS,
    build_decision_journal,
    validate_decision_events,
    write_decision_journal,
)


def _decision_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "reviewer_id": "operator",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/dashboard/topn_2026-05-30.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "strong score and clean watchlist signal",
            },
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "reviewer_id": "operator",
                "asset_id": "CN:SZ:000001",
                "stock_code": "000001.SZ",
                "stock_name": "Beta",
                "decision_label": "caution",
                "evidence_artifact_id": "watchlist:2026-05-30",
                "evidence_path": "outputs/p5/watchlist_2026-05-30.json",
                "source_context": "watchlist",
                "requires_follow_up": False,
                "follow_up_note": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "risk signal still active",
            },
        ]
    )


def test_build_decision_journal_normalizes_events_and_requires_manual_review():
    journal = build_decision_journal(
        review_date="2026-05-30",
        review_session_id="morning-review",
        reviewer_id="operator",
        source_artifact_root="outputs",
        events=_decision_events(),
    )

    assert journal["status"] == "review_recorded"
    assert journal["review_date"] == "2026-05-30"
    assert journal["review_session_id"] == "morning-review"
    assert journal["decision_count"] == 2
    assert journal["decision_label_counts"] == {"candidate": 1, "caution": 1}
    assert journal["manual_review_required"] is True
    assert journal["auto_trade_enabled"] is False
    assert journal["issues"] == []
    assert [item["asset_id"] for item in journal["items"]] == ["CN:SH:600001", "CN:SZ:000001"]
    assert all(item["manual_review_required"] is True for item in journal["items"])
    assert all(item["auto_trade_enabled"] is False for item in journal["items"])


def test_build_decision_journal_allows_empty_review_without_fake_decisions():
    journal = build_decision_journal(
        review_date="2026-05-30",
        review_session_id="empty-review",
        reviewer_id="operator",
        source_artifact_root="outputs",
        events=pd.DataFrame(columns=DECISION_JOURNAL_COLUMNS),
    )

    assert journal["status"] == "no_decisions_recorded"
    assert journal["decision_count"] == 0
    assert journal["decision_label_counts"] == {}
    assert journal["items"] == []
    assert journal["manual_review_required"] is True
    assert journal["auto_trade_enabled"] is False


def test_validate_decision_events_rejects_missing_evidence_invalid_labels_and_execution_fields():
    unsafe_events = pd.DataFrame(
        [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "reviewer_id": "operator",
                "asset_id": "CN:SH:600001",
                "decision_label": "buy",
                "evidence_artifact_id": "",
                "evidence_path": "",
                "requires_follow_up": False,
                "manual_review_required": False,
                "auto_trade_enabled": True,
                "execution_status": "submitted",
                "order_id": "order-1",
            }
        ]
    )

    issues = validate_decision_events(unsafe_events)

    assert {issue["code"] for issue in issues} == {
        "invalid_decision_label",
        "missing_evidence",
        "manual_review_required",
        "auto_trade_not_allowed",
        "execution_field_not_allowed",
    }


def test_build_decision_journal_raises_for_invalid_events():
    with pytest.raises(ValueError, match="invalid_decision_label"):
        build_decision_journal(
            review_date="2026-05-30",
            review_session_id="morning-review",
            reviewer_id="operator",
            source_artifact_root="outputs",
            events=pd.DataFrame(
                [
                    {
                        "review_date": "2026-05-30",
                        "review_session_id": "morning-review",
                        "reviewer_id": "operator",
                        "asset_id": "CN:SH:600001",
                        "decision_label": "sell",
                        "evidence_artifact_id": "dashboard:topn:2026-05-30",
                        "evidence_path": "outputs/p6/dashboard/topn_2026-05-30.json",
                        "requires_follow_up": False,
                        "manual_review_required": True,
                        "auto_trade_enabled": False,
                    }
                ]
            ),
        )


def test_write_decision_journal_outputs_json_csv_and_markdown(tmp_path):
    journal = build_decision_journal(
        review_date="2026-05-30",
        review_session_id="morning-review",
        reviewer_id="operator",
        source_artifact_root="outputs",
        events=_decision_events(),
    )

    paths = write_decision_journal(journal, output_dir=tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    rows = pd.read_csv(paths["csv_path"])
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert payload["review_session_id"] == "morning-review"
    assert payload["decision_count"] == 2
    assert rows["decision_label"].tolist() == ["candidate", "caution"]
    assert "Operator Decision Journal 2026-05-30" in markdown
    assert "manual_review_required" in markdown
    assert "auto_trade_enabled: `False`" in markdown
