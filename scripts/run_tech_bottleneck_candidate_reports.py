#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "tech_bottleneck_candidate_reports_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_reports_v1"
CANONICAL_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
CLOSURE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v2"
LEGACY_POOL = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
REPORT_SECTIONS = [
    "Executive summary",
    "Company business overview",
    "Main products and revenue structure",
    "Hard-tech bottleneck thesis",
    "Industry chain position",
    "Technology capability",
    "R&D and patents / technical platform",
    "Domestic substitution / supply chain security logic",
    "Industry and competition",
    "Financial quality snapshot",
    "Evidence matrix",
    "Risks and disqualifiers",
    "Research-only conclusion",
    "Next action",
]
FORBIDDEN_TRADING_PHRASES = ["买入", "卖出", "目标价", "入场", "退出", "buy recommendation", "sell recommendation"]


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


def _normalize_stock_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _safe_name(value: Any) -> str:
    return str(value).replace("/", "_").replace("\\", "_").strip()


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    text = str(value)
    return default if text == "nan" else text


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _load_pool() -> pd.DataFrame:
    pool = pd.read_csv(CANONICAL_POOL, dtype={"stock_code": str})
    pool["stock_code"] = pool["stock_code"].map(_normalize_stock_code)
    if len(pool) != 90:
        raise ValueError(f"Expected canonical report scope to contain 90 candidates, found {len(pool)}")
    return pool


def _select_candidates(pool: pd.DataFrame, stock_codes: str | None, limit: int | None) -> pd.DataFrame:
    selected = pool.copy()
    if stock_codes:
        requested = [_normalize_stock_code(code) for code in stock_codes.split(",") if code.strip()]
        selected = selected[selected["stock_code"].isin(requested)].copy()
        selected["_request_order"] = selected["stock_code"].map({code: index for index, code in enumerate(requested)})
        selected = selected.sort_values(["_request_order", "stock_code"]).drop(columns=["_request_order"])
    if limit is not None:
        selected = selected.head(limit).copy()
    return selected.reset_index(drop=True)


def _classification(row: pd.Series) -> dict[str, Any]:
    category = _clean(row.get("review_pool_category") or row.get("final_manual_approval_category"))
    evidence_strength = _clean(row.get("evidence_strength"), "missing")
    relevance_raw = _clean(row.get("bottleneck_relevance"), "unclear")
    has_primary = bool(_bool_value(row.get("primary_source_evidence_available"))) or bool(_clean(row.get("primary_source_url")))
    if category == "verified_core":
        return {
            "review_decision": "keep_core",
            "bottleneck_relevance": "core",
            "evidence_strength": evidence_strength if evidence_strength in {"strong", "moderate"} else "moderate",
            "report_status": "complete" if has_primary or evidence_strength in {"strong", "moderate", "sufficient"} else "partial_primary_source_missing",
            "bottleneck_confidence_score": 78 if evidence_strength != "strong" else 86,
            "evidence_quality_score": 70 if evidence_strength != "strong" else 82,
        }
    if category == "manual_anchor_core_pending_evidence":
        return {
            "review_decision": "evidence_required",
            "bottleneck_relevance": "likely",
            "evidence_strength": "missing",
            "report_status": "partial_primary_source_missing",
            "bottleneck_confidence_score": 64,
            "evidence_quality_score": 25,
        }
    if category == "likely_hard_tech_pending_evidence":
        return {
            "review_decision": "evidence_required",
            "bottleneck_relevance": "likely" if "pending" in relevance_raw else "unclear",
            "evidence_strength": "missing",
            "report_status": "partial_primary_source_missing",
            "bottleneck_confidence_score": 56,
            "evidence_quality_score": 20,
        }
    return {
        "review_decision": "downgrade_watchlist",
        "bottleneck_relevance": "adjacent",
        "evidence_strength": "weak",
        "report_status": "evidence_insufficient",
        "bottleneck_confidence_score": 35,
        "evidence_quality_score": 15,
    }


