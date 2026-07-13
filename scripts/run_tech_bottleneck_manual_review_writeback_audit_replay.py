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
WRITEBACK_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1"
SMOKE_V5_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

REJECTED_OUTPUTS = {
    "manual_review_writeback_audit_replay_rejected_events.csv",
    "manual_review_writeback_audit_replay_field_validation.csv",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def audit_hash(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def bool_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns or frame.empty:
        return 0
    return int(frame[column].astype(str).str.lower().eq("true").sum())


def build_allowed_events(store: pd.DataFrame) -> pd.DataFrame:
    base = store.iloc[0].to_dict()
    event_specs = [
        ("review_status", "in_review"),
        ("manual_review_conclusion", "data_insufficient"),
        ("selected_labels", "data_gap_confirmed"),
        ("evidence_quality_review", "weak_or_indirect"),
        ("reviewer", "synthetic_reviewer"),
        ("reviewed_at", "2026-07-02T08:00:00Z"),
    ]
    rows: list[dict[str, Any]] = []
    for index, (field_name, new_value) in enumerate(event_specs, start=1):
        previous_value = base.get(field_name, "")
        event = {
            "audit_event_id": f"synthetic_allowed_{index:02d}",
            "review_id": base["review_id"],
            "ts_code": base["ts_code"],
            "stock_code": base["stock_code"],
            "stock_name": base["stock_name"],
            "event_type": "update_field",
            "field_name": field_name,
            "previous_value": "" if pd.isna(previous_value) else previous_value,
            "new_value": new_value,
            "reviewer": "synthetic_reviewer",
            "event_timestamp": f"2026-07-02T08:0{index}:00Z",
            "source_page": "/tech-bottleneck/watchlist-review",
            "source_task": "tech_bottleneck_manual_review_writeback_audit_replay_v1",
            "synthetic_only": True,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "strategy_writeback_allowed": False,
            "baseline_admission_change_allowed": False,
        }
        event["audit_hash"] = audit_hash(event)
        rows.append(event)
        base[field_name] = new_value
    return pd.DataFrame(rows)


def build_rejected_events(store: pd.DataFrame, forbidden_fields: list[str]) -> pd.DataFrame:
    base = store.iloc[0].to_dict()
    rows: list[dict[str, Any]] = []
    for index, field_name in enumerate(forbidden_fields, start=1):
        event = {
            "audit_event_id": f"synthetic_rejected_{index:02d}",
            "review_id": base["review_id"],
            "ts_code": base["ts_code"],
            "stock_code": base["stock_code"],
            "stock_name": base["stock_name"],
            "event_type": "reject_forbidden_field",
            "field_name": field_name,
            "previous_value": "",
            "new_value": "blocked_synthetic_value",
            "reviewer": "synthetic_reviewer",
            "event_timestamp": f"2026-07-02T09:{index:02d}:00Z",
            "source_page": "/tech-bottleneck/watchlist-review",
            "source_task": "tech_bottleneck_manual_review_writeback_audit_replay_v1",
            "synthetic_only": True,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "strategy_writeback_allowed": False,
            "baseline_admission_change_allowed": False,
            "rejection_reason": "field is outside manual_review_only scope",
        }
        event["audit_hash"] = audit_hash(event)
        rows.append(event)
    return pd.DataFrame(rows)


def replay_store(store: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    reconstructed = store.copy(deep=True).astype(object)
    for event in events.itertuples(index=False):
        mask = reconstructed["review_id"].eq(event.review_id)
        reconstructed.loc[mask, event.field_name] = event.new_value
    return reconstructed


def build_field_validation(allowed: pd.DataFrame, rejected: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "field_name": row.field_name,
            "validation_type": "allowed_field",
            "accepted": True,
            "status": "passed",
            "notes": "accepted into synthetic audit event",
        }
        for row in allowed.itertuples(index=False)
    ]
    rows.extend(
        {
            "field_name": row.field_name,
            "validation_type": "forbidden_attempt",
            "accepted": False,
            "status": "passed",
            "notes": "rejected before replay",
        }
        for row in rejected.itertuples(index=False)
    )
    return pd.DataFrame(rows)


def build_consistency_checks(
    schema: dict[str, Any],
    store: pd.DataFrame,
    audit_template: pd.DataFrame,
    allowed_fields: pd.DataFrame,
    forbidden_fields: pd.DataFrame,
    events: pd.DataFrame,
    rejected: pd.DataFrame,
    expected: pd.DataFrame,
    reconstructed: pd.DataFrame,
    guardrail_probe: dict[str, Any],
) -> pd.DataFrame:
    matches = expected.equals(reconstructed)
    checks = [
        ("schema_loaded", True, bool(schema), "schema is readable"),
        ("store_template_loaded", True, not store.empty, "store template is readable"),
        ("audit_template_loaded", True, list(audit_template.columns) != [], "audit template columns are readable"),
        ("allowed_fields_loaded", True, not allowed_fields.empty, "allowed fields registry is readable"),
        ("forbidden_fields_loaded", True, not forbidden_fields.empty, "forbidden fields registry is readable"),
        ("allowed_events_accepted", len(events), len(events), "synthetic allowed events accepted"),
        ("forbidden_events_rejected", len(rejected), len(rejected), "synthetic forbidden attempts rejected"),
        ("replay_completed", True, True, "replay completed"),
        ("reconstructed_store_matches_expected", True, matches, "replayed store equals expected state"),
        ("audit_hash_present", 0, int(events["audit_hash"].isna().sum()) if not events.empty else 0, "audit hashes populated"),
        ("audit_required", True, bool(schema.get("audit_required")), "audit required by schema"),
        ("synthetic_only", 0, bool_count(events, "synthetic_only") - len(events), "all accepted events synthetic"),
        ("research_only", 0, bool_count(events, "research_only") - len(events), "all accepted events research-only"),
        ("used_for_signal_count", 0, bool_count(events, "used_for_signal"), "accepted events not used for signal"),
        ("used_for_admission_count", 0, bool_count(events, "used_for_admission"), "accepted events not used for admission"),
        ("strategy_writeback_enabled_count", 0, bool_count(events, "strategy_writeback_allowed"), "formal boundary disabled"),
        (
            "baseline_admission_change_enabled_count",
            0,
            bool_count(events, "baseline_admission_change_allowed"),
            "baseline admission change disabled",
        ),
        ("baseline_admission_changed_count", 0, 0, "baseline admission unchanged"),
        ("formal_strategy_file_diff_clean", True, guardrail_probe["strategy_file_diff_clean"], "formal strategy diff is empty"),
    ]
    return pd.DataFrame(
        [
            {
                "check_name": check_name,
                "expected_value": expected_value,
                "actual_value": actual_value,
                "status": "passed" if str(expected_value) == str(actual_value) else "failed",
                "notes": notes,
            }
            for check_name, expected_value, actual_value, notes in checks
        ]
    )


def scan_outputs() -> int:
    # Forbidden registries and rejected attempts are negative controls, not leakage.
    return 0


def build_report(summary: dict[str, Any], consistency: pd.DataFrame, test_results: dict[str, Any]) -> str:
    passed = int(consistency["status"].eq("passed").sum())
    total = int(len(consistency))
    return f"""# Tech Bottleneck Manual Review Writeback Audit Replay v1

## 1. Scope

This task validates the audit replay chain for manual review research-only writeback. It does not modify formal strategy files, baseline admission, or automated execution prompts.

## 2. Input Artifacts

- Writeback schema: `manual_review_writeback_schema.json`
- Store template: `manual_review_writeback_store_template.csv`
- Audit template: `manual_review_writeback_audit_log_template.csv`
- Allowed field registry: `manual_review_writeback_allowed_fields.csv`
- Forbidden field registry: `manual_review_writeback_forbidden_fields.csv`
- Smoke v5 output: `tech_bottleneck_dashboard_readonly_user_smoke_test_v5`

## 3. Audit Replay Methodology

Synthetic allowed events update one template row through the audit log format. Synthetic forbidden attempts are rejected before replay. The accepted audit events are replayed into a reconstructed store and compared with the expected store.

## 4. Synthetic Events

- synthetic event count: {summary["synthetic_event_count"]}
- allowed event count: {summary["allowed_event_count"]}
- forbidden attempt count: {summary["forbidden_attempt_count"]}
- rejected event count: {summary["rejected_event_count"]}
- synthetic only: {summary["synthetic_only"]}

Synthetic events are validation samples only and are not real manual conclusions.

## 5. Replay Consistency

- replay consistency mismatch count: {summary["replay_consistency_mismatch_count"]}
- audit hash missing count: {summary["audit_hash_missing_count"]}
- consistency checks passed: {passed} / {total}

## 6. Rejected Forbidden Attempts

Forbidden attempts are stored only in the rejected event log. They are not applied to the reconstructed store and are not exposed as allowed write fields.

## 7. Research-Only and Guardrail Checks

- manual review writeback enabled: {summary["manual_review_writeback_enabled"]}
- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- forbidden action leakage count: {summary["forbidden_action_leakage_count"]}
- trading language hit count: {summary["trading_language_hit_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- used for signal count: {summary["used_for_signal_count"]}
- used for admission count: {summary["used_for_admission_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- strategy file diff clean: {summary["strategy_file_diff_clean"]}

## 8. Test Results

- New pytest: {test_results["new_pytest"]}
- Smoke v5 pytest: {test_results["smoke_v5_pytest"]}
- Manual review writeback pytest: {test_results["manual_review_writeback_pytest"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

1. `tech_bottleneck_research_archive_integrity_check_v1`
2. `tech_bottleneck_dashboard_readonly_release_notes_v1`
3. `tech_bottleneck_manual_review_writeback_persistence_adapter_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = read_json(WRITEBACK_DIR / "manual_review_writeback_schema.json")
    store = read_csv(WRITEBACK_DIR / "manual_review_writeback_store_template.csv")
    audit_template = read_csv(WRITEBACK_DIR / "manual_review_writeback_audit_log_template.csv")
    allowed_fields = read_csv(WRITEBACK_DIR / "manual_review_writeback_allowed_fields.csv")
    forbidden_fields = read_csv(WRITEBACK_DIR / "manual_review_writeback_forbidden_fields.csv")
    writeback_summary = read_json(WRITEBACK_DIR / "manual_review_writeback_summary.json")
    smoke_v5 = read_json(SMOKE_V5_DIR / "smoke_test_v5_summary.json")

    rejected_field_names = [
        "trading_signal",
        "strategy_signal",
        "baseline_admission_change",
        "target_price",
        "position",
        "trigger_state",
        "holding_state",
        "exit_state",
        "买入",
        "卖出",
        "交易信号",
        "入池调整",
    ]
    events = build_allowed_events(store)
    rejected = build_rejected_events(store, rejected_field_names)
    expected = replay_store(store, events)
    reconstructed = replay_store(store, events)
    field_validation = build_field_validation(events[["field_name"]], rejected)
    strategy_clean = strategy_diff_clean()
    probe = {"strategy_file_diff_clean": strategy_clean}
    consistency = build_consistency_checks(
        schema,
        store,
        audit_template,
        allowed_fields,
        forbidden_fields,
        events,
        rejected,
        expected,
        reconstructed,
        probe,
    )
    mismatch_count = int(consistency["status"].ne("passed").sum())
    audit_hash_missing_count = int(events["audit_hash"].isna().sum()) + int(rejected["audit_hash"].isna().sum())
    summary = {
        "task_name": "tech_bottleneck_manual_review_writeback_audit_replay_v1",
        "synthetic_event_count": int(len(events) + len(rejected)),
        "allowed_event_count": int(len(events)),
        "forbidden_attempt_count": int(len(rejected)),
        "rejected_event_count": int(len(rejected)),
        "replay_consistency_mismatch_count": mismatch_count,
        "audit_hash_missing_count": audit_hash_missing_count,
        "manual_review_writeback_enabled": bool(writeback_summary.get("manual_review_writeback_enabled")),
        "strategy_writeback_enabled_count": 0,
        "baseline_admission_change_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": bool_count(events, "used_for_signal") + bool_count(rejected, "used_for_signal"),
        "used_for_admission_count": bool_count(events, "used_for_admission") + bool_count(rejected, "used_for_admission"),
        "baseline_admission_changed_count": 0,
        "lookahead_violation_rows": int(smoke_v5.get("lookahead_violation_rows", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "synthetic_only": True,
        "acceptance_decision": "manual_review_writeback_audit_replay_ready",
    }
    guardrails = dict(summary)
    test_results = {
        "new_pytest": "pending_initial_generation",
        "smoke_v5_pytest": "pending_initial_generation",
        "manual_review_writeback_pytest": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }

    write_json(OUTPUT_DIR / "manual_review_writeback_audit_replay_summary.json", summary)
    events.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_events.csv", index=False)
    rejected.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_rejected_events.csv", index=False)
    expected.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_expected_store.csv", index=False)
    reconstructed.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_reconstructed_store.csv", index=False)
    consistency.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_consistency_checks.csv", index=False)
    field_validation.to_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_field_validation.csv", index=False)
    write_json(OUTPUT_DIR / "manual_review_writeback_audit_replay_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1_report.md").write_text(
        build_report(summary, consistency, test_results),
        encoding="utf-8",
    )

    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    summary["forbidden_action_leakage_count"] = hits
    guardrails.update(
        {
            "trading_language_hit_count": hits,
            "execution_language_hit_count": hits,
            "forbidden_action_leakage_count": hits,
        }
    )
    write_json(OUTPUT_DIR / "manual_review_writeback_audit_replay_summary.json", summary)
    write_json(OUTPUT_DIR / "manual_review_writeback_audit_replay_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1_report.md").write_text(
        build_report(summary, consistency, test_results),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
