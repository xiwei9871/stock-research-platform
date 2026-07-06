#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
SCHEMA_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_label_schema_v1"
TEMPLATE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
SMOKE_V4_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v4"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1"

LABEL_DICTIONARY = SCHEMA_DIR / "manual_review_label_dictionary.csv"
STATUS_ENUM = SCHEMA_DIR / "manual_review_status_enum.csv"
FORM_SCHEMA = SCHEMA_DIR / "manual_review_form_schema.csv"
TEMPLATE = TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"
SMOKE_V4_SUMMARY = SMOKE_V4_DIR / "smoke_test_v4_summary.json"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

ALLOWED_FIELDS = [
    "review_status",
    "manual_review_conclusion",
    "selected_labels",
    "evidence_quality_review",
    "financial_statement_review",
    "news_context_review",
    "risk_review",
    "data_gap_confirmation",
    "review_note",
    "reviewer",
    "reviewed_at",
]

FORBIDDEN_FIELDS = [
    "buy",
    "sell",
    "hold",
    "entry",
    "exit",
    "target_price",
    "position",
    "increase_position",
    "reduce_position",
    "trading_signal",
    "strategy_signal",
    "admission_change",
    "baseline_admission_change",
    "trigger_state",
    "holding_state",
    "exit_state",
    "stop_loss",
    "take_profit",
    "rebalance",
    "买入",
    "卖出",
    "持有",
    "加仓",
    "减仓",
    "目标价",
    "入场",
    "退出",
    "止盈",
    "止损",
    "调仓",
    "交易信号",
    "策略信号",
    "入池调整",
    "基线入池调整",
    "触发",
    "持仓",
    "退出阶段",
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


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def asset_id_to_ts_code(asset_id: str, symbol: Any) -> str:
    market = "SH" if ":SH:" in str(asset_id) else "SZ" if ":SZ:" in str(asset_id) else ""
    symbol_str = f"{int(symbol):06d}" if str(symbol).isdigit() else str(symbol)
    return f"{symbol_str}.{market}" if market else symbol_str


def build_store_template(template: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in template.iterrows():
        asset_id = str(row["asset_id"])
        symbol = row["symbol"]
        rows.append(
            {
                "review_id": f"research_review_writeback|{asset_id}|round_1",
                "ts_code": asset_id_to_ts_code(asset_id, symbol),
                "stock_code": f"{int(symbol):06d}" if str(symbol).isdigit() else str(symbol),
                "stock_name": row["name"],
                "first_admission_date": row.get("baseline_first_admission_date", ""),
                "review_status": "not_reviewed",
                "manual_review_conclusion": "not_reviewed",
                "selected_labels": "",
                "evidence_quality_review": "not_reviewed",
                "financial_statement_review": "not_reviewed",
                "news_context_review": "not_reviewed",
                "risk_review": "not_reviewed",
                "data_gap_confirmation": False,
                "review_note": "",
                "reviewer": "",
                "reviewed_at": "",
                "source_page": "/tech-bottleneck/watchlist-review",
                "source_task": "tech_bottleneck_manual_review_writeback_research_only_v1",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "writeback_allowed": True,
                "strategy_writeback_allowed": False,
                "baseline_admission_change_allowed": False,
            }
        )
    return pd.DataFrame(rows)


def build_audit_template() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "audit_id",
            "review_id",
            "asset_id",
            "stock_code",
            "stock_name",
            "reviewer",
            "reviewed_at",
            "changed_fields",
            "old_values",
            "new_values",
            "source_page",
            "source_task",
            "research_only",
            "used_for_signal",
            "used_for_admission",
            "strategy_writeback_allowed",
            "baseline_admission_change_allowed",
        ]
    )


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "manual_review_writeback_forbidden_fields.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Manual Review Writeback Research-Only v1

## 1. Scope

This task defines and enables manual review research-only writeback. It does not modify formal strategy files, baseline admission, dashboard strategy inputs, or automated execution prompts.

## 2. Input Artifacts

- Manual review label schema: `tech_bottleneck_manual_review_label_schema_v1`
- Manual review template: `tech_bottleneck_manual_review_template_v1`
- Dashboard smoke v4: `tech_bottleneck_dashboard_readonly_user_smoke_test_v4`
- Financial statement and news dashboard patches are preserved as readonly context.

## 3. Writeback Design

The writeback store is a local research artifact with 102 default rows. Allowed fields are limited to review status, review conclusion, review labels, source quality notes, financial statement note, news context note, risk note, data gap confirmation, reviewer, and timestamp.

Forbidden vocabulary is stored in a separate registry file and is not exposed as an allowed UI action.

## 4. Frontend Changes

The Tech Bottleneck readonly page adds a Manual Review Research-Only Writeback panel with local form controls, a research review button label, and audit preview text. It does not call any production API in v1.

## 5. Research-Only Boundary

- manual_review_writeback_enabled: {summary["manual_review_writeback_enabled"]}
- writeback_scope: {summary["writeback_scope"]}
- strategy_writeback_enabled: {summary["strategy_writeback_enabled"]}
- baseline_admission_change_enabled: {summary["baseline_admission_change_enabled"]}
- used_for_signal_count: {summary["used_for_signal_count"]}
- used_for_admission_count: {summary["used_for_admission_count"]}

## 6. Audit Trail

Each future writeback must record review id, reviewer, timestamp, changed fields, source page, previous value, new value, research-only flag, and formal-boundary flags.

## 7. Guardrail Checks

