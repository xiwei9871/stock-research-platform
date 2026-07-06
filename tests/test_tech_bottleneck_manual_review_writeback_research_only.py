from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_research_only_v1"
FRONTEND_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|hold|entry|exit|target price|increase position|reduce position|"
        r"target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
    re.compile(r"提交策略|生成信号|确认买入|确认卖出|入池调整"),
]


def _has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def test_manual_review_writeback_outputs_and_schema_are_valid() -> None:
    expected = {
        "manual_review_writeback_summary.json",
        "manual_review_writeback_schema.json",
        "manual_review_writeback_store_template.csv",
        "manual_review_writeback_store_template.json",
        "manual_review_writeback_audit_log_template.csv",
        "manual_review_writeback_allowed_fields.csv",
        "manual_review_writeback_forbidden_fields.csv",
        "manual_review_writeback_frontend_contract.json",
        "manual_review_writeback_guardrails.json",
        "tech_bottleneck_manual_review_writeback_research_only_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "manual_review_writeback_summary.json").read_text(encoding="utf-8"))
    schema = json.loads((OUTPUT_DIR / "manual_review_writeback_schema.json").read_text(encoding="utf-8"))
    contract = json.loads((OUTPUT_DIR / "manual_review_writeback_frontend_contract.json").read_text(encoding="utf-8"))
    assert summary["manual_review_writeback_enabled"] is True
    assert summary["writeback_scope"] == "manual_review_only"
    assert summary["strategy_writeback_enabled"] is False
    assert summary["baseline_admission_change_enabled"] is False
    assert summary["research_only"] is True
    assert summary["audit_log_required"] is True
    assert schema["research_only"] is True
    assert schema["used_for_signal"] is False
    assert schema["used_for_admission"] is False
    assert schema["writeback_scope"] == "manual_review_only"
    assert schema["audit_required"] is True
    assert isinstance(schema["allowed_fields"], list)
    assert schema["forbidden_fields"] == "manual_review_writeback_forbidden_fields.csv"
    assert contract["manual_review_writeback_enabled"] is True
    assert contract["strategy_writeback_enabled"] is False
    assert contract["baseline_admission_change_enabled"] is False
    assert contract["research_only"] is True
    assert contract["used_for_signal"] is False
    assert contract["used_for_admission"] is False
    assert contract["audit_required"] is True
    assert contract["save_button_label"] == "Save Research Review"


def test_store_template_allowed_forbidden_fields_and_audit_are_valid() -> None:
    store = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_store_template.csv")
    audit = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_log_template.csv")
    allowed = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_allowed_fields.csv")
    forbidden = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_forbidden_fields.csv")
    assert len(store) == 102
    assert len(audit) == 0
    assert store["review_status"].eq("not_reviewed").all()
    assert store["manual_review_conclusion"].eq("not_reviewed").all()
    assert store["research_only"].astype(str).str.lower().eq("true").all()
    assert store["used_for_signal"].astype(str).str.lower().eq("false").all()
    assert store["used_for_admission"].astype(str).str.lower().eq("false").all()
    assert store["writeback_allowed"].astype(str).str.lower().eq("true").all()
    assert store["strategy_writeback_allowed"].astype(str).str.lower().eq("false").all()
    assert store["baseline_admission_change_allowed"].astype(str).str.lower().eq("false").all()
    assert {"review_id", "review_status", "manual_review_conclusion", "review_note", "reviewer", "reviewed_at"}.issubset(
        set(store.columns)
    )
    forbidden_fields = set(forbidden["field_name"])
    allowed_fields = set(allowed["field_name"])
    assert {"buy", "sell", "target_price", "position", "trading_signal", "baseline_admission_change"}.issubset(
        forbidden_fields
    )
    assert {"买入", "卖出", "交易信号", "基线入池调整"}.issubset(forbidden_fields)
    assert allowed_fields.isdisjoint(forbidden_fields)
    assert {"changed_fields", "old_values", "new_values", "source_page"}.issubset(set(audit.columns))


def test_guardrails_frontend_contract_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "manual_review_writeback_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["manual_review_writeback_enabled_count"] > 0
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["audit_log_required"] is True

    page = (FRONTEND_DIR / "TechBottleneckWatchlistReviewPage.tsx").read_text(encoding="utf-8")
    data = (FRONTEND_DIR / "techBottleneckReadonlyData.ts").read_text(encoding="utf-8")
    types = (FRONTEND_DIR / "types.ts").read_text(encoding="utf-8")
    route_test = ROUTE_TEST.read_text(encoding="utf-8")
    assert "Manual Review Research-Only Writeback" in page
    assert "Save Research Review" in page
    assert "techBottleneckManualReviewWritebackContract" in data
    assert "TechBottleneckManualReviewWritebackContract" in types
    assert "Save Research Review" in route_test
    for text in [page, data, types, route_test]:
        assert not _has_forbidden_language(text)

    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "manual_review_writeback_forbidden_fields.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            assert not _has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")), path

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
