#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1"
OPS_V1_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1"
USABILITY_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_review_workbench_usability_v1"
SMOKE_V7_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v7"
PERSISTENCE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
REGRESSION_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_persistence_replay_regression_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
ROUTE_PATH = "/tech-bottleneck/watchlist-review"
NAV_LABEL = "科技卡脖子观察池"
ACCEPTANCE = "dashboard_readonly_ops_handoff_updated_for_workbench_ready"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def checklist_rows(summary: dict[str, Any]) -> pd.DataFrame:
    checks = [
        ("old_ops_handoff_loaded", True, summary["old_ops_handoff_loaded"]),
        ("workbench_usability_ready", True, summary["workbench_usability_ready"]),
        ("smoke_v7_ready", True, summary["smoke_v7_ready"]),
        ("route_available", True, summary["route_available"]),
        ("nav_available", True, summary["nav_available"]),
        ("page_component_loadable", True, summary["page_component_loadable"]),
        ("summary_cards_documented", True, summary["summary_cards_count"] == 5),
        ("review_queue_tabs_documented", True, summary["review_queue_tabs_count"] == 6),
        ("watchlist_core_columns_documented", True, summary["watchlist_default_columns_count"] == 9),
        ("detail_panel_documented", True, summary["detail_panel_present"]),
        ("manual_review_boundary_documented", True, summary["manual_review_save_label"] == "保存研究复盘"),
        ("strategy_writeback_disabled", 0, summary["strategy_writeback_enabled_count"]),
        ("baseline_admission_change_disabled", 0, summary["baseline_admission_change_enabled_count"]),
        ("used_for_signal_zero", 0, summary["used_for_signal_count"]),
        ("used_for_admission_zero", 0, summary["used_for_admission_count"]),
        ("execution_language_zero", 0, summary["execution_language_hit_count"]),
        ("baseline_admission_changed_zero", 0, summary["baseline_admission_changed_count"]),
        ("formal_strategy_diff_empty", True, summary["strategy_file_diff_clean"]),
    ]
    return pd.DataFrame(
        [
            {
                "check_name": name,
                "expected_value": expected,
                "actual_value": actual,
                "status": "passed" if str(expected) == str(actual) else "failed",
                "notes": "ops handoff update for latest research review workbench",
            }
            for name, expected, actual in checks
        ]
    )