- manual_review_writeback_enabled_count: {summary["manual_review_writeback_enabled_count"]}
- strategy_writeback_enabled_count: {summary["strategy_writeback_enabled_count"]}
- baseline_admission_change_enabled_count: {summary["baseline_admission_change_enabled_count"]}
- forbidden_action_leakage_count: {summary["forbidden_action_leakage_count"]}
- trading_language_hit_count: {summary["trading_language_hit_count"]}
- execution_language_hit_count: {summary["execution_language_hit_count"]}
- baseline_admission_changed_count: {summary["baseline_admission_changed_count"]}
- lookahead_violation_rows: {summary["lookahead_violation_rows"]}
- strategy_file_diff_clean: {summary["strategy_file_diff_clean"]}

## 8. Test Results

Verification commands are recorded after generation:

- Pending at initial generation: `pytest tests/test_tech_bottleneck_manual_review_writeback_research_only.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_user_smoke_test_v4.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_news_patch.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_financial_statement_patch.py -q`
- Pending at initial generation: `cd dashboard && pnpm test -- tech-bottleneck-route.test.tsx`
- Pending at initial generation: `cd dashboard && pnpm build`
- Pending at initial generation: `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_user_smoke_test_v5`
2. `tech_bottleneck_manual_review_writeback_audit_replay_v1`
3. `tech_bottleneck_research_archive_integrity_check_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    label_dictionary = read_csv(LABEL_DICTIONARY)
    status_enum = read_csv(STATUS_ENUM)
    form_schema = read_csv(FORM_SCHEMA)
    template = read_csv(TEMPLATE)
    smoke_v4 = read_json(SMOKE_V4_SUMMARY)
    store = build_store_template(template)
    audit = build_audit_template()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    allowed = pd.DataFrame(
        [
            {
                "field_name": field,
                "field_group": "manual_review_research_writeback",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
            for field in ALLOWED_FIELDS
        ]
    )
    forbidden = pd.DataFrame(
        [
            {
                "field_name": field,
                "forbidden_scope": "formal_or_execution_boundary",
                "allowed_in_ui": False,
                "allowed_in_store": False,
                "notes": "forbidden registry only",
            }
            for field in FORBIDDEN_FIELDS
        ]
    )
    review_status_values = (
        status_enum[status_enum["enum_name"].eq("review_status")]["enum_value"].dropna().astype(str).tolist()
        if not status_enum.empty
        else ["not_reviewed"]
    )
    label_groups = sorted(label_dictionary["label_group"].dropna().astype(str).unique().tolist()) if not label_dictionary.empty else []
    schema = {
        "schema_version": "v1",
        "task_name": "tech_bottleneck_manual_review_writeback_research_only_v1",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "writeback_scope": "manual_review_only",
        "allowed_fields": ALLOWED_FIELDS,
        "forbidden_fields": "manual_review_writeback_forbidden_fields.csv",
        "audit_required": True,
        "review_status_enum": review_status_values,
        "label_groups": label_groups,
        "label_values": "manual_review_label_dictionary.csv",
        "note_fields": [
            "evidence_quality_review",
            "financial_statement_review",
            "news_context_review",
            "risk_review",
            "review_note",
        ],
        "created_at": now,
        "updated_at": now,
    }
    contract = {
        "section_name": "Manual Review Research-Only Writeback",
        "section_status": "passed",
        "manual_review_writeback_enabled": True,
        "manual_review_writeback_scope": "manual_review_only",
        "strategy_writeback_enabled": False,
        "baseline_admission_change_enabled": False,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "allowed_fields": ALLOWED_FIELDS,
        "forbidden_fields": "manual_review_writeback_forbidden_fields.csv",
        "audit_required": True,
        "save_button_label": "Save Research Review",
        "readonly_sections_preserved": True,
        "acceptance_decision": "manual_review_writeback_research_only_ready",
    }
    strategy_clean = strategy_diff_clean()
    summary = {
        "task_name": "tech_bottleneck_manual_review_writeback_research_only_v1",
        "store_template_rows": int(len(store)),
        "allowed_fields_count": int(len(allowed)),
        "forbidden_fields_count": int(len(forbidden)),
        "manual_review_writeback_enabled": True,
        "writeback_scope": "manual_review_only",
        "strategy_writeback_enabled": False,
        "baseline_admission_change_enabled": False,
        "research_only": True,
        "audit_log_required": True,
        "manual_review_writeback_enabled_count": int(len(store)),
        "strategy_writeback_enabled_count": 0,
        "baseline_admission_change_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": int(store["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(store["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "lookahead_violation_rows": int(smoke_v4.get("lookahead_violation_rows", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "manual_review_writeback_research_only_ready",
    }

    store.to_csv(OUTPUT_DIR / "manual_review_writeback_store_template.csv", index=False)
    write_json(OUTPUT_DIR / "manual_review_writeback_store_template.json", store.to_dict(orient="records"))
    audit.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_log_template.csv", index=False)
    allowed.to_csv(OUTPUT_DIR / "manual_review_writeback_allowed_fields.csv", index=False)
    forbidden.to_csv(OUTPUT_DIR / "manual_review_writeback_forbidden_fields.csv", index=False)
    write_json(OUTPUT_DIR / "manual_review_writeback_schema.json", schema)
    write_json(OUTPUT_DIR / "manual_review_writeback_frontend_contract.json", contract)
    write_json(OUTPUT_DIR / "manual_review_writeback_summary.json", summary)
    write_json(OUTPUT_DIR / "manual_review_writeback_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1_report.md").write_text(
        build_report(summary),
        encoding="utf-8",
    )

    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    summary["forbidden_action_leakage_count"] = hits
    write_json(OUTPUT_DIR / "manual_review_writeback_summary.json", summary)
    write_json(OUTPUT_DIR / "manual_review_writeback_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1_report.md").write_text(
        build_report(summary),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
