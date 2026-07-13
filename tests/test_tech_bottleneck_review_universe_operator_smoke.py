from __future__ import annotations

import json
from pathlib import Path

from stock_research.dashboard import tech_bottleneck_review_decisions as decisions
from stock_research.tech_bottleneck_review_universe_operator_smoke import run_audit, run_smoke


def _payload(stock_code: str = "000777", decision: str = "need_more_evidence", comment: str = "需要补证") -> dict:
    return {
        "stock_code": stock_code,
        "stock_name": "中核科技",
        "reviewer_decision": decision,
        "reviewer": "operator",
        "review_comment": comment,
        "rubric_flags": {"hard_tech": True, "page_level_evidence": True},
        "evidence_checked": True,
        "source_context": {"from": "operator_smoke_test"},
    }


def _setup_tmp_overlay(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(decisions, "OVERLAY_DIR", tmp_path / "overlay")
    decisions.load_ledger.cache_clear()
    decisions.load_current_overlay.cache_clear()


def test_operator_smoke_dry_run_does_not_write_ledger(monkeypatch, tmp_path):
    _setup_tmp_overlay(monkeypatch, tmp_path)

    result = run_smoke(dry_run=True, output_dir=tmp_path / "smoke")
    expected_total = len(decisions.review_universe_stock_codes())

    assert result["write_performed"] is False
    assert result["frontend_dataset_count"] == expected_total
    assert result["summary_after"]["reviewed_count"] == 0
    assert result["summary_after"]["pending_count"] == expected_total
    assert result["frontend_dataset_hash_before"] == result["frontend_dataset_hash_after"]
    assert result["frozen_v7_generated"] is False
    assert result["used_for_signal_count"] == 0
    assert result["used_for_admission_count"] == 0
    assert not (tmp_path / "overlay" / decisions.LEDGER_PATH_NAME).exists()
    assert (tmp_path / "smoke" / "operator_smoke_summary.json").exists()
    assert (tmp_path / "smoke" / "operator_smoke_summary.md").exists()


def test_operator_smoke_write_test_requires_token_comment_and_evidence_checked(monkeypatch, tmp_path):
    _setup_tmp_overlay(monkeypatch, tmp_path)
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")

    missing_token = run_smoke(
        dry_run=False,
        write_test_decision=True,
        stock_code="000777",
        decision="need_more_evidence",
        comment="需要补证",
        evidence_checked=True,
        write_token="",
        output_dir=tmp_path / "missing_token",
    )
    missing_comment = run_smoke(
        dry_run=False,
        write_test_decision=True,
        stock_code="000777",
        decision="need_more_evidence",
        comment="",
        evidence_checked=True,
        write_token="secret",
        output_dir=tmp_path / "missing_comment",
    )
    missing_evidence_checked = run_smoke(
        dry_run=False,
        write_test_decision=True,
        stock_code="000777",
        decision="need_more_evidence",
        comment="需要补证",
        evidence_checked=False,
        write_token="secret",
        output_dir=tmp_path / "missing_evidence",
    )

    assert missing_token["acceptance_decision"] == "blocked_due_to_missing_write_token"
    assert missing_comment["acceptance_decision"] == "blocked_due_to_missing_comment"
    assert missing_evidence_checked["acceptance_decision"] == "blocked_due_to_missing_evidence_checked"
    assert not (tmp_path / "overlay" / decisions.LEDGER_PATH_NAME).exists()


def test_operator_smoke_write_test_updates_overlay_without_mutating_frontend_dataset(monkeypatch, tmp_path):
    _setup_tmp_overlay(monkeypatch, tmp_path)
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")

    result = run_smoke(
        dry_run=False,
        write_test_decision=True,
        stock_code="000777",
        decision="need_more_evidence",
        comment="测试写入：需要补充一手证据。",
        evidence_checked=True,
        write_token="secret",
        output_dir=tmp_path / "write_test",
    )
    expected_total = len(decisions.review_universe_stock_codes())

    assert result["write_performed"] is True
    assert result["written_stock_code"] == "000777"
    assert result["written_decision"] == "need_more_evidence"
    assert result["summary_before"]["reviewed_count"] == 0
    assert result["summary_after"]["reviewed_count"] == 1
    assert result["summary_after"]["pending_count"] == expected_total - 1
    assert result["frontend_dataset_hash_before"] == result["frontend_dataset_hash_after"]
    assert result["frozen_v7_generated"] is False
    assert result["used_for_signal_count"] == 0
    assert result["used_for_admission_count"] == 0
    assert (tmp_path / "overlay" / decisions.LEDGER_PATH_NAME).exists()


def test_decision_audit_counts_corrections_and_guardrails(monkeypatch, tmp_path):
    _setup_tmp_overlay(monkeypatch, tmp_path)
    decisions.record_manual_decision(_payload(decision="hold", comment="先保留"))
    decisions.record_manual_decision(_payload(decision="reject", comment="改判为证据不支持"))

    audit = run_audit(output_dir=tmp_path / "audit")
    expected_total = len(decisions.review_universe_stock_codes())

    assert audit["total_review_universe_count"] == expected_total
    assert audit["ledger_entry_count"] == 2
    assert audit["unique_reviewed_stock_count"] == 1
    assert audit["current_overlay_count"] == 1
    assert audit["correction_supersede_count"] == 1
    assert audit["reject_count"] == 1
    assert audit["invalid_decision_count"] == 0
    assert audit["unknown_stock_code_count"] == 0
    assert audit["missing_comment_count"] == 0
    assert audit["missing_evidence_checked_count"] == 0
    assert audit["frozen_v7_generated"] is False
    assert audit["used_for_signal_count"] == 0
    assert audit["used_for_admission_count"] == 0
    current_overlay_csv = tmp_path / "audit" / "manual_decision_current_overlay.csv"
    assert current_overlay_csv.exists()
    assert json.loads((tmp_path / "audit" / "manual_decision_overlay_audit.json").read_text(encoding="utf-8"))[
        "correction_supersede_count"
    ] == 1
