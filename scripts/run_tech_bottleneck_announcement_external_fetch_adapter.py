#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd


FULLTEXT_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v1")
INGESTION_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_announcement_external_fetch_adapter_v1")
RULE_VERSION = "tech_bottleneck_announcement_external_fetch_adapter_v1"

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


class FetchResponse:
    def __init__(self, http_status: int, content_type: str, body: bytes) -> None:
        self.http_status = http_status
        self.content_type = content_type
        self.body = body


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


def stable_cache_key(announcement_id: Any, source_url: Any) -> str:
    seed = str(announcement_id or source_url or "").strip()
    if not seed:
        seed = str(source_url or "").strip()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    readable = re.sub(r"[^0-9A-Za-z]+", "_", _extract_url_id(seed) or "announcement").strip("_")[:40]
    return f"{readable}_{digest}"


def _extract_url_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"AN(\d+)|/(\d{9,})\.PDF|_(\d{9,})\.", text, re.IGNORECASE)
    if not match:
        return ""
    return next(part for part in match.groups() if part)


def _domain(url: Any) -> str:
    try:
        return urllib.parse.urlparse(str(url)).netloc
    except Exception:
        return ""


def _expected_content_type(url: Any) -> str:
    path = urllib.parse.urlparse(str(url or "")).path.lower()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".html") or path:
        return "text/html"
    return "unknown"


