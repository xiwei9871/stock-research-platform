from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_hard_tech_requalification_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_seed_tier_a_hard_tech_requalification.py"
CORE_POOL = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> tuple[str, str]:
    before = _sha(CORE_POOL)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after = _sha(CORE_POOL)
    return before, after


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_seed_tier_a_requalification_outputs_and_guardrails() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "seed_tier_a_requalification_summary.json",
        "seed_tier_a_requalification.csv",
        "confirmed_core_hard_tech_bottleneck.csv",
        "hard_tech_adjacent_watchlist.csv",
        "evidence_backfill_required.csv",
        "downgrade_manual_review_required.csv",
        "reject_seed_pollution.csv",
        "revised_core_pool_preview.csv",
        "tech_bottleneck_seed_tier_a_hard_tech_requalification_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "seed_tier_a_requalification_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["seed_tier_a_audited_count"] == 86
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["existing_workbench_core_candidates_modified"] is False
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["revised_core_pool_preview_count"] <= 114


def test_seed_tier_a_requalification_classifies_obvious_contaminants() -> None:
    _run_generator()
    df = pd.read_csv(OUTPUT_DIR / "seed_tier_a_requalification.csv")
    confirmed = pd.read_csv(OUTPUT_DIR / "confirmed_core_hard_tech_bottleneck.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "reject_seed_pollution.csv")
    preview = pd.read_csv(OUTPUT_DIR / "revised_core_pool_preview.csv")

    assert len(df) == 86
    assert set(df["source_group"]) == {"seed_tier_a"}
    assert not set(["渝农商行", "浙商银行", "建设银行", "中信银行"]).intersection(set(confirmed["stock_name"]))
    assert set(["渝农商行", "浙商银行", "建设银行", "中信银行"]).issubset(set(rejected["stock_name"]))
    assert "佛山照明" not in set(confirmed["stock_name"])
    assert "通宝能源" not in set(confirmed["stock_name"])
    assert df.loc[df["stock_name"].eq("佛山照明"), "final_requalification_category"].iloc[0] != "confirmed_core_hard_tech_bottleneck"
    assert df.loc[df["stock_name"].eq("通宝能源"), "final_requalification_category"].iloc[0] != "confirmed_core_hard_tech_bottleneck"
    assert df.loc[df["stock_name"].eq("许继电气"), "final_requalification_category"].iloc[0] != "reject_seed_pollution"
    assert df.loc[df["stock_name"].eq("艾罗能源"), "final_requalification_category"].iloc[0] != "confirmed_core_hard_tech_bottleneck"
    assert not set(["佛山照明", "通宝能源", "渝农商行", "浙商银行", "建设银行", "中信银行"]).intersection(
        set(preview["stock_name"])
    )


def test_seed_labels_alone_do_not_confirm_core_and_outputs_are_deterministic() -> None:
    _run_generator()
    first = _hash_outputs()
    _run_generator()
    second = _hash_outputs()
    assert first == second

    df = pd.read_csv(OUTPUT_DIR / "seed_tier_a_requalification.csv")
    inherited_only = df["primary_source_evidence_available"].astype(bool).eq(False)
    assert not df.loc[inherited_only, "final_requalification_category"].eq("confirmed_core_hard_tech_bottleneck").any()
    assert not df["used_for_signal"].astype(bool).any()
    assert not df["used_for_admission"].astype(bool).any()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
