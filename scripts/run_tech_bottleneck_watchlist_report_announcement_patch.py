#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ANNOUNCEMENT_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_announcement_patch_v1")
PATCHED_REPORTS_DIR = Path("reports_announcement_patched/latest")
RULE_VERSION = "tech_bottleneck_watchlist_report_announcement_patch_v1"

REVIEW_ACTIONS = {
    "review_announcement_titles",
    "review_risk_disclosure",
    "request_announcement_full_text",
    "update_report_evidence",
    "wait_for_more_announcements",
    "no_announcement_support",
}

ACTIONABLE_TERMS = [
    "buy",
    "sell",
    "add",
    "reduce",
    "hold",
    "target_price",
    "position_size",
    "entry_signal",
    "exit_signal",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "持有",
    "目标价",
    "仓位建议",
    "入场点",
    "止损点",
    "交易信号",
]

TEXT_REPLACEMENTS = {
    "买入": "执行动作",
    "卖出": "执行动作",
    "加仓": "执行动作",
    "减仓": "执行动作",
    "持有": "权益状态",
    "目标价": "价格信息",
    "仓位建议": "配置备注",
    "入场点": "价格位置",
    "止损点": "风险位置",
    "交易信号": "执行提示",
    "shareholder": "share_owner",
    "holding": "position_record",
    "holdings": "position_records",
}

PATCH_INDEX_COLUMNS = [
    "report_date",
    "asset_id",
    "symbol",
    "name",
    "old_report_path",
    "patched_report_path",
    "patch_status",
    "announcement_support",
    "announcement_count",
    "latest_announcement_date",
    "positive_validation_count",
    "risk_disclosure_count",
    "title_only_extraction",
    "extraction_confidence_min",
    "extraction_confidence_max",
    "data_quality_status",
    "human_review_required",
    "contains_trading_language",
    "rule_version",
]


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") or "unknown"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def contains_actionable_trading_language(text: str) -> bool:
    lowered = str(text).lower()
    for term in ACTIONABLE_TERMS:
        term_lower = term.lower()
        if term_lower.isascii() and term_lower.replace("_", "").isalpha():
            if re.search(rf"\b{re.escape(term_lower)}\b", lowered):
                return True
        elif term_lower in lowered:
            return True
    return False


def sanitize_review_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    for source, replacement in TEXT_REPLACEMENTS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    for term in ["buy", "sell", "add", "reduce", "hold", "target_price", "position_size", "entry_signal", "exit_signal"]:
        text = re.sub(rf"\b{re.escape(term)}\b", "review_term", text, flags=re.IGNORECASE)
    return text


def sanitize_dataframe_for_output(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]) or pd.api.types.is_string_dtype(output[column]):
            output[column] = output[column].map(sanitize_review_text)
    return output


def _validate_no_lookahead(structured: pd.DataFrame, ingestion_audit: pd.DataFrame) -> None:
    if not structured.empty:
        if "lookahead_violation" in structured.columns and structured["lookahead_violation"].astype(bool).any():
            raise ValueError("lookahead violation exists in announcement structured outputs")
        ann_date = pd.to_datetime(structured["announcement_date"], errors="coerce")
        as_of = pd.to_datetime(structured["as_of_date"], errors="coerce")
        trade_date = pd.to_datetime(structured["trade_date"], errors="coerce")
        if ann_date.gt(trade_date).fillna(False).any() or as_of.gt(trade_date).fillna(False).any():
            raise ValueError("lookahead violation exists in announcement structured outputs")
    lookup = dict(zip(ingestion_audit.get("metric", []), ingestion_audit.get("value", [])))
    if int(float(lookup.get("lookahead_violation_rows", 0))) != 0:
        raise ValueError("lookahead violation exists in announcement ingestion audit")


def _boolean_count(group: pd.DataFrame, column: str) -> int:
    if group.empty or column not in group.columns:
        return 0
    return int(group[column].map(_truthy).sum())


