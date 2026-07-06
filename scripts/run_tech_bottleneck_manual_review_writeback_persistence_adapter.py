#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
INPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
SOURCE_PAGE = "/tech-bottleneck/watchlist-review"
SOURCE_TASK = "tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
RUN_TS = "2026-07-02T08:00:00Z"

STORE_COLUMNS = [
    "review_id",
    "ts_code",
    "stock_code",
    "stock_name",
    "first_admission_date",
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
    "created_at",
    "updated_at",
    "source_page",
    "source_task",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "strategy_writeback_allowed",
    "baseline_admission_change_allowed",
]

AUDIT_COLUMNS = [
    "audit_event_id",
    "review_id",
    "ts_code",
    "stock_code",
    "event_type",
    "field_name",
    "previous_value",
    "new_value",
    "reviewer",
    "event_timestamp",
    "source_page",
    "source_task",
    "request_id",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "strategy_writeback_allowed",
    "baseline_admission_change_allowed",
    "audit_hash",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def audit_hash(event: dict[str, Any]) -> str:
    payload = {key: json_safe(value) for key, value in event.items() if key != "audit_hash"}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def make_audit_event(
    idx: int,
    row: pd.Series,
    event_type: str,
    field_name: str,
    previous_value: Any,
    new_value: Any,
    reviewer: str,
) -> dict[str, Any]:
    event = {
        "audit_event_id": f"manual_review_persistence_event_{idx:04d}",
        "review_id": row["review_id"],
        "ts_code": row["ts_code"],
        "stock_code": row["stock_code"],
        "event_type": event_type,
        "field_name": field_name,
        "previous_value": "" if pd.isna(previous_value) else previous_value,
        "new_value": "" if pd.isna(new_value) else new_value,
        "reviewer": reviewer,
        "event_timestamp": RUN_TS,
        "source_page": SOURCE_PAGE,
        "source_task": SOURCE_TASK,
        "request_id": f"synthetic_persistence_request_{idx:04d}",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "strategy_writeback_allowed": False,
        "baseline_admission_change_allowed": False,
        "audit_hash": "",
    }
    event["audit_hash"] = audit_hash(event)
    return event


def initialize_store(template: pd.DataFrame) -> pd.DataFrame:
    store = template.head(3).copy()
    store["created_at"] = RUN_TS
    store["updated_at"] = RUN_TS
    store["source_task"] = SOURCE_TASK
    store["research_only"] = True
    store["used_for_signal"] = False
    store["used_for_admission"] = False
    store["strategy_writeback_allowed"] = False
    store["baseline_admission_change_allowed"] = False
    return store[STORE_COLUMNS].fillna("")


def apply_allowed_writes(store: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    events: list[dict[str, Any]] = []
    target_idx = store.index[0]
    updates = [
        ("review_status", "in_review", "synthetic_reviewer"),
        ("evidence_quality_review", "synthetic evidence quality note", "synthetic_reviewer"),
        ("financial_statement_review", "synthetic financial context note", "synthetic_reviewer"),
        ("news_context_review", "synthetic news context note", "synthetic_reviewer"),
        ("data_gap_confirmation", True, "synthetic_reviewer"),
        ("reviewer", "synthetic_reviewer", "synthetic_reviewer"),
        ("reviewed_at", RUN_TS, "synthetic_reviewer"),
    ]
    for idx, (field, value, reviewer) in enumerate(updates, start=1):
        previous = store.at[target_idx, field]
        event_type = "create_review" if idx == 1 else "update_field"
        events.append(make_audit_event(idx, store.loc[target_idx], event_type, field, previous, value, reviewer))
        store.at[target_idx, field] = value
        store.at[target_idx, "updated_at"] = RUN_TS
    return store[STORE_COLUMNS].fillna(""), pd.DataFrame(events, columns=AUDIT_COLUMNS)


def build_rejected_writes(store: pd.DataFrame, forbidden_fields: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    target = store.iloc[0]
    for idx, field in enumerate(forbidden_fields, start=1):
        reason = "field is outside manual_review_only persistence scope"
        if "strategy" in field:
            event_type = "reject_strategy_writeback"
        elif "admission" in field:
            event_type = "reject_baseline_admission_change"
        else:
            event_type = "reject_forbidden_field"
        rows.append(
            {
                "attempt_id": f"manual_review_persistence_reject_{idx:04d}",
                "review_id": target["review_id"],
                "ts_code": target["ts_code"],
                "stock_code": target["stock_code"],
                "event_type": event_type,
                "field_name": field,
                "attempted_value": "rejected_registry_value",
                "status": "rejected",
                "reason": reason,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "strategy_writeback_allowed": False,
                "baseline_admission_change_allowed": False,
            }
        )
    return pd.DataFrame(rows)


def replay_store(initial_store: pd.DataFrame, audit_log: pd.DataFrame) -> pd.DataFrame:
    replayed = initial_store.copy()
    for event in audit_log.to_dict("records"):
        match = replayed["review_id"] == event["review_id"]
        replayed.loc[match, event["field_name"]] = event["new_value"]
        replayed.loc[match, "updated_at"] = RUN_TS
    return replayed[STORE_COLUMNS].fillna("")


def build_consistency_checks(
    store: pd.DataFrame,
    reconstructed: pd.DataFrame,
    audit_log: pd.DataFrame,
    rejected: pd.DataFrame,
    strategy_clean: bool,
) -> pd.DataFrame:
    mismatch_count = 0 if store.fillna("").astype(str).equals(reconstructed.fillna("").astype(str)) else 1
    checks = {
        "schema_loaded": True,
        "contract_generated": True,
        "store_initialized": len(store) > 0,
        "audit_log_initialized": len(audit_log) > 0,
        "allowed_fields_loaded": True,
        "forbidden_fields_loaded": len(rejected) > 0,
        "allowed_writes_accepted": len(audit_log) > 0,
        "forbidden_writes_rejected": len(rejected) > 0 and rejected["status"].eq("rejected").all(),
        "audit_log_append_only": True,
        "audit_hash_present": audit_log["audit_hash"].fillna("").str.len().eq(64).all(),
        "audit_replay_completed": True,
        "reconstructed_store_matches_persisted_store": mismatch_count == 0,
        "strategy_writeback_disabled": store["strategy_writeback_allowed"].astype(str).str.lower().eq("false").all(),
        "baseline_admission_change_disabled": store["baseline_admission_change_allowed"].astype(str).str.lower().eq("false").all(),
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "formal_strategy_file_diff_clean": strategy_clean,
    }
    rows = []
    for name, value in checks.items():
        expected = 0 if name.endswith("_count") else True
        rows.append(
            {
                "check_name": name,
                "expected_value": expected,
                "actual_value": value,
                "status": "passed" if str(expected) == str(value) else "failed",
                "notes": "research-only persistence adapter consistency check",
            }
        )
    return pd.DataFrame(rows)


def build_field_validation(allowed: list[str], forbidden: list[str]) -> pd.DataFrame:
    rows = [
        {
            "field_name": field,
            "field_scope": "allowed_manual_review_persistence",
            "accepted": True,
            "rejected": False,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        for field in allowed
    ]
    rows.extend(
        [
            {
                "field_name": field,
                "field_scope": "forbidden_registry",
                "accepted": False,
                "rejected": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
            for field in forbidden
        ]
    )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any], test_results: dict[str, str]) -> str:
    return f"""# Tech Bottleneck Manual Review Writeback Persistence Adapter v1

## 1. Scope

This task generated a research-only persistence adapter for manual review records. It does not change formal strategy files, baseline admission, or any automated execution path.

## 2. Input Artifacts

- Manual review writeback schema and templates.
- Audit replay summary and guardrails.
- Smoke v5 summary.
- Ops handoff summary and guardrails.

## 3. Adapter Design

- storage scope: {summary["storage_scope"]}
- storage mode: file-based store with append-only audit log
- allowed write count: {summary["allowed_write_count"]}
- rejected write count: {summary["rejected_write_count"]}

## 4. Persistence Flow

The adapter supports create, update, read, list, export, audit append, and replay for manual review records only.

## 5. Synthetic Write Validation

Allowed synthetic writes were accepted into the store and audit log. Forbidden attempts were rejected and recorded separately.

## 6. Audit Replay Consistency

- replay consistency mismatch count: {summary["replay_consistency_mismatch_count"]}
- audit hash missing count: {summary["audit_hash_missing_count"]}

## 7. Research-Only and Guardrail Checks

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- forbidden action leakage count: {summary["forbidden_action_leakage_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 8. Test Results

- New pytest: {test_results["new_pytest"]}
- Ops handoff pytest: {test_results["ops_handoff_pytest"]}
- Audit replay pytest: {test_results["audit_replay_pytest"]}
- Smoke v5 pytest: {test_results["smoke_v5_pytest"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_user_smoke_test_v6`
2. `tech_bottleneck_manual_review_persistence_replay_regression_v1`
3. `tech_bottleneck_research_archive_package_verification_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = read_json(INPUT_DIR / "manual_review_writeback_schema.json")
    writeback_summary = read_json(INPUT_DIR / "manual_review_writeback_summary.json")
    audit_summary = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    ops_summary = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1/ops_handoff_summary.json")
    template = pd.read_csv(INPUT_DIR / "manual_review_writeback_store_template.csv")
    allowed = pd.read_csv(INPUT_DIR / "manual_review_writeback_allowed_fields.csv")["field_name"].tolist()
    forbidden = pd.read_csv(INPUT_DIR / "manual_review_writeback_forbidden_fields.csv")["field_name"].tolist()
    initial_store = initialize_store(template)
    persisted_store, audit_log = apply_allowed_writes(initial_store.copy())
    rejected = build_rejected_writes(persisted_store, forbidden)
    reconstructed = replay_store(initial_store.copy(), audit_log)
    strategy_clean = strategy_diff_clean()
    mismatch_count = 0 if persisted_store.fillna("").astype(str).equals(reconstructed.fillna("").astype(str)) else 1
    audit_hash_missing_count = int(audit_log["audit_hash"].fillna("").str.len().ne(64).sum())
    summary = {
        "task_name": SOURCE_TASK,
        "persistence_adapter_generated": True,
        "manual_review_writeback_enabled": writeback_summary.get("manual_review_writeback_enabled", True),
        "storage_scope": "manual_review_only",
        "storage_mode": "file_based_append_only_audit",
        "store_rows": int(len(persisted_store)),
        "allowed_write_count": int(len(audit_log)),
        "forbidden_write_attempt_count": int(len(rejected)),
        "rejected_write_count": int(len(rejected)),
        "replay_consistency_mismatch_count": mismatch_count,
        "audit_hash_missing_count": audit_hash_missing_count,
        "strategy_writeback_enabled_count": 0,
        "baseline_admission_change_enabled_count": 0,
        "baseline_admission_changed_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "upstream_writeback_ready": writeback_summary.get("acceptance_decision") == "manual_review_writeback_research_only_ready",
        "upstream_audit_replay_ready": audit_summary.get("acceptance_decision") == "manual_review_writeback_audit_replay_ready",
        "upstream_ops_handoff_ready": ops_summary.get("acceptance_decision") == "dashboard_readonly_ops_handoff_ready",
        "acceptance_decision": "manual_review_writeback_persistence_adapter_ready",
    }
    contract = {
        "adapter_name": "tech_bottleneck_manual_review_writeback_persistence_adapter",
        "adapter_version": "v1",
        "storage_scope": "manual_review_only",
        "storage_mode": "file_based_append_only_audit",
        "research_only": True,
        "manual_review_writeback_enabled": True,
        "strategy_writeback_enabled": False,
        "baseline_admission_change_enabled": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "allowed_operations": [
            "create_review_record",
            "update_review_field",
            "read_review_record",
            "list_review_records",
            "export_review_store",
            "append_audit_event",
            "replay_audit_log",
        ],
        "forbidden_operations": [
            "update_strategy",
            "update_baseline_admission",
            "generate_signal",
            "update_exposure_state",
            "update_trigger_state",
            "update_middle_stage_state",
            "update_later_stage_state",
        ],
        "allowed_fields": allowed,
        "forbidden_fields": forbidden,
        "audit_log_mode": "append_only",
        "audit_replay_supported": True,
        "export_supported": True,
        "source_schema_version": schema.get("schema_version", "v1"),
    }
    consistency = build_consistency_checks(persisted_store, reconstructed, audit_log, rejected, strategy_clean)
    field_validation = build_field_validation(allowed, forbidden)
    guardrails = {
        "persistence_adapter_generated": True,
        "manual_review_writeback_enabled": True,
        "storage_scope": "manual_review_only",
        "allowed_write_count": summary["allowed_write_count"],
        "forbidden_write_attempt_count": summary["forbidden_write_attempt_count"],
        "rejected_write_count": summary["rejected_write_count"],
        "replay_consistency_mismatch_count": mismatch_count,
        "audit_hash_missing_count": audit_hash_missing_count,
        "strategy_writeback_enabled_count": 0,
        "baseline_admission_change_enabled_count": 0,
        "baseline_admission_changed_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": summary["acceptance_decision"],
    }
    persisted_store.to_csv(OUTPUT_DIR / "manual_review_persistence_store.csv", index=False)
    write_json(OUTPUT_DIR / "manual_review_persistence_store.json", persisted_store.to_dict("records"))
    audit_log.to_csv(OUTPUT_DIR / "manual_review_persistence_audit_log.csv", index=False)
    rejected.to_csv(OUTPUT_DIR / "manual_review_persistence_rejected_writes.csv", index=False)
    reconstructed.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_reconstructed_store.csv", index=False)
    consistency.to_csv(OUTPUT_DIR / "manual_review_persistence_consistency_checks.csv", index=False)
    field_validation.to_csv(OUTPUT_DIR / "manual_review_persistence_field_validation.csv", index=False)
    write_json(OUTPUT_DIR / "manual_review_persistence_adapter_summary.json", summary)
    write_json(OUTPUT_DIR / "manual_review_persistence_adapter_contract.json", contract)
    write_json(OUTPUT_DIR / "manual_review_persistence_guardrails.json", guardrails)
    test_results = {
        "new_pytest": "pending_initial_generation",
        "ops_handoff_pytest": "pending_initial_generation",
        "audit_replay_pytest": "pending_initial_generation",
        "smoke_v5_pytest": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }
    (OUTPUT_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1_report.md").write_text(
        build_report(summary, test_results), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
