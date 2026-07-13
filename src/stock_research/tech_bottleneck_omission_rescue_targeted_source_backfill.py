from __future__ import annotations

import argparse
import json
import signal
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.data_to_brief_backfill_primary_source_text_first_parse import (
    _extract_pages,
    _normalize_text,
    _split_chunk,
)
from stock_research.tech_bottleneck_hard_tech_keyword_taxonomy import SEED_KEYWORD_CATEGORIES
from stock_research.tech_bottleneck_omission_rescue_evidence_completion_reassessment import (
    run as run_omission_rescue_reassessment,
)
from stock_research.tech_bottleneck_remaining_primary_source_collection import (
    SEARCH_CATEGORIES,
    _build_manifest as _build_cninfo_manifest,
    _download_pdf as _download_cninfo_pdf,
    _load_stock_org_map,
    _query_cninfo,
    _select_announcements,
    _session,
)
from stock_research.tech_bottleneck_review_universe_quality_reassessment import (
    PROJECT_ROOT,
    _stock_code,
)
from stock_research.tech_bottleneck_review_universe_yanbaoke_report_backfill import (
    run_tech_bottleneck_review_universe_yanbaoke_report_backfill,
)


TASK_NAME = "tech_bottleneck_omission_rescue_targeted_source_backfill_v1"
REMAINING_GAP_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1/"
    "omission_rescue_remaining_evidence_gap_queue.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

BUSINESS_EVIDENCE_KEYWORDS = [
    "主营业务",
    "主要产品",
    "营业收入",
    "毛利率",
    "分产品",
    "客户",
    "订单",
    "产能",
    "认证",
    "研发",
    "核心技术",
    "关键技术",
    "国产替代",
    "自主可控",
    "供应链",
    "验证周期",
    "良率",
    "风险",
    "竞争",
]
HARD_TECH_KEYWORDS = sorted({keyword for values in SEED_KEYWORD_CATEGORIES.values() for keyword in values}, key=len, reverse=True)


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _downloaded_count(frame: pd.DataFrame, status_column: str, ok_statuses: set[str]) -> int:
    if frame.empty or status_column not in frame.columns:
        return 0
    return int(frame[status_column].astype(str).isin(ok_statuses).sum())


def _downloaded_stock_count(frame: pd.DataFrame, status_column: str, ok_statuses: set[str]) -> int:
    if frame.empty or status_column not in frame.columns or "stock_code" not in frame.columns:
        return 0
    return int(frame.loc[frame[status_column].astype(str).isin(ok_statuses), "stock_code"].astype(str).nunique())


def _default_primary_collector(
    queue: pd.DataFrame,
    output: Path,
    *,
    max_sources_per_stock: int,
    start_date: str,
    end_date: str,
    sleep_seconds: float,
) -> dict[str, pd.DataFrame]:
    download_dir = output / "cninfo_primary_source_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []

    try:
        org_map = _load_stock_org_map(session)
    except Exception as exc:  # noqa: BLE001 - audited and non-blocking.
        org_map = {}
        for _, row in queue.iterrows():
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "category": category,
                        "status": "stock_map_error",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )

    for _, row in queue.iterrows():
        code = str(row["stock_code"])
        name = str(row.get("stock_name") or "")
        org_id = org_map.get(code, "")
        candidates = []
        if org_id:
            for category in SEARCH_CATEGORIES:
                found, audit = _query_cninfo(
                    session,
                    stock_code=code,
                    stock_name=name,
                    org_id=org_id,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
                candidates.extend(found)
                search_rows.append(audit)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        elif org_map:
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "category": category,
                        "status": "org_id_missing",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": "org_id_missing",
                        "error_message": "stock code not found in cninfo stock map",
                    }
                )
        selected = _select_announcements(candidates, max_per_stock=max_sources_per_stock)
        for search_row in search_rows:
            if search_row["stock_code"] == code and search_row["status"] == "ok":
                search_row["selected_count"] = len([item for item in selected if item.category == search_row["category"]])
        for item in selected:
            download_rows.append(_download_cninfo_pdf(session, item, download_dir))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    search = pd.DataFrame(search_rows)
    downloads = pd.DataFrame(download_rows)
    manifest = _build_cninfo_manifest(downloads)
    return {"manifest": manifest, "search": search, "downloads": downloads}