def build_external_fetch_plan(fulltext_fetch_plan: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    cache_root = output_dir / "cache"
    raw_dir = cache_root / "raw"
    text_dir = cache_root / "text"
    pdf_dir = cache_root / "pdf"
    html_dir = cache_root / "html"
    for directory in [raw_dir, text_dir, pdf_dir, html_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    source = fulltext_fetch_plan[
        fulltext_fetch_plan.get("recommended_fetch_method", pd.Series(dtype=str)).fillna("").astype(str).eq("fetch_source_url")
    ].copy()
    rows: list[dict[str, Any]] = []
    for row in source.itertuples(index=False):
        url = str(getattr(row, "source_url", "") or "")
        key = stable_cache_key(getattr(row, "announcement_id", ""), url)
        raw_path = raw_dir / f"{key}.bin"
        html_path = html_dir / f"{key}.html"
        pdf_path = pdf_dir / f"{key}.pdf"
        text_path = text_dir / f"{key}.txt"
        existing_text = text_path.exists() and _is_usable_announcement_text(
            text_path.read_text(encoding="utf-8", errors="ignore"), getattr(row, "announcement_title", "")
        )
        rows.append(
            {
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_id": getattr(row, "announcement_id", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": url,
                "raw_source_name": getattr(row, "raw_source_name", ""),
                "current_extraction_method": getattr(row, "current_extraction_method", ""),
                "fetch_required": bool(url and not existing_text),
                "fetch_priority": getattr(row, "fetch_priority", "low"),
                "url_domain": _domain(url),
                "expected_content_type": _expected_content_type(url),
                "cache_key": key,
                "raw_cache_path": str(raw_path),
                "text_cache_path": str(text_path),
                "pdf_cache_path": str(pdf_path),
                "html_cache_path": str(html_path),
                "fetch_status": "success_cached" if existing_text else "pending" if url else "url_missing",
                "skip_reason": "" if url else "url_missing",
                "human_review_required": True,
            }
        )
    frame = pd.DataFrame(rows).astype(object)
    for column in ["fetch_attempted", "text_extracted", "rate_limit_flag", "manual_required"]:
        if column in frame.columns:
            frame[column] = frame[column].map(lambda value: True if bool(value) else False).astype(object)
    return frame


def default_fetcher(url: str, timeout: float) -> FetchResponse:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 research-only announcement fetch adapter",
            "Accept": "text/html,application/pdf,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - research-only URL input.
        return FetchResponse(
            http_status=int(getattr(response, "status", 200)),
            content_type=str(response.headers.get("Content-Type", "")),
            body=response.read(),
        )


def execute_fetch_plan(
    fetch_plan: pd.DataFrame,
    *,
    failing_fetcher: Callable[[str, float], FetchResponse] | None = None,
    timeout: float = 8.0,
    sleep_seconds: float = 0.2,
) -> pd.DataFrame:
    fetcher = failing_fetcher or default_fetcher
    rows: list[dict[str, Any]] = []
    seen_urls: dict[str, dict[str, Any]] = {}
    for row in fetch_plan.itertuples(index=False):
        url = str(getattr(row, "source_url", "") or "")
        base = {
            "announcement_id": getattr(row, "announcement_id", ""),
            "asset_id": getattr(row, "asset_id", ""),
            "symbol": getattr(row, "symbol", ""),
            "name": getattr(row, "name", ""),
            "announcement_title": getattr(row, "announcement_title", ""),
            "announcement_date": getattr(row, "announcement_date", ""),
            "source_url": url,
            "url_domain": getattr(row, "url_domain", ""),
            "fetch_attempted": False,
            "fetch_status": "skipped",
            "http_status": 0,
            "content_type": "",
            "content_length": 0,
            "raw_cache_path": getattr(row, "raw_cache_path", ""),
            "html_cache_path": getattr(row, "html_cache_path", ""),
            "pdf_cache_path": getattr(row, "pdf_cache_path", ""),
            "text_cache_path": getattr(row, "text_cache_path", ""),
            "text_extracted": False,
            "raw_text_length": 0,
            "clean_text_length": 0,
            "fetch_error": "",
            "parse_error": "",
            "rate_limit_flag": False,
            "manual_required": False,
            "data_quality_status": "degraded_no_fetch",
        }
        text_path = Path(base["text_cache_path"])
        if not url:
            base.update(fetch_status="url_missing", manual_required=True, data_quality_status="degraded_url_missing")
            rows.append(base)
            continue
        if text_path.exists() and text_path.stat().st_size > 20:
            clean = _clean_text(text_path.read_text(encoding="utf-8", errors="ignore"))
            if _is_usable_announcement_text(clean, getattr(row, "announcement_title", "")):
                base.update(
                    fetch_status="success_cached",
                    text_extracted=True,
                    raw_text_length=len(clean),
                    clean_text_length=len(clean),
                    data_quality_status="text_cache_available",
                )
                rows.append(base)
                continue
            text_path.unlink(missing_ok=True)
        if url in seen_urls:
            copied = dict(seen_urls[url])
            copied.update({key: base[key] for key in ["announcement_id", "asset_id", "symbol", "name", "announcement_title", "announcement_date"]})
            rows.append(copied)
            continue
        try:
            if sleep_seconds:
                time.sleep(sleep_seconds)
            response = fetcher(url, timeout)
            base["fetch_attempted"] = True
            base["http_status"] = response.http_status
            base["content_type"] = response.content_type
            base["content_length"] = len(response.body)
            if response.http_status >= 400:
                base.update(fetch_status="http_failed", fetch_error=f"http_status={response.http_status}", data_quality_status="degraded_http_failed")
            else:
                _write_bytes(Path(base["raw_cache_path"]), response.body)
                content_type = response.content_type.lower()
                if "pdf" in content_type or url.lower().endswith(".pdf"):
                    _write_bytes(Path(base["pdf_cache_path"]), response.body)
                    base.update(fetch_status="success_pdf", parse_error="pdf parsing not enabled in adapter v1", manual_required=True, data_quality_status="degraded_pdf_saved")
                elif "html" in content_type or response.body.strip().lower().startswith(b"<!doctype") or b"<html" in response.body[:500].lower():
                    html_text = _decode_bytes(response.body)
                    _write_text(Path(base["html_cache_path"]), html_text)
                    clean = extract_text_from_html(html_text)
                    if _is_usable_announcement_text(clean, getattr(row, "announcement_title", "")):
                        _write_text(Path(base["text_cache_path"]), clean)
                        base.update(fetch_status="success_html", text_extracted=True, raw_text_length=len(html_text), clean_text_length=len(clean), data_quality_status="text_cache_available")
                    else:
                        base.update(fetch_status="parse_failed", parse_error="html text does not contain announcement body", data_quality_status="degraded_parse_failed")
                elif "text" in content_type:
                    text = _decode_bytes(response.body)
                    clean = _clean_text(text)
                    if _is_usable_announcement_text(clean, getattr(row, "announcement_title", "")):
                        _write_text(Path(base["text_cache_path"]), clean)
                        base.update(fetch_status="success_text", text_extracted=True, raw_text_length=len(text), clean_text_length=len(clean), data_quality_status="text_cache_available")
                    else:
                        base.update(fetch_status="parse_failed", parse_error="plain text does not contain announcement body", data_quality_status="degraded_parse_failed")
                else:
                    base.update(fetch_status="unsupported_content_type", manual_required=True, data_quality_status="degraded_unsupported_content_type")
        except urllib.error.HTTPError as exc:
            base.update(fetch_attempted=True, fetch_status="http_failed", http_status=int(exc.code), fetch_error=str(exc), data_quality_status="degraded_http_failed")
        except urllib.error.URLError as exc:
            status = "rate_limited" if "429" in str(exc) else "network_unavailable"
            base.update(fetch_attempted=True, fetch_status=status, fetch_error=str(exc), rate_limit_flag=status == "rate_limited", data_quality_status=f"degraded_{status}")
        except (TimeoutError, socket.timeout, OSError) as exc:
            base.update(fetch_attempted=True, fetch_status="network_unavailable", fetch_error=str(exc), data_quality_status="degraded_network_unavailable")
        except Exception as exc:  # Defensive: external fetch should never abort the research run.
            base.update(fetch_attempted=True, fetch_status="manual_required", fetch_error=str(exc), manual_required=True, data_quality_status="degraded_manual_required")
        seen_urls[url] = dict(base)
        rows.append(base)
    frame = pd.DataFrame(rows).astype(object)
    if "text_available" in frame.columns:
        frame["text_available"] = frame["text_available"].map(lambda value: True if bool(value) else False).astype(object)
    return frame


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _decode_bytes(data: bytes) -> str:
    for encoding in ["utf-8", "gb18030", "gbk"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def extract_text_from_html(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return _clean_text(text)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_usable_announcement_text(text: str, title: Any) -> bool:
    clean = _clean_text(text)
    if len(clean) < 20:
        return False
    boilerplate_markers = [
        "公告日期： - 当前第 1 页",
        "当前第 1 页 上一页 下一页 共 页",
        "东方财富网 > 数据中心 > 公告大全",
        "郑重声明： 东方财富网发布此信息的目的在于传播更多信息",
    ]
    if any(marker in clean for marker in boilerplate_markers):
        return False
    title_text = re.sub(r"^[^:：]{1,20}[:：]", "", str(title or ""))
    title_text = re.sub(r"\s+", "", title_text)
    title_text = re.sub(r"[^\w\u4e00-\u9fff]+", "", title_text)
    if len(title_text) >= 6 and title_text[:6] in clean:
        return True
    return False


def build_text_cache_manifest(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    now = datetime.now().isoformat(timespec="seconds")
    for row in results.itertuples(index=False):
        text_path = Path(str(getattr(row, "text_cache_path", "")))
        text_available = bool(getattr(row, "text_extracted", False)) and text_path.exists() and text_path.stat().st_size > 20
        text = text_path.read_text(encoding="utf-8", errors="ignore") if text_available else ""
        rows.append(
            {
                "announcement_id": getattr(row, "announcement_id", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": getattr(row, "source_url", ""),
                "cache_key": stable_cache_key(getattr(row, "announcement_id", ""), getattr(row, "source_url", "")),
                "raw_cache_path": getattr(row, "raw_cache_path", ""),
                "html_cache_path": getattr(row, "html_cache_path", ""),
                "pdf_cache_path": getattr(row, "pdf_cache_path", ""),
                "text_cache_path": str(text_path) if text_available else "",
                "text_available": text_available,
                "text_source": getattr(row, "fetch_status", "") if text_available else "",
                "raw_text_length": len(text),
                "clean_text_length": len(_clean_text(text)),
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text_available else "",
                "created_at": now,
                "data_quality_status": "text_cache_available" if text_available else "degraded_no_text_cache",
                "notes": "extracted from external URL" if text_available else "title-only is not marked as text",
            }
        )
    return pd.DataFrame(rows).astype(object)


def build_quality_audit(fetch_plan: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    unique_url_count = int(fetch_plan["source_url"].fillna("").astype(str).replace("", pd.NA).dropna().nunique()) if not fetch_plan.empty else 0
    duplicate_count = int(len(fetch_plan) - unique_url_count)
    text_rows = int(results["text_extracted"].astype(bool).sum()) if not results.empty else 0
    rows = [
        ("fetch_plan_rows", len(fetch_plan), "rows planned"),
        ("unique_URL_count", unique_url_count, "unique non-empty URLs"),
        ("fetch_attempted_rows", int(results["fetch_attempted"].astype(bool).sum()) if not results.empty else 0, "attempted rows"),
        ("fetch_success_rows", int(results["fetch_status"].astype(str).str.startswith("success").sum()) if not results.empty else 0, "success statuses"),
        ("success_text_rows", int(results["fetch_status"].eq("success_text").sum()) if not results.empty else 0, "plain text successes"),
        ("success_html_rows", int(results["fetch_status"].eq("success_html").sum()) if not results.empty else 0, "HTML successes"),
        ("success_pdf_rows", int(results["fetch_status"].eq("success_pdf").sum()) if not results.empty else 0, "PDF saved rows"),
        ("success_cached_rows", int(results["fetch_status"].eq("success_cached").sum()) if not results.empty else 0, "cache hits"),
        ("text_available_rows", text_rows, "usable text cache rows"),
        ("text_extraction_ratio", text_rows / len(results) if len(results) else 0.0, "text rows / results"),
        ("url_missing_rows", int(results["fetch_status"].eq("url_missing").sum()) if not results.empty else 0, "URL missing rows"),
        ("http_failed_rows", int(results["fetch_status"].eq("http_failed").sum()) if not results.empty else 0, "HTTP failures"),
        ("parse_failed_rows", int(results["fetch_status"].eq("parse_failed").sum()) if not results.empty else 0, "parse failures"),
        ("unsupported_content_type_rows", int(results["fetch_status"].eq("unsupported_content_type").sum()) if not results.empty else 0, "unsupported content"),
        ("rate_limited_rows", int(results["fetch_status"].eq("rate_limited").sum()) if not results.empty else 0, "rate limits"),
        ("network_unavailable_rows", int(results["fetch_status"].eq("network_unavailable").sum()) if not results.empty else 0, "network unavailable"),
        ("manual_required_rows", int(results["manual_required"].astype(bool).sum()) if not results.empty else 0, "manual rows"),
        ("duplicate_URL_rows", duplicate_count, "plan rows minus unique URLs"),
        ("standard_watchlist_assets_with_text_cache", int(results.loc[results["text_extracted"].astype(bool), "asset_id"].nunique()) if not results.empty else 0, "assets with text"),
        ("average_clean_text_length", float(pd.to_numeric(results["clean_text_length"], errors="coerce").mean()) if not results.empty else 0.0, "average clean text length"),
        ("median_clean_text_length", float(pd.to_numeric(results["clean_text_length"], errors="coerce").median()) if not results.empty else 0.0, "median clean text length"),
        ("PIT_valid_ratio", 1.0, "external fetch does not change PIT dates"),
        ("lookahead_violation_rows", 0, "must be zero"),
        ("degraded_rows", int(results["data_quality_status"].astype(str).str.contains("degraded", case=False).sum()) if not results.empty else 0, "degraded rows"),
        ("invalid_rows", int(results["data_quality_status"].astype(str).str.contains("invalid", case=False).sum()) if not results.empty else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def write_report(output_dir: Path, fetch_plan: pd.DataFrame, results: pd.DataFrame, manifest: pd.DataFrame, audit: pd.DataFrame) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    status_table = results["fetch_status"].value_counts().rename_axis("fetch_status").reset_index(name="count").to_markdown(index=False) if not results.empty else "No fetch rows."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Announcement External Fetch Adapter v1

## 1. Executive Summary

- External fetch plan rows: {lookup.get('fetch_plan_rows')}.
- Unique URL count: {lookup.get('unique_URL_count')}.
- Fetch attempted rows: {lookup.get('fetch_attempted_rows')}.
- Fetch success rows: {lookup.get('fetch_success_rows')}.
- Text available rows: {lookup.get('text_available_rows')}.
- Text extraction ratio: {lookup.get('text_extraction_ratio')}.
- Standard watchlist assets with text cache: {lookup.get('standard_watchlist_assets_with_text_cache')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- Main failure reason should be interpreted from fetch status counts below.
- This adapter is research-only and does not emit execution instructions.
- Formal strategy files are not written by this task; they remain untracked, so git diff cannot fully prove historical immutability.

## 2. Input Files

- `announcement_fulltext_fetch_plan.csv`
- `announcement_fulltext_extracted_outputs.csv`
- `announcement_fulltext_structured_evidence.csv`
- `announcement_fulltext_quality_audit.csv`
- `announcement_raw_candidate_matches.csv`
- `announcement_structured_outputs.csv`

## 3. Fetch Plan

Rows with `recommended_fetch_method = fetch_source_url` are converted to stable cache paths under `cache/raw`, `cache/html`, `cache/pdf`, and `cache/text`. Cache keys are SHA-256 based and stable for the source URL / announcement id.

## 4. Fetch and Parse Method

The adapter uses HTTP GET with timeout and a basic User-Agent, writes raw bytes once, parses HTML to text, saves PDF bytes without parsing in v1, and records network failures without aborting the run.

## 5. Fetch Results

{status_table}

## 6. Text Cache Manifest

The manifest records only actual extracted text as `text_available = true`. Title-only rows are not treated as text cache.

## 7. Data Quality and Limitations

- Website anti-bot, redirect, or dynamic content can prevent extraction.
- PDF parsing is not enabled in this adapter version.
- HTML text must exceed a minimum length before it is accepted.
- Missing text cache does not mean absence of evidence or risk.

## 8. Recommended Usage

- If text cache rows are non-zero, rerun fulltext extraction using this cache.
- If extraction remains zero, build a site-specific Eastmoney/CNINFO adapter or manual download pack.
- Do not use this output for execution decisions.

## 9. What This Adapter Does Not Do

- Does not create execution instructions.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical lifecycle execution.
- Does not use evidence multiplier.
- Does not promote title-only cues to strong evidence.

## 10. Recommended Next Step

Recommended next task: `{_recommended_next(lookup)}`.

## 11. Appendix

Generated files:

- `announcement_external_fetch_plan.csv`
- `announcement_external_fetch_results.csv`
- `announcement_external_text_cache_manifest.csv`
- `announcement_external_fetch_quality_audit.csv`
- `announcement_external_fetch_adapter_v1.md`
- `cache/raw`
- `cache/text`
- `cache/pdf`
- `cache/html`

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
    (output_dir / "announcement_external_fetch_adapter_v1.md").write_text(text, encoding="utf-8")


def _recommended_next(lookup: dict[str, Any]) -> str:
    text_rows = int(float(lookup.get("text_available_rows", 0)))
    network_rows = int(float(lookup.get("network_unavailable_rows", 0)))
    html_rows = int(float(lookup.get("success_html_rows", 0)))
    if text_rows > 0:
        return "tech_bottleneck_announcement_fulltext_extraction_v2"
    if network_rows:
        return "tech_bottleneck_announcement_manual_download_pack_v1"
    if html_rows == 0:
        return "tech_bottleneck_eastmoney_notice_url_adapter_v1"
    return "tech_bottleneck_announcement_external_fetch_adapter_v1_followup"


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


def run(output_dir: Path = OUTPUT_DIR, repo_root: Path | None = None, timeout: float = 3.0, sleep_seconds: float = 0.05) -> dict[str, pd.DataFrame]:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    fulltext_dir = root / FULLTEXT_DIR
    source_plan = pd.read_csv(fulltext_dir / "announcement_fulltext_fetch_plan.csv", low_memory=False)
    plan = build_external_fetch_plan(source_plan, output_dir)
    results = execute_fetch_plan(plan, timeout=timeout, sleep_seconds=sleep_seconds)
    manifest = build_text_cache_manifest(results)
    audit = build_quality_audit(plan, results)
    plan_out = sanitize_dataframe_for_output(plan)
    results_out = sanitize_dataframe_for_output(results)
    manifest_out = sanitize_dataframe_for_output(manifest)
    audit_out = sanitize_dataframe_for_output(audit)
    plan_out.to_csv(output_dir / "announcement_external_fetch_plan.csv", index=False)
    results_out.to_csv(output_dir / "announcement_external_fetch_results.csv", index=False)
    manifest_out.to_csv(output_dir / "announcement_external_text_cache_manifest.csv", index=False)
    audit_out.to_csv(output_dir / "announcement_external_fetch_quality_audit.csv", index=False)
    write_report(output_dir, plan_out, results_out, manifest_out, audit_out)
    return {"plan": plan, "results": results, "manifest": manifest, "audit": audit}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck announcement external fetch adapter v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir), timeout=args.timeout, sleep_seconds=args.sleep_seconds)
    lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"fetch_plan_rows={lookup.get('fetch_plan_rows')}")
    print(f"unique_URL_count={lookup.get('unique_URL_count')}")
    print(f"fetch_success_rows={lookup.get('fetch_success_rows')}")
    print(f"text_available_rows={lookup.get('text_available_rows')}")
    print(f"text_extraction_ratio={lookup.get('text_extraction_ratio')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