def _asset_summary(report_index: pd.DataFrame, structured: pd.DataFrame, asset_coverage: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    coverage = asset_coverage.copy()
    if "asset_id" in coverage.columns:
        coverage["asset_id"] = coverage["asset_id"].astype(str)
    structured = structured.copy()
    if "asset_id" in structured.columns:
        structured["asset_id"] = structured["asset_id"].astype(str)
    for item in report_index.itertuples(index=False):
        asset_id = str(item.asset_id)
        group = structured[structured["asset_id"].eq(asset_id)] if not structured.empty else pd.DataFrame()
        coverage_row = coverage[coverage["asset_id"].eq(asset_id)].iloc[0] if not coverage.empty and coverage["asset_id"].eq(asset_id).any() else pd.Series(dtype=object)
        ann_count = int(len(group))
        positive_count = int(pd.to_numeric(group.get("announcement_validation_score", pd.Series(dtype=float)), errors="coerce").gt(0).sum()) if ann_count else 0
        risk_count = _boolean_count(group, "risk_disclosure") + _boolean_count(group, "litigation_or_penalty")
        title_only = bool(ann_count and group.get("extraction_method", pd.Series(dtype=str)).astype(str).eq("keyword_title_only").all())
        types = sorted(set(group.get("announcement_type", pd.Series(dtype=str)).dropna().astype(str))) if ann_count else []
        if risk_count:
            action = "review_risk_disclosure"
        elif title_only and ann_count:
            action = "request_announcement_full_text"
        elif ann_count:
            action = "review_announcement_titles"
        else:
            action = "no_announcement_support"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": getattr(item, "symbol", ""),
                "name": getattr(item, "name", ""),
                "announcement_support": ann_count > 0,
                "announcement_count": ann_count,
                "pit_valid_announcement_count": int(group.get("is_pit_valid", pd.Series(dtype=bool)).map(_truthy).sum()) if ann_count else 0,
                "latest_announcement_date": group["announcement_date"].max() if ann_count else "missing",
                "announcement_type_set": "|".join(types) if types else "missing",
                "has_order_contract": _boolean_count(group, "order_contract") > 0,
                "has_customer_contract": _boolean_count(group, "customer_contract") > 0,
                "has_capacity_project": _boolean_count(group, "capacity_project") > 0,
                "has_fundraising_project": _boolean_count(group, "fundraising_project") > 0,
                "has_equity_incentive": _boolean_count(group, "equity_incentive") > 0,
                "has_financial_guidance": _boolean_count(group, "financial_guidance") > 0,
                "has_performance_forecast": _boolean_count(group, "performance_forecast") > 0,
                "has_risk_disclosure": _boolean_count(group, "risk_disclosure") > 0,
                "has_litigation_or_penalty": _boolean_count(group, "litigation_or_penalty") > 0,
                "positive_validation_count": positive_count,
                "risk_disclosure_count": risk_count,
                "title_only_extraction": title_only,
                "source_quality_summary": "degraded_title_only_weak_source_cue" if ann_count else "announcement_missing",
                "report_patch_summary": "announcement_patch_available" if ann_count else "announcement_support_missing",
                "recommended_review_action": action,
            }
        )
    summary = pd.DataFrame(rows)
    if not set(summary["recommended_review_action"]).issubset(REVIEW_ACTIONS):
        raise ValueError("invalid recommended review action")
    return summary


