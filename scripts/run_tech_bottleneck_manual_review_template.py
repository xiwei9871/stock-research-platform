#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
SCHEMA_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_label_schema_v1"
V2_GENERATOR_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
DASHBOARD_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
TEMPLATE_VERSION = "tech_bottleneck_manual_review_template_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def load_inputs() -> dict[str, pd.DataFrame]:
    return {
        "labels": _read_csv(SCHEMA_DIR / "manual_review_label_dictionary.csv"),
        "form": _read_csv(SCHEMA_DIR / "manual_review_form_schema.csv"),
        "actions": _read_csv(SCHEMA_DIR / "manual_review_action_enum.csv"),
        "schema_audit": _read_csv(SCHEMA_DIR / "manual_review_quality_audit.csv"),
        "candidates": _read_csv(V2_GENERATOR_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"),
        "dashboard": _read_csv(V2_GENERATOR_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"),
        "consolidated_index": _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_index.csv"),
        "dashboard_links": _read_csv(DASHBOARD_DIR / "tech_bottleneck_dashboard_report_links.csv"),
    }


def _default_value(row: pd.Series) -> Any:
    default = row.get("default_value", "")
    if pd.isna(default):
        default = ""
    typ = str(row.get("label_type", ""))
    name = str(row.get("label_name", ""))
    if typ == "boolean":
        return str(default).lower() == "true"
    if typ == "integer":
        return int(default) if str(default).strip() else ""
    if name == "review_status":
        return "not_started"
    if name == "manual_review_conclusion":
        return "not_reviewed"
    if name == "research_status_after_manual":
        return "not_reviewed"
    return default


def build_labels_template(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    candidates = inputs["candidates"].copy()
    schema = inputs["labels"].copy()
    if candidates.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for _, candidate in candidates.iterrows():
        row: dict[str, Any] = {}
        for _, label in schema.iterrows():
            name = str(label["label_name"])
            if name in {"asset_id", "symbol", "name"}:
                row[name] = candidate.get(name, "")
            elif name == "review_id":
                row[name] = f"manual_review_template|{candidate['asset_id']}|round_1"
            elif name == "review_round":
                row[name] = 1
            elif name == "source_report_path":
                row[name] = candidate.get("consolidated_report_path", "")
            else:
                row[name] = _default_value(label)

        row.update(
            {
                "baseline_first_admission_date": candidate.get("baseline_first_admission_date", ""),
                "v2_review_priority": candidate.get("v2_review_priority", ""),
                "v2_review_priority_reason": candidate.get("v2_review_priority_reason", ""),
                "main_review_focus": candidate.get("v2_review_priority_reason", ""),
                "main_risk_summary": candidate.get("main_risk_summary", ""),
                "main_missing_data": candidate.get("main_missing_data", ""),
                "template_version": TEMPLATE_VERSION,
                "template_status": "empty_template_not_reviewed",
                "used_for_signal": False,
                "baseline_admission_changed": False,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("asset_id").reset_index(drop=True)


def build_history_template() -> pd.DataFrame:
    columns = [
        "review_id",
        "asset_id",
        "symbol",
        "name",
        "review_round",
        "review_timestamp",
        "reviewer",
        "changed_fields",
        "old_values",
        "new_values",
        "review_status_before",
        "review_status_after",
        "review_note",
        "writeback_source",
        "used_for_signal",
        "baseline_admission_changed",
    ]
    return pd.DataFrame(columns=columns)


def build_dashboard_template(labels_template: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    allowed = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("true")]["action_name"].astype(str).tolist()
    allowed_actions = "|".join(allowed)
    df = labels_template.copy()
    df["dashboard_badges"] = df["v2_review_priority"].fillna("manual_review_ready")
    df["allowed_actions"] = allowed_actions
    columns = [
        "asset_id",
        "symbol",
        "name",
        "v2_review_priority",
        "review_status",
        "manual_review_conclusion",
        "research_status_after_manual",
        "risk_level_manual",
        "source_coverage_quality",
        "data_gap_follow_up_needed",
        "needs_more_news",
        "needs_full_financial_statement",
        "next_review_date",
        "source_report_path",
        "dashboard_badges",
        "allowed_actions",
        "used_for_signal",
        "baseline_admission_changed",
    ]
    return df[columns]


def build_field_guide(labels: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, label in labels.iterrows():
        name = str(label["label_name"])
        rows.append(
            {
                "field_name": name,
                "field_group": label["label_group"],
                "field_type": label["label_type"],
                "allowed_values": label["allowed_values"],
                "default_value": label["default_value"],
                "required": label["required"],
                "how_to_fill": "Fill after reading source reports; leave default when not reviewed.",
                "example_non_trading_value": _example_value(name, label),
                "common_mistakes": _common_mistake(name),
                "used_for_signal": False,
            }
        )
    extra = {
        "field_name": "needs_technical_follow_up",
        "field_group": "follow_up_review",
        "field_type": "boolean",
        "allowed_values": "true|false",
        "default_value": False,
        "required": False,
        "how_to_fill": "Set true only when more research work is needed on technical context.",
        "example_non_trading_value": "true when a research note needs deeper technology review",
        "common_mistakes": "This is research follow-up, not a trigger or execution workflow.",
        "used_for_signal": False,
    }
    # Replace the generated row with the explicit wording above.
    rows = [r for r in rows if r["field_name"] != "needs_technical_follow_up"]
    rows.append(extra)
    return pd.DataFrame(rows)


def _example_value(name: str, label: pd.Series) -> str:
    if name.endswith("_note") or name in {"final_review_note", "follow_up_note"}:
        return "source requires manual research follow-up"
    values = str(label.get("allowed_values", ""))
    if values and values != "nan":
        return values.split("|")[0]
    if str(label.get("label_type", "")) == "boolean":
        return "false"
    if str(label.get("label_type", "")) == "date":
        return "2026-07-02"
    if str(label.get("label_type", "")) == "integer":
        return "1"
    return "not_reviewed"


def _common_mistake(name: str) -> str:
    if name == "needs_technical_follow_up":
        return "Do not treat this as a trigger; it only means research follow-up."
    if "risk" in name:
        return "Do not treat missing data as absence of risk."
    if "valuation" in name or "pe_" in name:
        return "Do not interpret valuation context as an automatic decision."
    return "Do not overwrite defaults without source review."


def _forbidden_action_leakage(dashboard: pd.DataFrame, actions: pd.DataFrame) -> int:
    forbidden = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("false")]["action_name"].astype(str).tolist()
    if not forbidden or dashboard.empty:
        return 0
    pattern = "|".join(re.escape(item) for item in forbidden)
    return int(dashboard["allowed_actions"].astype(str).str.contains(pattern, case=False, regex=True).sum())


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_quality_audit(labels_template: pd.DataFrame, history: pd.DataFrame, dashboard: pd.DataFrame, guide: pd.DataFrame, schema: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    schema_labels = set(schema["label_name"].astype(str))
    template_labels = set(labels_template.columns)
    missing = sorted(schema_labels - template_labels)
    used_false = (
        int((labels_template["used_for_signal"].astype(str).str.lower() == "false").sum())
        + int((dashboard["used_for_signal"].astype(str).str.lower() == "false").sum())
        + int((guide["used_for_signal"].astype(str).str.lower() == "false").sum())
    )
    default_not_reviewed_count = int((labels_template["manual_review_conclusion"].eq("not_reviewed")).sum()) if "manual_review_conclusion" in labels_template else 0
    rows = [
        ("template candidate rows", len(labels_template), "manual review label rows"),
        ("expected candidate rows", 102, "baseline v2 candidates"),
        ("history template rows", len(history), "empty history template"),
        ("dashboard template rows", len(dashboard), "dashboard template rows"),
        ("field guide rows", len(guide), "field guide rows"),
        ("schema labels covered", len(schema_labels & template_labels), "schema labels present in template"),
        ("missing schema labels", len(missing), "|".join(missing) if missing else "none"),
        ("default not reviewed count", default_not_reviewed_count, "manual conclusion default rows"),
        ("used_for_signal false count", used_false, "research-only rows"),
        ("baseline admission changed count", int(labels_template["baseline_admission_changed"].astype(bool).sum()) if not labels_template.empty else 0, "must remain zero"),
        ("forbidden action leakage count", _forbidden_action_leakage(dashboard, actions), "forbidden actions must not be in allowed_actions"),
        ("trading language hit count", 0, "computed after write"),
        ("lookahead violation rows", 0, "template only"),
        ("formal strategy file status", status, "must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(audit: pd.DataFrame) -> str:
    metric = dict(zip(audit["metric"], audit["value"]))
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    return f"""# Tech Bottleneck Manual Review Template v1

## 1. Executive Summary
Generated manual review templates for {metric.get('template candidate rows', 0)} candidates. Dashboard template rows: {metric.get('dashboard template rows', 0)}. History template rows: {metric.get('history template rows', 0)}. Schema labels covered: {metric.get('schema labels covered', 0)}. No real manual review conclusion was filled; defaults remain `not_reviewed` or blank. Baseline admission changed count: {metric.get('baseline admission changed count', 0)}. Output scan hits: {metric.get('trading language hit count', 0)}. Formal strategy status: {status}.

## 2. Input Files
- Manual review schema from `{SCHEMA_DIR}`.
- v2 generator outputs from `{V2_GENERATOR_DIR}`.
- Consolidated report outputs from `{CONSOLIDATED_DIR}`.
- Dashboard read-only data pack from `{DASHBOARD_DIR}`.

## 3. Manual Review Labels Template
The labels template is one row per baseline asset. It includes schema labels, v2 review priority context, report paths, missing data, risk summary, template status, `used_for_signal = false`, and `baseline_admission_changed = false`.

## 4. Manual Review History Template
The history template is header-only and contains no real review events.

## 5. Dashboard Table Template
The dashboard table is manual-review-ready, contains one row per asset, and exposes only allowed research actions from the schema.

## 6. Field Guide
The field guide explains how to fill every manual review field. `needs_technical_follow_up` is explicitly research follow-up, not trigger workflow.

## 7. Quality Controls
Defaults remain not reviewed or blank. Baseline admission unchanged. Forbidden action leakage count: {metric.get('forbidden action leakage count', 0)}. Formal strategy diff: {diff}.

## 8. What This Template Does Not Do
This template does not create automatic execution cues, does not alter Top5, does not alter baseline admission, does not alter formal strategy files, does not study trigger / intermediate-stage / exit, does not use evidence multiplier, does not use manual labels as automatic execution input, and does not write real manual review conclusions.

## 9. Recommended Next Step
Recommended next task: `tech_bottleneck_watchlist_dashboard_readonly_integration_v1`. Manual review writeback should remain research-only. Continue full financial statement and news source planning.

## 10. Appendix
Generated files:
- `tech_bottleneck_manual_review_labels_template.csv`
- `tech_bottleneck_manual_review_history_template.csv`
- `tech_bottleneck_manual_review_dashboard_table_template.csv`
- `tech_bottleneck_manual_review_template_field_guide.csv`
- `tech_bottleneck_manual_review_template_quality_audit.csv`
- `tech_bottleneck_manual_review_template_v1.md`

Formal strategy file status: {status}.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    labels_template = build_labels_template(inputs)
    history = build_history_template()
    dashboard = build_dashboard_template(labels_template, inputs["actions"])
    guide = build_field_guide(inputs["labels"])
    audit = build_quality_audit(labels_template, history, dashboard, guide, inputs["labels"], inputs["actions"])

    labels_template.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_labels_template.csv", index=False)
    history.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_history_template.csv", index=False)
    dashboard.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_dashboard_table_template.csv", index=False)
    guide.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_field_guide.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv", index=False)
    (OUTPUT_DIR / "tech_bottleneck_manual_review_template_v1.md").write_text(render_report(audit), encoding="utf-8")

    hits = _count_output_hits(OUTPUT_DIR)
    if hits:
        audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hits
        audit.to_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv", index=False)
        raise RuntimeError(f"forbidden output hits: {hits}")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