def _default_broker_report_collector(
    universe_path: Path,
    output: Path,
    *,
    max_reports_per_stock: int,
    start_date: str,
    end_date: str,
    sleep_seconds: float,
) -> dict[str, pd.DataFrame]:
    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=universe_path,
        output_dir=output / "yanbaoke_report_backfill",
        search_roots=[output, PROJECT_ROOT / "outputs/research", PROJECT_ROOT / "data/reports"],
        max_reports_per_stock=max_reports_per_stock,
        max_missing_stocks=None,
        start_date=start_date,
        end_date=end_date,
        sleep_seconds=sleep_seconds,
    )
    return {
        "downloads": result.get("downloads", pd.DataFrame()),
        "search": result.get("search", pd.DataFrame()),
        "coverage": result.get("coverage", pd.DataFrame()),
    }


def _source_rows_from_cninfo(manifest: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if manifest.empty:
        return rows
    for row in manifest.fillna("").to_dict("records"):
        path = str(row.get("local_pdf_path") or "")
        if not path or not Path(path).exists():
            continue
        rows.append(
            {
                "stock_code": _stock_code(row.get("stock_code")),
                "stock_name": str(row.get("stock_name") or ""),
                "source_type": str(row.get("source_type") or "primary_source"),
                "source_title": str(row.get("source_title") or ""),
                "source_path": path,
                "local_pdf_path": path,
                "source_url": str(row.get("source_url") or ""),
                "provider": str(row.get("provider") or "cninfo"),
                "source_id": str(row.get("source_id") or f"cninfo-{row.get('stock_code')}-{len(rows)+1}"),
                "is_primary_source": True,
            }
        )
    return rows


def _source_rows_from_yanbaoke(downloads: pd.DataFrame, coverage: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not downloads.empty:
        ok = downloads[downloads.get("status", pd.Series(dtype=str)).astype(str).isin(["downloaded", "already_downloaded"])].copy()
        for row in ok.fillna("").to_dict("records"):
            path = str(row.get("pdf_path") or "")
            if not path or not Path(path).exists():
                continue
            rows.append(
                {
                    "stock_code": _stock_code(row.get("stock_code")),
                    "stock_name": str(row.get("stock_name") or ""),
                    "source_type": "broker_report",
                    "source_title": str(row.get("report_title") or row.get("filename") or Path(path).name),
                    "source_path": path,
                    "local_pdf_path": path,
                    "source_url": str(row.get("download_url") or ""),
                    "provider": str(row.get("org_name") or "yanbaoke"),
                    "source_id": str(row.get("uuid") or f"yanbaoke-{row.get('stock_code')}-{len(rows)+1}"),
                    "is_primary_source": False,
                }
            )
    if not coverage.empty and "report_pdf_paths" in coverage.columns:
        for row in coverage.fillna("").to_dict("records"):
            for raw_path in str(row.get("report_pdf_paths") or "").split("|"):
                path = raw_path.strip()
                if not path or not path.lower().endswith(".pdf") or not Path(path).exists():
                    continue
                rows.append(
                    {
                        "stock_code": _stock_code(row.get("stock_code")),
                        "stock_name": str(row.get("stock_name") or ""),
                        "source_type": "broker_report",
                        "source_title": Path(path).stem,
                        "source_path": path,
                        "local_pdf_path": path,
                        "source_url": "",
                        "provider": "existing_yanbaoke_pdf",
                        "source_id": f"existing-report-{_stock_code(row.get('stock_code'))}-{len(rows)+1}",
                        "is_primary_source": False,
                    }
                )
    return rows


def _build_source_index(cninfo_manifest: pd.DataFrame, yanbaoke_downloads: pd.DataFrame, yanbaoke_coverage: pd.DataFrame) -> pd.DataFrame:
    rows = _source_rows_from_cninfo(cninfo_manifest) + _source_rows_from_yanbaoke(yanbaoke_downloads, yanbaoke_coverage)
    if not rows:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_type",
                "source_title",
                "source_path",
                "local_pdf_path",
                "source_url",
                "provider",
                "source_id",
                "is_primary_source",
            ]
        )
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["stock_code", "source_path"], keep="first")
        .sort_values(["stock_code", "is_primary_source", "source_title"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def _page_score(text: str, stock_name: str) -> tuple[int, list[str]]:
    matches: list[str] = []
    for keyword in HARD_TECH_KEYWORDS + BUSINESS_EVIDENCE_KEYWORDS:
        if keyword and keyword in text:
            matches.append(keyword)
    if stock_name and stock_name in text:
        matches.append(stock_name)
    return len(set(matches)), sorted(set(matches), key=len, reverse=True)


def _claim_type(text: str) -> str:
    if any(token in text for token in ["毛利率", "营业收入", "分产品", "收入"]):
        return "financial_or_business_composition"
    if any(token in text for token in ["风险", "竞争", "替代", "不确定"]):
        return "risk_or_disconfirmation"
    if any(token in text for token in ["客户", "认证", "验证", "产能", "订单"]):
        return "customer_capacity_or_validation"
    if any(token in text for token in HARD_TECH_KEYWORDS):
        return "hard_tech_exposure"
    return "primary_or_broker_source_context"


def _default_pdf_parser(
    sources: pd.DataFrame,
    *,
    max_pages_per_source: int,
    max_chunks_per_source: int,
    per_source_timeout_seconds: int = 8,
) -> dict[str, pd.DataFrame]:
    evidence_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for source_index, source in enumerate(sources.fillna("").to_dict("records"), start=1):
        pdf_path = Path(str(source.get("local_pdf_path") or source.get("source_path") or ""))
        base = {
            "stock_code": _stock_code(source.get("stock_code")),
            "stock_name": str(source.get("stock_name") or ""),
            "source_type": str(source.get("source_type") or ""),
            "source_title": str(source.get("source_title") or ""),
            "source_path": str(pdf_path),
            "source_id": str(source.get("source_id") or f"source-{source_index}"),
            "provider": str(source.get("provider") or ""),
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        try:
            pages, metadata = _extract_pages_with_timeout(
                pdf_path,
                max_pages_per_source=max_pages_per_source,
                timeout_seconds=per_source_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - per PDF parse failure is audited.
            row = {**base, "parse_status": "parse_failed", "error_type": type(exc).__name__, "error_message": str(exc)[:500]}
            manifest_rows.append(row)
            failure_rows.append(row)
            continue
        scored_pages = []
        for page in pages:
            score, matches = _page_score(str(page.get("text") or ""), base["stock_name"])
            page = dict(page)
            page["target_score"] = score
            page["target_matches"] = matches
            scored_pages.append(page)
        selected = sorted(
            [page for page in scored_pages if int(page.get("target_score") or 0) > 0] or scored_pages[: min(3, len(scored_pages))],
            key=lambda item: (-int(item.get("target_score") or 0), int(item.get("page") or 0)),
        )[:max_chunks_per_source]
        selected = sorted(selected, key=lambda item: int(item.get("page") or 0))
        parse_status = "parsed" if selected else "evidence_required"
        manifest_rows.append(
            {
                **base,
                "parse_status": parse_status,
                "page_count": metadata.get("page_count", 0),
                "pages_examined": metadata.get("pages_examined", 0),
                "non_empty_page_count": metadata.get("non_empty_page_count", 0),
                "selected_page_count": len(selected),
                "extract_error_count": metadata.get("extract_error_count", 0),
                "extract_errors": metadata.get("extract_errors", ""),
            }
        )
        if not selected:
            failure_rows.append({**base, "parse_status": "evidence_required", "error_type": "NoSelectedPages", "error_message": "No text pages matched evidence terms."})
            continue
        chunk_index = 1
        for page in selected:
            for part_index, chunk_text in enumerate(_split_chunk(_normalize_text(str(page.get("text") or "")), max_chars=1800), start=1):
                if not chunk_text:
                    continue
                evidence_rows.append(
                    {
                        **base,
                        "page": int(page.get("page") or 0),
                        "page_start": int(page.get("page") or 0),
                        "page_end": int(page.get("page") or 0),
                        "citation_id": f"ORS{source_index}P{int(page.get('page') or 0)}C{part_index}",
                        "chunk_id": f"{base['stock_code']}-ORS{source_index}-P{int(page.get('page') or 0)}-C{part_index}",
                        "chunk_index": chunk_index,
                        "evidence_text": chunk_text,
                        "excerpt": chunk_text[:320],
                        "chunk_text": chunk_text,
                        "evidence_claim_type": _claim_type(chunk_text),
                        "citation_quality": "page_level",
                        "matched_keywords": "|".join(page.get("target_matches") or []),
                        "keyword_score": int(page.get("target_score") or 0),
                    }
                )
                chunk_index += 1
    return {
        "evidence": pd.DataFrame(evidence_rows),
        "parse_manifest": pd.DataFrame(manifest_rows),
        "parse_failures": pd.DataFrame(failure_rows),
    }


def _extract_pages_with_timeout(pdf_path: Path, *, max_pages_per_source: int, timeout_seconds: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if timeout_seconds <= 0:
        return _extract_pages(pdf_path, max_pages_per_source=max_pages_per_source)

    def _raise_timeout(signum: int, frame: Any) -> None:  # noqa: ARG001
        raise TimeoutError(f"PDF text extraction exceeded {timeout_seconds}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(timeout_seconds)
    try:
        return _extract_pages(pdf_path, max_pages_per_source=max_pages_per_source)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copyfile(source, target)


def _prepare_reassessment_queue(queue: pd.DataFrame, output: Path) -> Path:
    keep_columns = [
        "stock_code",
        "stock_name",
        "source_artifact",
        "source_bucket",
        "already_in_review_universe",
        "primary_source_supported",
        "primary_source_evidence_count",
        "page_level_citation_count",
        "tech_bottleneck_domain",
        "supply_chain_role",
        "concept_pollution_risk",
        "remaining_evidence_gap_flags",
        "downgrade_risk_flags",
        "recall_decision",
        "recall_reason",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    ]
    cleaned = queue[[column for column in keep_columns if column in queue.columns]].copy()
    path = output / "omission_rescue_reassessment_input_queue.csv"
    cleaned.to_csv(path, index=False)
    return path


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    text = f"""# {TASK_NAME}

## Summary

- source remaining gap count: {summary['source_remaining_gap_count']}
- processed count: {summary['processed_count']}
- CNINFO downloaded PDFs: {summary['cninfo_downloaded_pdf_count']}
- Yanbaoke downloaded PDFs: {summary['yanbaoke_downloaded_pdf_count']}
- parsed PDFs: {summary['parsed_pdf_count']}
- page-level evidence stocks after: {summary['page_level_evidence_stock_count_after']}
- remaining evidence gaps after: {summary['remaining_evidence_gap_count_after']}
- tier1/tier2/tier3/tier4: {summary['tier_1_core_review_priority_count']} / {summary['tier_2_strong_review_candidate_count']} / {summary['tier_3_quality_or_value_capture_gap_count']} / {summary['tier_4_downgrade_or_reject_review_count']}

## Guardrails

- research_only: true
- frozen_quality_pool_generated: false
- auto_added_to_quality_pool_count: 0
- used_for_signal/admission: 0 / 0
- strategy_file_diff_clean: {str(summary['strategy_file_diff_clean']).lower()}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_omission_rescue_targeted_source_backfill_v1_report.md").write_text(text, encoding="utf-8")


def run(
    *,
    remaining_gap_queue_path: Path = REMAINING_GAP_QUEUE,
    output_dir: Path = OUTPUT_DIR,
    max_primary_sources_per_stock: int = 2,
    max_reports_per_stock: int = 1,
    max_pages_per_source: int = 80,
    max_chunks_per_source: int = 4,
    per_source_timeout_seconds: int = 8,
    start_date: str = "2021-01-01",
    end_date: str = "2026-07-10",
    sleep_seconds: float = 0.2,
    as_of_date: str = "2026-07-09",
    service: str = SETTINGS.research_service,
    primary_collector: Callable[..., dict[str, pd.DataFrame]] | None = None,
    broker_report_collector: Callable[..., dict[str, pd.DataFrame]] | None = None,
    pdf_parser: Callable[..., dict[str, pd.DataFrame]] | None = None,
    market_profile: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    queue = _read_csv(Path(remaining_gap_queue_path)).sort_values("stock_code").reset_index(drop=True)
    universe = queue[["stock_code", "stock_name"]].drop_duplicates().sort_values("stock_code").reset_index(drop=True)
    universe_path = output / "omission_rescue_gap_universe.csv"
    universe.to_csv(universe_path, index=False)

    primary = (primary_collector or _default_primary_collector)(
        queue,
        output,
        max_sources_per_stock=max_primary_sources_per_stock,
        start_date=start_date,
        end_date=end_date,
        sleep_seconds=sleep_seconds,
    )
    cninfo_manifest = primary.get("manifest", pd.DataFrame())
    cninfo_search = primary.get("search", pd.DataFrame())
    cninfo_downloads = primary.get("downloads", pd.DataFrame())

    broker = (broker_report_collector or _default_broker_report_collector)(
        universe_path,
        output,
        max_reports_per_stock=max_reports_per_stock,
        start_date=start_date,
        end_date=end_date,
        sleep_seconds=sleep_seconds,
    )
    yanbaoke_downloads = broker.get("downloads", pd.DataFrame())
    yanbaoke_search = broker.get("search", pd.DataFrame())
    yanbaoke_coverage = broker.get("coverage", pd.DataFrame())

    sources = _build_source_index(cninfo_manifest, yanbaoke_downloads, yanbaoke_coverage)
    parsed = (pdf_parser or _default_pdf_parser)(
        sources,
        max_pages_per_source=max_pages_per_source,
        max_chunks_per_source=max_chunks_per_source,
        per_source_timeout_seconds=per_source_timeout_seconds,
    )
    evidence = parsed.get("evidence", pd.DataFrame())
    parse_manifest = parsed.get("parse_manifest", pd.DataFrame())
    parse_failures = parsed.get("parse_failures", pd.DataFrame())

    cninfo_manifest.to_csv(output / "omission_rescue_primary_source_manifest.csv", index=False)
    cninfo_search.to_csv(output / "omission_rescue_cninfo_search_audit.csv", index=False)
    cninfo_downloads.to_csv(output / "omission_rescue_cninfo_download_manifest.csv", index=False)
    yanbaoke_search.to_csv(output / "omission_rescue_yanbaoke_report_search_results.csv", index=False)
    yanbaoke_downloads.to_csv(output / "omission_rescue_yanbaoke_report_download_manifest.csv", index=False)
    sources.to_csv(output / "omission_rescue_targeted_source_index.csv", index=False)
    evidence.to_csv(output / "omission_rescue_targeted_evidence_index.csv", index=False)
    parse_manifest.to_csv(output / "omission_rescue_targeted_parse_manifest.csv", index=False)
    parse_failures.to_csv(output / "omission_rescue_targeted_parse_failures.csv", index=False)

    reassessment_dir = output / "reassessment"
    reassessment_queue_path = _prepare_reassessment_queue(queue, output)
    reassessment_summary = run_omission_rescue_reassessment(
        rescue_queue_path=reassessment_queue_path,
        evidence_files=[output / "omission_rescue_targeted_evidence_index.csv"],
        output_dir=reassessment_dir,
        as_of_date=as_of_date,
        service=service,
        market_profile=market_profile,
    )
    _copy_if_exists(reassessment_dir / "omission_rescue_quality_reassessment.csv", output / "omission_rescue_targeted_quality_reassessment.csv")
    _copy_if_exists(reassessment_dir / "omission_rescue_tier1_priority_review.csv", output / "omission_rescue_targeted_tier1_priority_review.csv")
    _copy_if_exists(reassessment_dir / "omission_rescue_tier2_review_candidate.csv", output / "omission_rescue_targeted_tier2_review_candidate.csv")
    _copy_if_exists(reassessment_dir / "omission_rescue_tier3_gap_or_hold.csv", output / "omission_rescue_targeted_tier3_gap_or_hold.csv")
    _copy_if_exists(reassessment_dir / "omission_rescue_tier4_reject_or_downgrade.csv", output / "omission_rescue_targeted_tier4_reject_or_downgrade.csv")
    _copy_if_exists(reassessment_dir / "omission_rescue_remaining_evidence_gap_queue.csv", output / "omission_rescue_targeted_remaining_evidence_gap_queue.csv")

    strategy_clean = _strategy_diff_clean()
    cninfo_downloaded = _downloaded_count(cninfo_downloads, "download_status", {"downloaded", "already_exists"})
    yanbaoke_downloaded = _downloaded_count(yanbaoke_downloads, "status", {"downloaded", "already_downloaded"})
    parsed_pdf_count = (
        int(parse_manifest["parse_status"].astype(str).eq("parsed").sum())
        if not parse_manifest.empty and "parse_status" in parse_manifest.columns
        else 0
    )
    source_stock_count = int(universe["stock_code"].nunique())
    used_for_signal = int(evidence["used_for_signal"].astype(str).str.lower().isin(["true", "1"]).sum()) if not evidence.empty and "used_for_signal" in evidence else 0
    used_for_admission = int(evidence["used_for_admission"].astype(str).str.lower().isin(["true", "1"]).sum()) if not evidence.empty and "used_for_admission" in evidence else 0
    blocking = source_stock_count != len(queue) or used_for_signal or used_for_admission or not strategy_clean
    remaining_after = int(reassessment_summary.get("remaining_evidence_gap_count", 0))
    acceptance = (
        "blocked_due_to_guardrail_violation"
        if blocking
        else ("omission_rescue_targeted_source_backfill_ready" if remaining_after == 0 else "conditionally_ready_with_source_gaps")
    )
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_remaining_gap_count": int(len(queue)),
        "processed_count": source_stock_count,
        "cninfo_downloaded_pdf_count": cninfo_downloaded,
        "cninfo_downloaded_stock_count": _downloaded_stock_count(cninfo_downloads, "download_status", {"downloaded", "already_exists"}),
        "yanbaoke_downloaded_pdf_count": yanbaoke_downloaded,
        "yanbaoke_downloaded_stock_count": _downloaded_stock_count(yanbaoke_downloads, "status", {"downloaded", "already_downloaded"}),
        "source_pdf_count": int(len(sources)),
        "primary_source_pdf_count": int(sources["is_primary_source"].astype(bool).sum()) if not sources.empty and "is_primary_source" in sources else 0,
        "broker_report_source_pdf_count": int(sources["source_type"].astype(str).eq("broker_report").sum()) if not sources.empty and "source_type" in sources else 0,
        "yanbaoke_existing_or_reused_pdf_count": int(
            sources["provider"].astype(str).isin(["existing_yanbaoke_pdf", "yanbaoke"]).sum()
        )
        if not sources.empty and "provider" in sources
        else 0,
        "parsed_pdf_count": parsed_pdf_count,
        "parse_failure_count": int(len(parse_failures)),
        "targeted_evidence_index_rows": int(len(evidence)),
        "page_level_evidence_stock_count_after": int(reassessment_summary.get("page_level_evidence_stock_count", 0)),
        "remaining_evidence_gap_count_after": remaining_after,
        "scored_count": int(reassessment_summary.get("scored_count", 0)),
        "tier_1_core_review_priority_count": int(reassessment_summary.get("tier_1_core_review_priority_count", 0)),
        "tier_2_strong_review_candidate_count": int(reassessment_summary.get("tier_2_strong_review_candidate_count", 0)),
        "tier_3_quality_or_value_capture_gap_count": int(reassessment_summary.get("tier_3_quality_or_value_capture_gap_count", 0)),
        "tier_4_downgrade_or_reject_review_count": int(reassessment_summary.get("tier_4_downgrade_or_reject_review_count", 0)),
        "primary_source_collection_performed": True,
        "broker_report_collection_performed": True,
        "evidence_parse_performed": True,
        "quality_reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": acceptance,
    }
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_remaining_gap_count": summary["source_remaining_gap_count"],
        "processed_count": summary["processed_count"],
        "only_remaining_gap_processed": summary["source_remaining_gap_count"] == 74 and summary["processed_count"] == 74,
        "primary_source_collection_performed": True,
        "broker_report_collection_performed": True,
        "evidence_parse_performed": True,
        "quality_reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": acceptance,
    }
    _write_json(output / "omission_rescue_targeted_source_backfill_summary.json", summary)
    _write_json(output / "omission_rescue_targeted_source_backfill_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Targeted CNINFO/Yanbaoke source backfill for omission-rescue evidence gaps.")
    parser.add_argument("--remaining-gap-queue-path", type=Path, default=REMAINING_GAP_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-primary-sources-per-stock", type=int, default=2)
    parser.add_argument("--max-reports-per-stock", type=int, default=1)
    parser.add_argument("--max-pages-per-source", type=int, default=80)
    parser.add_argument("--max-chunks-per-source", type=int, default=4)
    parser.add_argument("--per-source-timeout-seconds", type=int, default=8)
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default="2026-07-10")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--as-of-date", default="2026-07-09")
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args(argv)
    summary = run(
        remaining_gap_queue_path=args.remaining_gap_queue_path,
        output_dir=args.output_dir,
        max_primary_sources_per_stock=args.max_primary_sources_per_stock,
        max_reports_per_stock=args.max_reports_per_stock,
        max_pages_per_source=args.max_pages_per_source,
        max_chunks_per_source=args.max_chunks_per_source,
        per_source_timeout_seconds=args.per_source_timeout_seconds,
        start_date=args.start_date,
        end_date=args.end_date,
        sleep_seconds=args.sleep_seconds,
        as_of_date=args.as_of_date,
        service=args.service,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|processed_count|{summary['processed_count']}")
    print(f"{TASK_NAME}|cninfo_downloaded_pdf_count|{summary['cninfo_downloaded_pdf_count']}")
    print(f"{TASK_NAME}|yanbaoke_downloaded_pdf_count|{summary['yanbaoke_downloaded_pdf_count']}")
    print(f"{TASK_NAME}|remaining_evidence_gap_count_after|{summary['remaining_evidence_gap_count_after']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
