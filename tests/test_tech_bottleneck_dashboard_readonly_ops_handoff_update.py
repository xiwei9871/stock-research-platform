from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_ops_handoff_update_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_ops_handoff_update_outputs_and_summary_exist() -> None:
    expected = {
        "ops_handoff_update_summary.json",
        "ops_handoff_update_checklist.csv",
        "ops_handoff_update_guardrails.json",
        "ops_handoff_updated_user_guide.md",
        "ops_handoff_updated_README.md",
        "ops_handoff_updated_troubleshooting.md",
        "ops_handoff_updated_rollback_plan.md",
        "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "ops_handoff_update_summary.json").read_text(encoding="utf-8"))
    assert summary["acceptance_decision"] == "dashboard_readonly_ops_handoff_updated_for_workbench_ready"
    assert summary["ops_handoff_update_generated"] is True
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["page_component_loadable"] is True
    assert summary["workbench_usability_ready"] is True
    assert summary["smoke_v7_ready"] is True
    assert summary["summary_cards_count"] == 5
    assert summary["review_queue_tabs_count"] == 6
    assert summary["watchlist_default_columns_count"] == 9
    assert summary["detail_panel_present"] is True
    assert summary["manual_review_save_label"] == "保存研究复盘"


def test_ops_handoff_update_docs_reflect_latest_workbench_shape() -> None:
    readme = (OUTPUT_DIR / "ops_handoff_updated_README.md").read_text(encoding="utf-8")
    user_guide = (OUTPUT_DIR / "ops_handoff_updated_user_guide.md").read_text(encoding="utf-8")
    troubleshooting = (OUTPUT_DIR / "ops_handoff_updated_troubleshooting.md").read_text(encoding="utf-8")
    rollback = (OUTPUT_DIR / "ops_handoff_updated_rollback_plan.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1_report.md").read_text(
        encoding="utf-8"
    )

    for text in [readme, user_guide, troubleshooting, rollback, report]:
        assert "研究复盘工作台" in text
        assert "工程验收页" in text
        assert "/tech-bottleneck/watchlist-review" in text
        assert "科技卡脖子观察池" in text

    for required in ["观察池标的：102", "待复盘：102", "高优先复核：64", "财报缺口：39", "新闻缺口：71"]:
        assert required in readme

    for required in ["全部", "未复盘", "高优先复核", "财报缺口", "新闻缺口", "风险复核"]:
        assert required in readme

    for required in [
        "入池与研究摘要",
        "公告 / evidence",
        "财报复核上下文",
        "新闻与事件上下文",
        "风险与数据缺口",
        "Consolidated Report",
        "Manual Review 研究复盘",
    ]:
        assert required in readme

    assert "保存研究复盘" in readme
    assert "manual_review_only" in readme
    assert "先看 Summary Cards" in user_guide
    assert "Review Queue Tabs" in user_guide
    assert "点击查看详情" in user_guide
    assert "不得把页面内容当作交易执行依据" in user_guide
    for required in [
        "旧工程验收页",
        "Summary Cards 不显示",
        "Review Queue Tabs 不显示",
        "detail panel 不打开",
        "Manual Review 保存按钮不显示",
        "route/nav 异常",
        "chunk-size warning",
        "strategy diff 非空",
        "guardrail 命中执行类词",
    ]:
        assert required in troubleshooting
    assert "不触碰正式策略文件" in rollback
    assert "重跑 smoke v7 或 v6" in rollback


def test_ops_handoff_update_checklist_guardrails_and_strategy_diff_are_clean() -> None:
    checklist = pd.read_csv(OUTPUT_DIR / "ops_handoff_update_checklist.csv")
    guardrails = json.loads((OUTPUT_DIR / "ops_handoff_update_guardrails.json").read_text(encoding="utf-8"))
    summary = json.loads((OUTPUT_DIR / "ops_handoff_update_summary.json").read_text(encoding="utf-8"))

    assert set(checklist["status"]) == {"passed"}
    for payload in [guardrails, summary]:
        assert payload["strategy_writeback_enabled_count"] == 0
        assert payload["baseline_admission_change_enabled_count"] == 0
        assert payload["used_for_signal_count"] == 0
        assert payload["used_for_admission_count"] == 0
        assert payload["forbidden_action_leakage_count"] == 0
        assert payload["trading_language_hit_count"] == 0
        assert payload["execution_language_hit_count"] == 0
        assert payload["baseline_admission_changed_count"] == 0
        assert payload["strategy_file_diff_clean"] is True
        assert payload["formal_strategy_files_modified"] is False
        assert payload["research_only"] is True

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
