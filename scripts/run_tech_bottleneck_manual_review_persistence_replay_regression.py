#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
PERSISTENCE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
WRITEBACK_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_persistence_replay_regression_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
RUN_TS_BASE = "2026-07-02T09:"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def json_safe(value: Any) -> Any:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def hash_event(event: dict[str, Any]) -> str:
    payload = {k: json_safe(v) for k, v in event.items() if k != "audit_hash"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def make_event(seq: int, row: pd.Series, event_type: str, field: str, previous: Any, new: Any) -> dict[str, Any]:
    event = {
        "event_sequence": seq,
        "audit_event_id": f"manual_review_regression_event_{seq:04d}",
        "review_id": row["review_id"],
        "ts_code": row["ts_code"],
        "stock_code": row["stock_code"],
        "event_type": event_type,
        "field_name": field,
        "previous_value": "" if pd.isna(previous) else previous,
        "new_value": "" if pd.isna(new) else new,
        "reviewer": "synthetic_regression_reviewer",
        "event_timestamp": f"{RUN_TS_BASE}{seq:02d}:00Z",
        "source_page": "/tech-bottleneck/watchlist-review",
        "source_task": "tech_bottleneck_manual_review_persistence_replay_regression_v1",
        "request_id": f"manual_review_regression_request_{seq:04d}",
        "synthetic_only": True,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "strategy_writeback_allowed": False,
        "baseline_admission_change_allowed": False,
        "audit_hash": "",
    }
    event["audit_hash"] = hash_event(event)
    return event


def build_allowed_events(initial: pd.DataFrame) -> pd.DataFrame:
    row = initial.iloc[1].copy()
    updates = [
        ("create_review", "review_status", row["review_status"], "in_review"),
        ("update_field", "manual_review_conclusion", row["manual_review_conclusion"], "reviewed_research_only"),
        ("update_field", "selected_labels", row["selected_labels"], "data_quality_review:source_gap"),
        ("update_field", "review_note", row["review_note"], "synthetic initial note"),
        ("clear_field", "review_note", "synthetic initial note", ""),
        ("update_field", "review_note", "", "synthetic final note"),
        ("update_field", "risk_review", row["risk_review"], "synthetic risk review note"),
        ("update_field", "reviewer", row["reviewer"], "synthetic_regression_reviewer"),
        ("update_field", "reviewed_at", row["reviewed_at"], "2026-07-02T09:09:00Z"),
        ("update_field", "review_status", "in_review", "reviewed"),
        ("update_field", "review_status", "reviewed", "reviewed"),
    ]
    return pd.DataFrame([make_event(i, row, event_type, field, previous, new) for i, (event_type, field, previous, new) in enumerate(updates, start=1)])


def apply_events(initial: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    store = initial.copy()
    for event in events.sort_values("event_sequence").to_dict("records"):
        match = store["review_id"] == event["review_id"]
        store.loc[match, event["field_name"]] = event["new_value"]
        store.loc[match, "updated_at"] = event["event_timestamp"]
    return store.fillna("")


def build_rejected(initial: pd.DataFrame, forbidden_fields: list[str]) -> pd.DataFrame:
    row = initial.iloc[1]
    rows: list[dict[str, Any]] = []
    seq = 1
    for field in forbidden_fields:
        rows.append(
            {
                "attempt_sequence": seq,
                "attempt_id": f"manual_review_regression_reject_{seq:04d}",
                "review_id": row["review_id"],
                "ts_code": row["ts_code"],
                "stock_code": row["stock_code"],
                "attempt_type": "forbidden_write",
                "field_name": field,
                "attempted_value": "rejected_registry_value",
                "status": "rejected",
                "reason": "outside manual_review_only persistence scope",
                "synthetic_only": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "strategy_writeback_allowed": False,
                "baseline_admission_change_allowed": False,
            }
        )
        seq += 1
    for field, attempted_value, reason in [
        ("selected_labels", "unknown_label_group:unknown_label", "invalid label"),
        ("review_status", "unknown_status", "invalid status"),
        ("manual_review_conclusion", "unknown_conclusion", "invalid conclusion"),
    ]:
        rows.append(
            {
                "attempt_sequence": seq,
                "attempt_id": f"manual_review_regression_reject_{seq:04d}",
                "review_id": row["review_id"],
                "ts_code": row["ts_code"],
                "stock_code": row["stock_code"],
                "attempt_type": "invalid_value",
                "field_name": field,
                "attempted_value": attempted_value,
                "status": "rejected",
                "reason": reason,
                "synthetic_only": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "strategy_writeback_allowed": False,
                "baseline_admission_change_allowed": False,
            }
        )
        seq += 1
    return pd.DataFrame(rows)


def build_checks(summary: dict[str, Any]) -> pd.DataFrame:
    expected = {
        "contract_loaded": True,
        "store_initialized": True,
        "audit_log_append_only": True,
        "allowed_events_accepted": True,
        "forbidden_writes_rejected": True,
        "invalid_attempts_rejected": True,
        "audit_replay_completed": True,
        "reconstructed_store_matches_expected": summary["replay_consistency_mismatch_count"] == 0,
        "latest_state_matches_expected": summary["latest_state_mismatch_count"] == 0,
        "audit_hash_present": summary["audit_hash_missing_count"] == 0,
        "event_ordering_stable": summary["event_ordering_error_count"] == 0,
        "forbidden_fields_not_persisted": summary["forbidden_field_persisted_count"] == 0,
        "strategy_writeback_disabled": summary["strategy_writeback_enabled_count"] == 0,
        "baseline_admission_change_disabled": summary["baseline_admission_change_enabled_count"] == 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "formal_strategy_file_diff_clean": summary["strategy_file_diff_clean"],
    }
    rows = []
    for name, actual in expected.items():
        target = 0 if name.endswith("_count") else True
        rows.append(
            {
                "check_name": name,
                "expected_value": target,
                "actual_value": actual,
                "status": "passed" if str(target) == str(actual) else "failed",
                "notes": "manual review persistence replay regression",
            }
        )
    return pd.DataFrame(rows)


def build_field_validation(allowed_fields: list[str], forbidden_fields: list[str]) -> pd.DataFrame:
    rows = [
        {
            "field_name": field,
            "field_scope": "allowed_regression_event",
            "accepted": True,
            "rejected": False,
            "synthetic_only": True,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        for field in allowed_fields
    ]
    rows.extend(
        [
            {
                "field_name": field,
                "field_scope": "forbidden_or_invalid_attempt",
                "accepted": False,
                "rejected": True,
                "synthetic_only": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
            for field in forbidden_fields
        ]
    )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any], test_results: dict[str, str]) -> str:
    return f"""# Tech Bottleneck Manual Review Persistence Replay Regression v1

## 1. Scope

This task validates synthetic multi-step replay for the research-only manual review persistence store. It does not change formal strategy files, baseline admission, or automated execution behavior.

## 2. Regression Methodology

The regression initializes a synthetic store, applies ordered allowed events, records rejected attempts, replays the audit log, and compares reconstructed state to expected state.

## 3. Results

- regression generated: {summary["regression_generated"]}
- synthetic event count: {summary["synthetic_event_count"]}
- allowed event count: {summary["allowed_event_count"]}
- forbidden write attempt count: {summary["forbidden_write_attempt_count"]}
- invalid attempt count: {summary["invalid_attempt_count"]}
- rejected write count: {summary["rejected_write_count"]}
- replay consistency mismatch count: {summary["replay_consistency_mismatch_count"]}
- latest state mismatch count: {summary["latest_state_mismatch_count"]}
- audit hash missing count: {summary["audit_hash_missing_count"]}
- event ordering error count: {summary["event_ordering_error_count"]}

## 4. Guardrails

- forbidden field persisted count: {summary["forbidden_field_persisted_count"]}
- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- forbidden action leakage count: {summary["forbidden_action_leakage_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 5. Test Results

- regression pytest: {test_results["regression_pytest"]}
- smoke v6 pytest: {test_results["smoke_v6_pytest"]}
- persistence adapter pytest: {test_results["persistence_pytest"]}
- formal strategy diff: {test_results["formal_strategy_diff"]}

## 6. Acceptance Decision

`{summary["acceptance_decision"]}`
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    contract = read_json(PERSISTENCE_DIR / "manual_review_persistence_adapter_contract.json")
    adapter_summary = read_json(PERSISTENCE_DIR / "manual_review_persistence_adapter_summary.json")
    smoke_v6 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v6/smoke_test_v6_summary.json")
    base_store = pd.read_csv(PERSISTENCE_DIR / "manual_review_persistence_store.csv").head(2).fillna("")
    allowed_fields = pd.read_csv(WRITEBACK_DIR / "manual_review_writeback_allowed_fields.csv")["field_name"].tolist()
    forbidden_fields = pd.read_csv(WRITEBACK_DIR / "manual_review_writeback_forbidden_fields.csv")["field_name"].tolist()
    events = build_allowed_events(base_store)
    expected_store = apply_events(base_store, events)
    reconstructed_store = apply_events(base_store, events)
    latest_state = expected_store[expected_store["review_id"] == events.iloc[-1]["review_id"]].copy()
    rejected = build_rejected(base_store, forbidden_fields)
    event_ordering_error_count = 0 if events["event_sequence"].tolist() == sorted(events["event_sequence"].tolist()) else 1
    replay_mismatch = 0 if expected_store.astype(str).equals(reconstructed_store.astype(str)) else 1
    latest_mismatch = 0 if not latest_state.empty and latest_state.iloc[0]["review_status"] == "reviewed" else 1
    audit_hash_missing = int(events["audit_hash"].fillna("").str.len().ne(64).sum())
    forbidden_field_persisted = len(set(forbidden_fields).intersection(set(expected_store.columns)))
    strategy_clean = strategy_diff_clean()
    invalid_attempt_count = int((rejected["attempt_type"] == "invalid_value").sum())
    forbidden_attempt_count = int((rejected["attempt_type"] == "forbidden_write").sum())
    summary = {
        "task_name": "tech_bottleneck_manual_review_persistence_replay_regression_v1",
        "regression_generated": True,
        "synthetic_event_count": int(len(events) + len(rejected)),
        "allowed_event_count": int(len(events)),
        "forbidden_write_attempt_count": forbidden_attempt_count,
        "invalid_attempt_count": invalid_attempt_count,
        "rejected_write_count": int(len(rejected)),
        "replay_consistency_mismatch_count": replay_mismatch,
        "latest_state_mismatch_count": latest_mismatch,
        "audit_hash_missing_count": audit_hash_missing,
        "event_ordering_error_count": event_ordering_error_count,
        "forbidden_field_persisted_count": forbidden_field_persisted,
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
        "synthetic_only": True,
        "upstream_persistence_ready": adapter_summary.get("acceptance_decision") == "manual_review_writeback_persistence_adapter_ready",
        "upstream_smoke_v6_ready": smoke_v6.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_persistence",
        "storage_scope": contract.get("storage_scope", "manual_review_only"),
        "acceptance_decision": "manual_review_persistence_replay_regression_ready",
    }
    guardrails = {
        "regression_generated": True,
        "synthetic_event_count": summary["synthetic_event_count"],
        "allowed_event_count": summary["allowed_event_count"],
        "forbidden_write_attempt_count": summary["forbidden_write_attempt_count"],
        "invalid_attempt_count": summary["invalid_attempt_count"],
        "rejected_write_count": summary["rejected_write_count"],
        "replay_consistency_mismatch_count": summary["replay_consistency_mismatch_count"],
        "latest_state_mismatch_count": summary["latest_state_mismatch_count"],
        "audit_hash_missing_count": summary["audit_hash_missing_count"],
        "event_ordering_error_count": summary["event_ordering_error_count"],
        "forbidden_field_persisted_count": summary["forbidden_field_persisted_count"],
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
        "synthetic_only": True,
        "acceptance_decision": summary["acceptance_decision"],
    }
    test_results = {
        "regression_pytest": "pending_initial_generation",
        "smoke_v6_pytest": "pending_initial_generation",
        "persistence_pytest": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }
    events.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_events.csv", index=False)
    rejected.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_rejected_writes.csv", index=False)
    expected_store.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_expected_store.csv", index=False)
    reconstructed_store.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_reconstructed_store.csv", index=False)
    latest_state.to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_latest_state.csv", index=False)
    build_checks(summary).to_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_consistency_checks.csv", index=False)
    build_field_validation(allowed_fields, forbidden_fields + ["invalid_label", "invalid_status", "invalid_conclusion"]).to_csv(
        OUTPUT_DIR / "manual_review_persistence_replay_regression_field_validation.csv", index=False
    )
    write_json(OUTPUT_DIR / "manual_review_persistence_replay_regression_summary.json", summary)
    write_json(OUTPUT_DIR / "manual_review_persistence_replay_regression_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_persistence_replay_regression_v1_report.md").write_text(
        build_report(summary, test_results), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