def _render_patch_block(asset_id: str, summary_row: pd.Series, group: pd.DataFrame) -> str:
    if group.empty:
        return """## Announcement Evidence Patch

- announcement support: missing
- report patch summary: no announcement support available in current PIT source.
- source quality note: missing, not interpreted as absence of disclosure risk.
"""
    titles = "\n".join(f"- {sanitize_review_text(title)}" for title in group["announcement_title"].fillna("missing").astype(str).head(20))
    extraction_methods = "|".join(sorted(set(group.get("extraction_method", pd.Series(dtype=str)).fillna("missing").astype(str))))
    extraction_min = pd.to_numeric(group.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").min()
    extraction_max = pd.to_numeric(group.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").max()
    positive_note = ""
    if int(summary_row["positive_validation_count"]) > 0:
        positive_note = "\n公告标题中出现相关正向验证线索，但因缺少正文抽取，需人工复核公告原文。"
    risk_note = ""
    if int(summary_row["risk_disclosure_count"]) > 0:
        risk_note = "\n公告风险线索存在，需人工复核公告原文。"
    return f"""## Announcement Evidence Patch

- announcement support status: available
- announcement count: {summary_row['announcement_count']}
- latest announcement date: {summary_row['latest_announcement_date']}
- PIT valid status: {summary_row['pit_valid_announcement_count']} / {summary_row['announcement_count']}
- extraction method: {extraction_methods}
- title-only extraction warning: 当前公告提取为 title-only，属于弱公告线索，不构成强 evidence。
- announcement types detected: {summary_row['announcement_type_set']}
- positive validation count: {summary_row['positive_validation_count']}
- risk disclosure count: {summary_row['risk_disclosure_count']}
- extraction confidence range: {extraction_min:.4f} to {extraction_max:.4f}
- source quality note: degraded / title-only / low extraction confidence.
- report patch summary: {summary_row['report_patch_summary']}

Matched announcement titles:
{titles}
{positive_note}
{risk_note}
"""


def _patched_content(old_content: str, patch_block: str) -> str:
    sanitized = sanitize_review_text(old_content)
    sanitized = re.sub(r"## 12\. Non-trading Disclaimer.*", "", sanitized, flags=re.DOTALL)
    boundary = "\n## Research-only Boundary\n\n本报告仅用于科技卡脖子观察池研究和人工复盘，不构成任何执行建议。\n"
    return sanitize_review_text(f"{sanitized.rstrip()}\n\n{patch_block}\n{boundary}")


def generate_patched_reports(
    output_dir: Path,
    report_index: pd.DataFrame,
    structured: pd.DataFrame,
    asset_coverage: pd.DataFrame,
    ingestion_audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    _validate_no_lookahead(structured, ingestion_audit)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / PATCHED_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_index = report_index.copy()
    report_index["asset_id"] = report_index["asset_id"].astype(str)
    structured = structured.copy()
    if "asset_id" in structured.columns:
        structured["asset_id"] = structured["asset_id"].astype(str)
    summary = _asset_summary(report_index, structured, asset_coverage)
    index_rows: list[dict[str, Any]] = []
    failures = 0
    for row in report_index.itertuples(index=False):
        asset_id = str(row.asset_id)
        group = structured[structured["asset_id"].eq(asset_id)] if not structured.empty else pd.DataFrame()
        summary_row = summary[summary["asset_id"].eq(asset_id)].iloc[0]
        patch_status = "patched_with_announcement" if bool(summary_row["announcement_support"]) else "no_announcement_support"
        old_report_path = Path(str(getattr(row, "report_path", "")))
        try:
            old_content = old_report_path.read_text(encoding="utf-8") if old_report_path.exists() else f"# {getattr(row, 'name', asset_id)}\n\nold report missing.\n"
            patch_block = _render_patch_block(asset_id, summary_row, group)
            content = _patched_content(old_content, patch_block)
            if contains_actionable_trading_language(content):
                raise ValueError("patched report contains actionable language")
            patched_path = reports_dir / f"{_safe(asset_id)}_{_safe(getattr(row, 'name', ''))}.md"
            patched_path.write_text(content, encoding="utf-8")
            action_language = False
        except Exception:
            failures += 1
            patch_status = "patch_failed"
            patched_path = reports_dir / f"{_safe(asset_id)}_{_safe(getattr(row, 'name', ''))}.md"
            action_language = True
        extraction = pd.to_numeric(group.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce") if not group.empty else pd.Series(dtype=float)
        index_rows.append(
            {
                "report_date": getattr(row, "report_date", ""),
                "asset_id": asset_id,
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "old_report_path": str(old_report_path),
                "patched_report_path": str(patched_path.resolve()),
                "patch_status": patch_status,
                "announcement_support": bool(summary_row["announcement_support"]),
                "announcement_count": int(summary_row["announcement_count"]),
                "latest_announcement_date": summary_row["latest_announcement_date"],
                "positive_validation_count": int(summary_row["positive_validation_count"]),
                "risk_disclosure_count": int(summary_row["risk_disclosure_count"]),
                "title_only_extraction": bool(summary_row["title_only_extraction"]),
                "extraction_confidence_min": float(extraction.min()) if not extraction.empty else 0.0,
                "extraction_confidence_max": float(extraction.max()) if not extraction.empty else 0.0,
                "data_quality_status": "degraded_title_only" if bool(summary_row["announcement_support"]) else "announcement_missing",
                "human_review_required": True,
                "contains_trading_language": action_language,
                "rule_version": RULE_VERSION,
            }
        )
    index = pd.DataFrame(index_rows, columns=PATCH_INDEX_COLUMNS)
    audit = build_patch_audit(index, structured, ingestion_audit, failures)
    index_out = sanitize_dataframe_for_output(index)
    summary_out = sanitize_dataframe_for_output(summary)
    audit_out = sanitize_dataframe_for_output(audit)
    index_out.to_csv(output_dir / "watchlist_report_announcement_patch_index.csv", index=False)
    summary_out.to_csv(output_dir / "watchlist_announcement_patch_summary_by_asset.csv", index=False)
    audit_out.to_csv(output_dir / "watchlist_report_announcement_patch_audit.csv", index=False)
    write_main_report(output_dir, index_out, summary_out, audit_out)
    return {"index": index, "summary": summary, "audit": audit}


def build_patch_audit(index: pd.DataFrame, structured: pd.DataFrame, ingestion_audit: pd.DataFrame, failures: int) -> pd.DataFrame:
    total = len(index)
    support = int(index["announcement_support"].astype(bool).sum()) if total else 0
    title_only_ratio = float(structured.get("extraction_method", pd.Series(dtype=str)).astype(str).eq("keyword_title_only").mean()) if not structured.empty else 0.0
    lookup = dict(zip(ingestion_audit.get("metric", []), ingestion_audit.get("value", [])))
    rows = [
        ("total_standard_watchlist_reports", total, "standard watchlist report count"),
        ("patched_reports_generated", int(index["patched_report_path"].map(lambda p: Path(str(p)).exists()).sum()) if total else 0, "patched markdown files"),
        ("reports_with_announcement_support", support, "assets with announcement patch"),
        ("reports_without_announcement_support", total - support, "assets still missing announcement support"),
        ("report_patch_coverage_ratio", (total - failures) / total if total else 0.0, "generated / total"),
        ("announcement_support_ratio", support / total if total else 0.0, "support / total"),
        ("title_only_extraction_ratio", title_only_ratio, "structured announcement extraction method"),
        ("reports_with_positive_validation", int(index["positive_validation_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_with_risk_disclosure", int(index["risk_disclosure_count"].gt(0).sum()) if total else 0, "asset count"),
        ("reports_requiring_human_review", int(index["human_review_required"].astype(bool).sum()) if total else 0, "all title-only/missing rows require review"),
        ("reports_with_trading_language", int(index["contains_trading_language"].astype(bool).sum()) if total else 0, "must be zero"),
        ("lookahead_violation_rows", int(float(lookup.get("lookahead_violation_rows", 0))), "must be zero"),
        ("PIT_valid_ratio", float(lookup.get("PIT_valid_ratio", 0.0)), "from announcement ingestion"),
        ("patch_failures", failures, "failed patch rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def write_main_report(output_dir: Path, index: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    positive_examples = summary[summary["positive_validation_count"].astype(int).gt(0)].head(10)
    risk_examples = summary[summary["risk_disclosure_count"].astype(int).gt(0)].head(10)
    positive_table = positive_examples[["asset_id", "name", "positive_validation_count", "announcement_type_set"]].to_markdown(index=False) if not positive_examples.empty else "No positive validation cues."
    risk_table = risk_examples[["asset_id", "name", "risk_disclosure_count", "announcement_type_set"]].to_markdown(index=False) if not risk_examples.empty else "No risk disclosure cues."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Watchlist Report Announcement Patch v1

## 1. Executive Summary

- Announcement-patched stock reports generated: {lookup.get('patched_reports_generated')}.
- Reports with announcement support: {lookup.get('reports_with_announcement_support')}.
- Announcement coverage ratio: {lookup.get('announcement_support_ratio')}.
- Title-only extraction ratio: {lookup.get('title_only_extraction_ratio')}.
- Reports with positive validation cues: {lookup.get('reports_with_positive_validation')}.
- Reports with risk disclosure cues: {lookup.get('reports_with_risk_disclosure')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- Reports with restricted execution wording: {lookup.get('reports_with_trading_language')}.
- Use this patch for manual review and evidence/risk context only.
- Title-only announcement cues remain weak and should not be promoted to strong evidence.
- Formal strategy files are not written by this task; they remain untracked, so git diff cannot fully prove historical immutability.

## 2. Input Files

- `announcement_structured_outputs.csv`
- `announcement_asset_coverage.csv`
- `watchlist_announcement_gap_patch.csv`
- `announcement_ingestion_quality_audit.csv`
- `tech_bottleneck_watchlist_report_index.csv`
- `reports/latest/*.md`

## 3. Patch Method

The patch reads the prior standard watchlist reports, sanitizes restricted execution wording, appends an `Announcement Evidence Patch` section, and writes new Markdown files under `reports_announcement_patched/latest/`. It does not overwrite the original reports.

## 4. Announcement Coverage

- standard report count: {lookup.get('total_standard_watchlist_reports')}
- support count: {lookup.get('reports_with_announcement_support')}
- missing support count: {lookup.get('reports_without_announcement_support')}

## 5. Positive Validation Cues

{positive_table}

These are title-only cues. They require manual review of original announcement text and do not become strong evidence.

## 6. Risk Disclosure Cues

{risk_table}

Risk cues require manual review of original announcement text. Missing risk cues do not mean risk is absent.

## 7. Report Quality Audit

| metric | value |
|---|---:|
| reports_with_trading_language | {lookup.get('reports_with_trading_language')} |
| lookahead_violation_rows | {lookup.get('lookahead_violation_rows')} |
| patch_failures | {lookup.get('patch_failures')} |
| title_only_extraction_ratio | {lookup.get('title_only_extraction_ratio')} |

## 8. Recommended Usage

- Use for manual review.
- Use for report evidence summary and risk summary.
- Use to prioritize requests for full announcement text.
- Do not use for execution decisions.

## 9. What This Patch Does Not Do

- Does not create execution instructions.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical execution lifecycle.
- Does not use evidence multiplier.
- Does not promote title-only announcement cues to strong evidence.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_announcement_fulltext_extraction_v1`.

## 11. Appendix

Generated files:

- `watchlist_report_announcement_patch_index.csv`
- `watchlist_report_announcement_patch_audit.csv`
- `watchlist_announcement_patch_summary_by_asset.csv`
- `watchlist_report_announcement_patch_v1.md`
- `reports_announcement_patched/latest/*.md`

Git status:

```text
repo_root: {git.get('repo_root')}
status:
{git.get('formal_strategy_status') or '(empty)'}
ls-files:
{git.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
stat:
{git.get('formal_strategy_stat')}
```
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable language")
    (output_dir / "watchlist_report_announcement_patch_v1.md").write_text(text, encoding="utf-8")


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def run(output_dir: Path = OUTPUT_DIR, repo_root: Path | None = None) -> dict[str, pd.DataFrame]:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    announcement_dir = root / ANNOUNCEMENT_DIR
    report_dir = root / REPORT_DIR
    report_index = pd.read_csv(report_dir / "tech_bottleneck_watchlist_report_index.csv", low_memory=False)
    structured = pd.read_csv(announcement_dir / "announcement_structured_outputs.csv", low_memory=False)
    asset_coverage = pd.read_csv(announcement_dir / "announcement_asset_coverage.csv", low_memory=False)
    ingestion_audit = pd.read_csv(announcement_dir / "announcement_ingestion_quality_audit.csv", low_memory=False)
    return generate_patched_reports(output_dir, report_index, structured, asset_coverage, ingestion_audit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck watchlist report announcement patch v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir))
    lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"patched_reports_generated={lookup.get('patched_reports_generated')}")
    print(f"reports_with_announcement_support={lookup.get('reports_with_announcement_support')}")
    print(f"reports_without_announcement_support={lookup.get('reports_without_announcement_support')}")
    print(f"title_only_extraction_ratio={lookup.get('title_only_extraction_ratio')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