def _evidence_rows(row: pd.Series, classification: dict[str, Any]) -> list[dict[str, Any]]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    source_path = _rel(CANONICAL_POOL)
    category = _clean(row.get("review_pool_category") or row.get("final_manual_approval_category"))
    business_category = _clean(row.get("business_relevance_category") or row.get("final_manual_approval_category"), "evidence_required")
    rationale = _clean(row.get("rationale"), "evidence_required")
    source_url = _clean(row.get("primary_source_url"))
    rows = [
        {
            "evidence_id": "E1",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "claim": "Candidate is in the canonical hard-tech review pool.",
            "section": "Executive summary",
            "source_type": "canonical_closure_v2_pool",
            "source_title": "hard_tech_review_pool_preview.csv",
            "source_path_or_url": source_path,
            "excerpt": f"{stock_name} appears in canonical v2 hard-tech review pool as {category}.",
            "evidence_strength": "moderate" if category == "verified_core" else "weak",
            "evidence_required": False,
        },
        {
            "evidence_id": "E2",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "claim": "Business category is hard-tech or bottleneck-relevant.",
            "section": "Company business overview",
            "source_type": "canonical_pool_classification",
            "source_title": "hard_tech_review_pool_preview.csv",
            "source_path_or_url": source_path,
            "excerpt": business_category,
            "evidence_strength": "weak",
            "evidence_required": False,
        },
        {
            "evidence_id": "E3",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "claim": "Local primary-source support for hard-tech thesis.",
            "section": "Evidence matrix",
            "source_type": "primary_source" if source_url else "evidence_required",
            "source_title": "primary source URL" if source_url else "evidence_required",
            "source_path_or_url": source_url or "evidence_required",
            "excerpt": rationale if source_url else "evidence_required: annual report, announcement, prospectus, official product page, or investor disclosure needed.",
            "evidence_strength": classification["evidence_strength"] if source_url else "missing",
            "evidence_required": not bool(source_url),
        },
        {
            "evidence_id": "E4",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "claim": "Financial quality and revenue structure snapshot.",
            "section": "Financial quality snapshot",
            "source_type": "evidence_required",
            "source_title": "financial statement source required",
            "source_path_or_url": "evidence_required",
            "excerpt": "evidence_required: revenue structure, gross margin, R&D, and cash-flow data were not backfilled in this report run.",
            "evidence_strength": "missing",
            "evidence_required": True,
        },
    ]
    return rows


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    frame = pd.DataFrame(rows)
    columns = ["evidence_id", "claim", "source_type", "source_path_or_url", "evidence_strength", "evidence_required"]
    return frame[columns].to_markdown(index=False)