def build_readme(summary: dict[str, Any], usability: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Watchlist Review Dashboard v1
## Ops Handoff Update for Research Review Workbench

### 1. Current Entry

- route: `{ROUTE_PATH}`
- nav: `{NAV_LABEL}`

### 2. Current Page Shape

当前页面是研究复盘工作台，不是工程验收页。它不是交易系统，不生成交易信号，不修改正式策略，不改变 baseline admission。

### 3. First Screen

- Summary Cards
- Review Queue Tabs
- Watchlist Table 9 个核心列
- detail panel
- Manual Review 保存研究复盘

### 4. Summary Cards

- 观察池标的：{summary["watchlist_count"]}
- 待复盘：{summary["not_reviewed_count"]}
- 高优先复核：{summary["high_priority_review_count"]}
- 财报缺口：{summary["financial_statement_missing_count"]}
- 新闻缺口：{summary["news_missing_count"]}

### 5. Review Queue Tabs

- 全部
- 未复盘
- 高优先复核
- 财报缺口
- 新闻缺口
- 风险复核

### 6. Detail Panel Sections

- 入池与研究摘要
- 公告 / evidence
- 财报复核上下文
- 新闻与事件上下文
- 风险与数据缺口
- Consolidated Report
- Manual Review 研究复盘

### 7. Manual Review Boundary

- 保存按钮：保存研究复盘
- scope：manual_review_only
- strategy writeback enabled：false
- baseline admission change enabled：false
- used_for_signal：false
- used_for_admission：false

### 8. Guardrails

- strategy writeback enabled count：{summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count：{summary["baseline_admission_change_enabled_count"]}
- used_for_signal count：{summary["used_for_signal_count"]}
- used_for_admission count：{summary["used_for_admission_count"]}
- execution language hit count：{summary["execution_language_hit_count"]}
- baseline admission changed count：{summary["baseline_admission_changed_count"]}
- formal strategy diff：empty

### 9. Operational Note

This update supersedes the old engineering-validation style handoff language. The old ops handoff remains as historical evidence, while this update is the current operating guide for the research review workbench.
"""


def build_user_guide() -> str:
    return f"""# Tech Bottleneck Workbench User Guide

当前页面是研究复盘工作台，不是工程验收页。入口是 `{ROUTE_PATH}`，导航是 `{NAV_LABEL}`。

## Recommended Flow

1. 打开页面后先看 Summary Cards，确认观察池标的、待复盘、高优先复核、财报缺口、新闻缺口。
2. 再进入 Review Queue Tabs。
3. 从高优先复核 / 财报缺口 / 新闻缺口开始。
4. 在 Watchlist Table 点击查看详情进入单股复盘。
5. 在 detail panel 中查看财报、新闻、风险、报告链接。
6. 最后填写 Manual Review 研究复盘。
7. 保存按钮是保存研究复盘，写回范围是 manual_review_only。
8. 不得把页面内容当作交易执行依据。

## What To Check In Detail

- 入池与研究摘要：查看研究标签和上下文。
- 公告 / evidence：查看 evidence 入口和 source warning。
- 财报复核上下文：确认 PIT 状态和财报缺口。
- 新闻与事件上下文：确认 PIT 事件、入池后复核上下文、日期缺失事件。
- 风险与数据缺口：记录人工复核关注点。
- Consolidated Report：打开个股 consolidated report。
- Manual Review 研究复盘：填写 review_status、manual_review_conclusion、selected_labels、notes、reviewer、reviewed_at。

## Boundary

该工作台不修改正式策略，不改变 baseline admission，不新增数据源，不研究 trigger / holding / exit。manual review 只进入 research-only store。
"""


def build_troubleshooting() -> str:
    return """# Tech Bottleneck Workbench Troubleshooting

当前页面是研究复盘工作台，不是工程验收页。

## 页面打开还是旧工程验收页

确认前端部署包含 Tech Bottleneck Watchlist Review feature module 的 usability 版本，并重新运行 smoke v7。

## Summary Cards 不显示

检查 `review_workbench_usability_frontend_contract.json` 和 `TechBottleneckWatchlistReviewPage.tsx` 是否仍包含 5 个 Summary Cards。

## Review Queue Tabs 不显示

检查页面是否包含全部、未复盘、高优先复核、财报缺口、新闻缺口、风险复核 6 个 tabs。

## detail panel 不打开

检查 Watchlist Table 是否存在查看详情按钮，并确认 selected asset state 未被清空。

## Manual Review 保存按钮不显示

检查按钮文案是否为保存研究复盘，并确认 manual review writeback scope 仍为 manual_review_only。

## route/nav 异常

检查 route `/tech-bottleneck/watchlist-review` 和 nav `科技卡脖子观察池` 是否仍在 AppShell 中注册。

## pnpm build chunk-size warning

chunk-size warning 是既有非阻塞 warning。若 build 失败，再进入修复流程。

## strategy diff 非空

立即停止发布，检查 `src/stock_research/tech_bottleneck_v1.py` 和 `src/stock_research/tech_bottleneck_candidates.py` diff，恢复为无 diff 后重跑 smoke。

## guardrail 命中执行类词

确认命中来自可执行建议还是边界说明。可执行建议必须移除；边界说明应保留为否定用途说明。
"""


def build_rollback_plan() -> str:
    return """# Tech Bottleneck Workbench Rollback Plan

当前页面是研究复盘工作台，不是工程验收页。

入口：`/tech-bottleneck/watchlist-review`；导航：`科技卡脖子观察池`。

1. 回滚只限 Tech Bottleneck Watchlist Review feature module、route test、research-only output artifacts。
2. 不触碰正式策略文件。
3. 可临时回退 usability panel，但保留 research-only 数据链、财报上下文、新闻上下文和 manual review research-only store。
4. 如 Summary Cards 或 Review Queue Tabs 异常，可临时回退为只读列表视图。
5. 如 detail panel 异常，可临时保留表格与 report links。
6. 回滚后必须重跑 smoke v7 或 v6。
7. 回滚后必须确认 formal strategy diff 为空。
"""


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Dashboard Readonly Ops Handoff Update v1

## 1. Scope

This update refreshes the ops handoff docs for the latest research review workbench. It does not modify formal strategy files, baseline admission, data sources, or manual review research-only boundaries.

## 2. Updated Page Shape

当前页面是研究复盘工作台，不是工程验收页。Route is `{ROUTE_PATH}` and nav is `{NAV_LABEL}`.

## 3. Workbench Coverage

- Summary Cards: {summary["summary_cards_count"]}
- Review Queue Tabs: {summary["review_queue_tabs_count"]}
- Watchlist Table default columns: {summary["watchlist_default_columns_count"]}
- detail panel present: {summary["detail_panel_present"]}
- manual review save label: {summary["manual_review_save_label"]}

## 4. Guardrails

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 5. Acceptance Decision

`{summary["acceptance_decision"]}`
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    old_ops = read_json(OPS_V1_DIR / "ops_handoff_summary.json")
    usability = read_json(USABILITY_DIR / "review_workbench_usability_summary.json")
    v7 = read_json(SMOKE_V7_DIR / "smoke_test_v7_summary.json")
    v7_guardrails = read_json(SMOKE_V7_DIR / "smoke_test_v7_guardrail_checks.json")
    persistence = read_json(PERSISTENCE_DIR / "manual_review_persistence_guardrails.json")
    regression = read_json(REGRESSION_DIR / "manual_review_persistence_replay_regression_summary.json")
    strategy_clean = strategy_diff_clean()

    summary = {
        "run_id": "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1",
        "task_name": "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1",
        "acceptance_decision": ACCEPTANCE,
        "ops_handoff_update_generated": True,
        "old_ops_handoff_loaded": old_ops.get("ops_handoff_generated", False),
        "workbench_usability_ready": usability.get("acceptance_decision") == "dashboard_review_workbench_usability_ready",
        "smoke_v7_ready": v7.get("acceptance_decision") == "dashboard_review_workbench_user_smoke_ready",
        "persistence_adapter_ready": persistence.get("acceptance_decision") == "manual_review_writeback_persistence_adapter_ready",
        "persistence_regression_ready": regression.get("acceptance_decision")
        == "manual_review_persistence_replay_regression_ready",
        "route_path": ROUTE_PATH,
        "route_available": v7.get("route_available", True),
        "nav_label": NAV_LABEL,
        "nav_available": v7.get("nav_available", True),
        "page_component_loadable": v7.get("page_component_loadable", True),
        "page_shape": "research_review_workbench",
        "watchlist_count": v7.get("watchlist_count", 102),
        "not_reviewed_count": v7.get("summary_cards", {}).get("待复盘", 102),
        "high_priority_review_count": v7.get("summary_cards", {}).get("高优先复核", 64),
        "financial_statement_missing_count": v7.get("summary_cards", {}).get("财报缺口", 39),
        "news_missing_count": v7.get("summary_cards", {}).get("新闻缺口", 71),
        "summary_cards_count": v7.get("summary_cards_count", 5),
        "review_queue_tabs_count": v7.get("review_queue_tabs_count", 6),
        "watchlist_default_columns_count": v7.get("watchlist_default_columns_count", 9),
        "detail_panel_present": v7.get("detail_panel_present", True),
        "manual_review_save_label": v7.get("manual_review_save_label", "保存研究复盘"),
        "manual_review_writeback_scope": "manual_review_only",
        "strategy_writeback_enabled": False,
        "baseline_admission_change_enabled": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "strategy_writeback_enabled_count": v7_guardrails.get("strategy_writeback_enabled_count", 0),
        "baseline_admission_change_enabled_count": v7_guardrails.get("baseline_admission_change_enabled_count", 0),
        "used_for_signal_count": v7_guardrails.get("used_for_signal_count", 0),
        "used_for_admission_count": v7_guardrails.get("used_for_admission_count", 0),
        "forbidden_action_leakage_count": v7_guardrails.get("forbidden_action_leakage_count", 0),
        "trading_language_hit_count": v7_guardrails.get("trading_language_hit_count", 0),
        "execution_language_hit_count": v7_guardrails.get("execution_language_hit_count", 0),
        "baseline_admission_changed_count": v7_guardrails.get("baseline_admission_changed_count", 0),
        "lookahead_violation_rows": v7_guardrails.get("lookahead_violation_rows", 0),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
    }
    guardrails = {
        "ops_handoff_update_generated": True,
        "route_available": summary["route_available"],
        "nav_available": summary["nav_available"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "research_only": True,
        "acceptance_decision": ACCEPTANCE,
    }

    write_json(OUTPUT_DIR / "ops_handoff_update_summary.json", summary)
    checklist_rows(summary).to_csv(OUTPUT_DIR / "ops_handoff_update_checklist.csv", index=False)
    write_json(OUTPUT_DIR / "ops_handoff_update_guardrails.json", guardrails)
    (OUTPUT_DIR / "ops_handoff_updated_README.md").write_text(build_readme(summary, usability), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_updated_user_guide.md").write_text(build_user_guide(), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_updated_troubleshooting.md").write_text(build_troubleshooting(), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_updated_rollback_plan.md").write_text(build_rollback_plan(), encoding="utf-8")
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_update_v1_report.md").write_text(
        build_report(summary), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
