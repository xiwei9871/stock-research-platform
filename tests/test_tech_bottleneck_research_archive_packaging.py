from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_archive_packaging_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
]


def _has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def test_package_outputs_and_readiness_flags_exist() -> None:
    expected = {
        "research_archive_package_summary.json",
        "research_archive_package_manifest.csv",
        "research_archive_package_file_index.csv",
        "research_archive_package_checksums.csv",
        "research_archive_package_guardrails.json",
        "research_archive_package_usage_boundary.md",
        "research_archive_package_known_limitations.md",
        "research_archive_package_handoff_notes.md",
        "research_archive_package_README.md",
        "tech_bottleneck_research_archive_packaging_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "research_archive_package_summary.json").read_text(encoding="utf-8"))
    assert summary["package_generated"] is True
    assert summary["package_manifest_generated"] is True
    assert summary["package_checksums_generated"] is True
    assert summary["release_notes_ready"] is True
    assert summary["archive_integrity_ready"] is True
    assert summary["smoke_v5_ready"] is True
    assert summary["manual_review_writeback_ready"] is True
    assert summary["audit_replay_ready"] is True
    assert summary["acceptance_decision"] == "research_archive_packaging_ready"


def test_package_manifest_file_index_and_checksums_are_valid() -> None:
    manifest = pd.read_csv(OUTPUT_DIR / "research_archive_package_manifest.csv")
    file_index = pd.read_csv(OUTPUT_DIR / "research_archive_package_file_index.csv")
    checksums = pd.read_csv(OUTPUT_DIR / "research_archive_package_checksums.csv")
    assert len(manifest) > 0
    assert len(file_index) > 0
    assert len(checksums) > 0
    assert manifest["checksum_sha256"].fillna("").str.len().eq(64).all()
    assert checksums["checksum_sha256"].fillna("").str.len().eq(64).all()
    assert manifest["research_only"].astype(str).str.lower().eq("true").all()
    assert manifest["used_for_signal"].astype(str).str.lower().eq("false").all()
    assert manifest["used_for_admission"].astype(str).str.lower().eq("false").all()
    assert manifest["included_in_package"].astype(str).str.lower().eq("true").any()
    assert {"internal_research", "reviewer", "auditor", "ops_handoff"}.issubset(set(file_index["consumer"]))


def test_package_guardrails_docs_and_formal_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "research_archive_package_guardrails.json").read_text(encoding="utf-8"))
    readme = (OUTPUT_DIR / "research_archive_package_README.md").read_text(encoding="utf-8")
    usage = (OUTPUT_DIR / "research_archive_package_usage_boundary.md").read_text(encoding="utf-8")
    limitations = (OUTPUT_DIR / "research_archive_package_known_limitations.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "tech_bottleneck_research_archive_packaging_v1_report.md").read_text(encoding="utf-8")
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert "research-only" in readme
    assert "Forbidden Usage" in usage
    assert "Known Limitations" in limitations
    for text in [readme, usage, limitations, report]:
        assert not _has_forbidden_language(text)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
