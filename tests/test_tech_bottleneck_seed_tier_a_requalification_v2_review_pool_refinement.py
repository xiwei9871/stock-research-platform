from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement"
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


def test_v2_outputs_and_summary_guardrails() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "requalification_v2_summary.json",
        "seed_tier_a_requalification_v2.csv",
        "verified_core_candidates.csv",
        "manual_anchor_core_pending_evidence.csv",
        "likely_hard_tech_pending_evidence.csv",
        "adjacent_pending_evidence.csv",
        "low_priority_evidence_backfill.csv",
        "reject_seed_pollution.csv",
        "hard_tech_review_pool_preview.csv",
        "dashboard_pool_migration_preview.csv",
        "tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement_report.md",
    }
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "requalification_v2_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["verified_core_count"] == 28
    assert summary["hard_tech_review_pool_preview_count"] > 28
    assert summary["hard_tech_review_pool_preview_count"] < 114
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["existing_workbench_core_candidates_modified"] is False


def test_v2_pool_retains_hard_tech_anchors_and_excludes_pollution() -> None:
    _run_generator()
    seed_v2 = pd.read_csv(OUTPUT_DIR / "seed_tier_a_requalification_v2.csv", dtype={"stock_code": str})
    pool = pd.read_csv(OUTPUT_DIR / "hard_tech_review_pool_preview.csv", dtype={"stock_code": str})
    verified = pd.read_csv(OUTPUT_DIR / "verified_core_candidates.csv", dtype={"stock_code": str})

    assert len(seed_v2) == 86
    assert {"北方华创", "中微公司"}.issubset(set(pool["stock_name"]))
    assert set(
        seed_v2.loc[
            seed_v2["stock_name"].isin(["北方华创", "中微公司"]),
            "requalification_v2_category",
        ]
    ) == {"manual_anchor_core_pending_evidence"}
    assert {"北方华创", "中微公司"}.issubset(
        set(
            pd.read_csv(
                OUTPUT_DIR / "manual_anchor_core_pending_evidence.csv",
                dtype={"stock_code": str},
            )["stock_name"]
        )
    )

    excluded_names = {"佛山照明", "通宝能源", "渝农商行", "浙商银行", "建设银行", "中信银行"}
    assert not excluded_names.intersection(set(pool["stock_name"]))
    assert {"京泉华", "浙江力诺"}.issubset(set(verified["stock_name"]))
    assert {"京泉华", "浙江力诺"}.issubset(set(pool["stock_name"]))


def test_v2_outputs_are_deterministic_and_do_not_touch_formal_strategy() -> None:
    _run_generator()
    first = _hash_outputs()
    _run_generator()
    second = _hash_outputs()
    assert first == second

    pool = pd.read_csv(OUTPUT_DIR / "hard_tech_review_pool_preview.csv", dtype={"stock_code": str})
    assert not pool["allowed_for_signal"].astype(bool).any()
    assert not pool["allowed_for_admission"].astype(bool).any()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