def _render_markdown(row: pd.Series, classification: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    category = _clean(row.get("review_pool_category") or row.get("final_manual_approval_category"))
    business_category = _clean(row.get("business_relevance_category") or row.get("final_manual_approval_category"), "evidence_required")
    rationale = _clean(row.get("rationale"), "evidence_required")
    next_action = _clean(row.get("recommended_next_action"), "evidence_required: define next source check")
    return f"""# {stock_name} ({stock_code}) Hard-Tech Bottleneck Candidate Report

Research-only. Manual review only. Not used for signal or admission.

## Executive summary

- Candidate source: canonical pipeline closure v2 hard-tech review pool. [E1]
- Review decision: {classification['review_decision']}
- Bottleneck relevance: {classification['bottleneck_relevance']}
- Evidence strength: {classification['evidence_strength']}
- Report status: {classification['report_status']}

## Company business overview

- Current local business category: {business_category}. [E2]
- Local rationale: {rationale}. [E1]

## Main products and revenue structure

evidence_required: product mix, revenue split, customer exposure, and segment economics require annual report or official disclosure evidence. [E4]

## Hard-tech bottleneck thesis

The candidate remains in the hard-tech review workflow because the canonical v2 pool classifies it as `{category}`. [E1]
Primary-source verification is required before any claim can be treated as verified core. [E3]

## Industry chain position

evidence_required: map upstream/downstream industry-chain position using annual report, prospectus, announcement, or official product evidence. [E3]

## Technology capability

evidence_required: validate product capability, process capability, customer certification, or technical platform with primary-source evidence. [E3]

## R&D and patents / technical platform

evidence_required: R&D intensity, patents, core platform, or technical moat require source-backed extraction. [E3]

## Domestic substitution / supply chain security logic

evidence_required: import substitution, domestic replacement, supply-chain security, or customer certification must be linked to primary or credible secondary evidence. [E3]

## Industry and competition

evidence_required: competitor set, substitute maturity, route-around risk, and value capture require source-backed research. [E3]

## Financial quality snapshot

evidence_required: financial quality snapshot was not inferred from concept tags or company name. [E4]

## Evidence matrix

{_markdown_table(evidence)}

## Risks and disqualifiers

- Missing primary-source evidence can force downgrade or exclusion. [E3]
- Concept tags alone are not valid evidence. [E3]
- Financial and revenue exposure gaps remain until source-backed extraction is complete. [E4]

## Research-only conclusion

This report is a research-only candidate dossier. The scores below are workflow confidence scores, not trading scores:

- bottleneck_confidence_score: {classification['bottleneck_confidence_score']}
- evidence_quality_score: {classification['evidence_quality_score']}

No production signal, admission, scoring logic, position guidance, or execution action is generated.

## Next action

{next_action}. [E3]
"""


def _render_html(markdown_text: str, title: str) -> str:
    escaped = html.escape(markdown_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; line-height: 1.55; color: #17202a; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f7f8fa; padding: 20px; border: 1px solid #d9dee7; }}
  </style>
</head>
<body>
<pre>{escaped}</pre>
</body>
</html>
"""


def _render_pdf(markdown_text: str, path: Path) -> tuple[str, str]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover - depends on environment
        return "failed", f"reportlab unavailable: {exc}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        x = 40
        y = height - 42
        pdf.setFont("Helvetica", 9)
        for raw_line in markdown_text.splitlines():
            line = raw_line.encode("latin-1", "replace").decode("latin-1")
            while len(line) > 110:
                pdf.drawString(x, y, line[:110])
                line = line[110:]
                y -= 12
                if y < 40:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 9)
                    y = height - 42
            pdf.drawString(x, y, line)
            y -= 12
            if y < 40:
                pdf.showPage()
                pdf.setFont("Helvetica", 9)
                y = height - 42
        pdf.save()
        return "generated", ""
    except Exception as exc:  # pragma: no cover - renderer failure is recorded
        return "failed", str(exc)


def _trading_language_hit_count(text: str) -> int:
    lowered = text.lower()
    return sum(lowered.count(phrase.lower()) for phrase in FORBIDDEN_TRADING_PHRASES)


def generate_one(row: pd.Series, reports_dir: Path, updated_at: str) -> dict[str, Any]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    candidate_dir = reports_dir / f"{stock_code}_{_safe_name(stock_name)}"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    classification = _classification(row)
    evidence = _evidence_rows(row, classification)
    markdown_text = _render_markdown(row, classification, evidence)
    trading_hits = _trading_language_hit_count(markdown_text)

    report_md_path = candidate_dir / "report.md"
    report_html_path = candidate_dir / "report.html"
    report_pdf_path = candidate_dir / "report.pdf"
    evidence_matrix_path = candidate_dir / "evidence_matrix.csv"
    sources_path = candidate_dir / "sources.jsonl"
    excerpts_path = candidate_dir / "excerpts.csv"

    report_md_path.write_text(markdown_text, encoding="utf-8")
    report_html_path.write_text(_render_html(markdown_text, f"{stock_name} hard-tech report"), encoding="utf-8")
    pd.DataFrame(evidence).to_csv(evidence_matrix_path, index=False)
    _append_jsonl(sources_path, evidence)
    pd.DataFrame(
        [
            {
                "evidence_id": item["evidence_id"],
                "stock_code": stock_code,
                "stock_name": stock_name,
                "excerpt": item["excerpt"],
            }
            for item in evidence
        ]
    ).to_csv(excerpts_path, index=False)
    pdf_status, pdf_failure_reason = _render_pdf(markdown_text, report_pdf_path)

    report_status = classification["report_status"]
    if trading_hits:
        report_status = "failed"
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "source_group": _clean(row.get("source_group")),
        "review_pool_category": _clean(row.get("review_pool_category") or row.get("final_manual_approval_category")),
        "review_decision": classification["review_decision"],
        "bottleneck_relevance": classification["bottleneck_relevance"],
        "evidence_strength": classification["evidence_strength"],
        "report_status": report_status,
        "pdf_status": pdf_status,
        "pdf_failure_reason": pdf_failure_reason,
        "bottleneck_confidence_score": classification["bottleneck_confidence_score"],
        "evidence_quality_score": classification["evidence_quality_score"],
        "report_md_path": _rel(report_md_path),
        "report_html_path": _rel(report_html_path),
        "report_pdf_path": _rel(report_pdf_path) if pdf_status == "generated" else "",
        "evidence_matrix_path": _rel(evidence_matrix_path),
        "sources_jsonl_path": _rel(sources_path),
        "excerpts_path": _rel(excerpts_path),
        "hard_tech_claim_count": 4,
        "evidence_required_count": int(sum(bool(item["evidence_required"]) for item in evidence)),
        "trading_language_hit_count": trading_hits,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "updated_at": updated_at,
    }


def _landscape_markdown(summary: dict[str, Any], manifest: pd.DataFrame) -> str:
    by_status = manifest["report_status"].value_counts().rename_axis("report_status").reset_index(name="count")
    by_decision = manifest["review_decision"].value_counts().rename_axis("review_decision").reset_index(name="count")
    return f"""# Hard-Tech Candidate Landscape Report

Research-only landscape summary for canonical v2 hard-tech review pool reports.

## Scope

- canonical scope count: {summary['canonical_scope_count']}
- generated report count: {summary['generated_report_count']}
- legacy 114 pool used as default: {summary['legacy_pool_used_as_default']}

## Report Status

{by_status.to_markdown(index=False)}

## Review Decisions

{by_decision.to_markdown(index=False)}

## Guardrails

- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}
- production_update: {summary['production_update']}
- strategy_files_modified: {summary['formal_strategy_files_modified']}
"""


def generate(output_dir: Path = OUTPUT_DIR, limit: int | None = None, stock_codes: str | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / "reports"
    pool = _load_pool()
    selected = _select_candidates(pool, stock_codes, limit)
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [generate_one(row, reports_dir, updated_at) for _, row in selected.iterrows()]
    manifest = pd.DataFrame(rows).sort_values(["stock_code"], kind="stable").reset_index(drop=True)

    strategy_diff = _git_diff_formal_strategy_files()
    closure = json.loads((CLOSURE_DIR / "pipeline_closure_v2_summary.json").read_text(encoding="utf-8"))
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "canonical_pool_path": _rel(CANONICAL_POOL),
        "closure_path": _rel(CLOSURE_DIR),
        "canonical_scope_count": int(len(pool)),
        "legacy_pool_path": _rel(LEGACY_POOL),
        "legacy_pool_count": int(len(pd.read_csv(LEGACY_POOL))),
        "legacy_pool_used_as_default": False,
        "closure_acceptance_decision": closure.get("acceptance_decision"),
        "generated_report_count": int(len(manifest)),
        "markdown_generated_count": int(manifest["report_md_path"].astype(bool).sum()) if not manifest.empty else 0,
        "html_generated_count": int(manifest["report_html_path"].astype(bool).sum()) if not manifest.empty else 0,
        "pdf_generated_count": int(manifest["pdf_status"].eq("generated").sum()) if not manifest.empty else 0,
        "pdf_failed_count": int(manifest["pdf_status"].eq("failed").sum()) if not manifest.empty else 0,
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "production_update": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "trading_language_hit_count": int(manifest["trading_language_hit_count"].sum()) if not manifest.empty else 0,
        "acceptance_decision": "tech_bottleneck_candidate_reports_ready" if strategy_diff == "" else "blocked_due_to_guardrail_failure",
        "updated_at": updated_at,
    }

    _write_json(output_dir / "report_run_summary.json", summary)
    manifest.to_csv(output_dir / "report_manifest.csv", index=False)
    _write_json(output_dir / "report_manifest.json", manifest.to_dict(orient="records"))
    pool_with_status = pool.merge(
        manifest[
            [
                "stock_code",
                "report_status",
                "report_md_path",
                "report_html_path",
                "report_pdf_path",
                "evidence_matrix_path",
                "bottleneck_confidence_score",
                "evidence_quality_score",
                "updated_at",
            ]
        ],
        on="stock_code",
        how="left",
    )
    pool_with_status.to_csv(output_dir / "hard_tech_review_pool_with_report_status.csv", index=False)
    quality = manifest[
        [
            "stock_code",
            "stock_name",
            "report_status",
            "pdf_status",
            "hard_tech_claim_count",
            "evidence_required_count",
            "trading_language_hit_count",
            "used_for_signal",
            "used_for_admission",
        ]
    ].copy()
    quality.to_csv(output_dir / "report_quality_audit.csv", index=False)
    coverage = (
        manifest.groupby(["review_pool_category", "report_status"], dropna=False)
        .size()
        .reset_index(name="candidate_count")
        if not manifest.empty
        else pd.DataFrame(columns=["review_pool_category", "report_status", "candidate_count"])
    )
    coverage.to_csv(output_dir / "evidence_coverage_summary.csv", index=False)
    landscape = _landscape_markdown(summary, manifest)
    landscape_md = output_dir / "hard_tech_candidate_landscape_report.md"
    landscape_pdf = output_dir / "hard_tech_candidate_landscape_report.pdf"
    landscape_md.write_text(landscape, encoding="utf-8")
    _render_pdf(landscape, landscape_pdf)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--stock-codes", default=None)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir, limit=args.limit, stock_codes=args.stock_codes)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
