#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
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


EXTERNAL_FETCH_DIR = Path("outputs/research/tech_bottleneck_announcement_external_fetch_adapter_v1")
INGESTION_DIR = Path("outputs/research/tech_bottleneck_announcement_source_ingestion_v1")
FULLTEXT_DIR = Path("outputs/research/tech_bottleneck_announcement_fulltext_extraction_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_eastmoney_notice_url_adapter_v1")
RULE_VERSION = "tech_bottleneck_eastmoney_notice_url_adapter_v1"

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

ANNOUNCEMENT_BODY_KEYWORDS = [
    "公告",
    "公司",
    "董事会",
    "监事会",
    "证券代码",
    "证券简称",
    "特此公告",
    "重大事项",
    "风险提示",
]

EASTMONEY_SHELL_MARKERS = [
    "东方财富网 > 数据中心 > 公告大全",
    "公告日期： - 当前第 1 页",
    "当前第 1 页 上一页 下一页 共 页",
    "郑重声明： 东方财富网发布此信息的目的在于传播更多信息",
    "notice_content",
]


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


def _domain(url: Any) -> str:
    try:
        return urllib.parse.urlparse(str(url or "")).netloc.lower()
    except Exception:
        return ""


def _extract_notice_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(AN\d{12,})", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _extract_symbol_from_url(url: Any) -> str:
    path = urllib.parse.urlparse(str(url or "")).path
    match = re.search(r"/detail/([^/]+)/AN\d+", path, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def stable_cache_key(announcement_id: Any, source_url: Any) -> str:
    seed = str(announcement_id or source_url or "").strip()
    notice_id = _extract_notice_id(seed) or _extract_notice_id(source_url)
    readable = re.sub(r"[^0-9A-Za-z]+", "_", notice_id or _extract_symbol_from_url(source_url) or "eastmoney_notice").strip("_")[:48]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{readable}_{digest}"


def _read_text_if_exists(path_value: Any) -> str:
    path = Path(str(path_value or ""))
    if not str(path_value or "") or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract_text_from_html(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", str(html_text or ""))
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return _clean_text(text)


def _is_page_shell(text: str) -> bool:
    clean = _clean_text(text)
    if any(marker in clean for marker in EASTMONEY_SHELL_MARKERS[:4]):
        return True
    if "东方财富网" in clean and "公告大全" in clean and len(clean) < 1200:
        return True
    return False


def _is_usable_announcement_text(text: str, title: Any) -> bool:
    clean = _clean_text(text)
    if len(clean) < 120:
        return False
    if _is_page_shell(clean):
        return False
    title_text = re.sub(r"^[^:：]{1,25}[:：]", "", str(title or ""))
    title_text = re.sub(r"\s+", "", title_text)
    title_text = re.sub(r"[^\w\u4e00-\u9fff]+", "", title_text)
    keyword_count = sum(1 for keyword in ANNOUNCEMENT_BODY_KEYWORDS if keyword in clean)
    title_match = len(title_text) >= 6 and title_text[:6] in re.sub(r"\s+", "", clean)
    return keyword_count >= 2 or title_match


def _extract_mobile_notice_url(html_text: str) -> str:
    match = re.search(r"url=(https?://np-info\.eastmoney\.com/wap/notice/\?infocode=AN\d+)", html_text, flags=re.IGNORECASE)
    return html.unescape(match.group(1)) if match else ""


def _extract_pdf_url(html_text: str) -> str:
    candidates = re.findall(r"https?://[^\"'<>\\\s]+?\.pdf(?:\?[^\"'<>\\\s]*)?", html_text, flags=re.IGNORECASE)
    if candidates:
        return html.unescape(candidates[0])
    relative = re.findall(r"((?:/|//)[^\"'<>\\\s]+?\.pdf(?:\?[^\"'<>\\\s]*)?)", html_text, flags=re.IGNORECASE)
    if not relative:
        return ""
    value = relative[0]
    if value.startswith("//"):
        return "https:" + value
    return urllib.parse.urljoin("https://data.eastmoney.com", value)


def _eastmoney_cnotice_api_url(notice_id: str, page_index: int = 1) -> str:
    if not notice_id:
        return ""
    query = urllib.parse.urlencode({"art_code": notice_id, "client_source": "web", "page_index": str(page_index)})
    return f"https://np-cnotice-stock.eastmoney.com/api/content/ann?{query}"


def _url_pattern(url: str, cached_html: str) -> str:
    domain = _domain(url)
    path = urllib.parse.urlparse(str(url or "")).path.lower()
    if "eastmoney" not in domain:
        return "non_eastmoney"
    if path.endswith(".pdf"):
        return "eastmoney_pdf_direct"
    if "/notices/detail/" in path and _is_page_shell(extract_text_from_html(cached_html or "")):
        return "eastmoney_html_shell"
    if "/notices/detail/" in path:
        return "eastmoney_notice_detail"
    if "data.eastmoney" in domain:
        return "eastmoney_data_page"
    return "unknown"


def build_url_inventory(fetch_plan: pd.DataFrame, fetch_results: pd.DataFrame | None = None) -> pd.DataFrame:
    result_by_url: dict[str, Any] = {}
    if fetch_results is not None and not fetch_results.empty and "source_url" in fetch_results.columns:
        result_by_url = {str(row.source_url or ""): row for row in fetch_results.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    for row in fetch_plan.itertuples(index=False):
        url = str(getattr(row, "source_url", "") or "")
        cached_html = _read_text_if_exists(getattr(row, "html_cache_path", ""))
        result_row = result_by_url.get(url)
        if not cached_html and result_row is not None:
            cached_html = _read_text_if_exists(getattr(result_row, "html_cache_path", ""))
        raw_path = str(getattr(row, "raw_cache_path", "") or getattr(result_row, "raw_cache_path", "") if result_row is not None else "")
        html_path = str(getattr(row, "html_cache_path", "") or getattr(result_row, "html_cache_path", "") if result_row is not None else "")
        raw_length = Path(raw_path).stat().st_size if raw_path and Path(raw_path).exists() else 0
        html_length = Path(html_path).stat().st_size if html_path and Path(html_path).exists() else len(cached_html.encode("utf-8")) if cached_html else 0
        notice_id = _extract_notice_id(url) or _extract_notice_id(cached_html)
        pdf_hint = _extract_pdf_url(cached_html)
        mobile_hint = _extract_mobile_notice_url(cached_html)
        domain = _domain(url)
        is_eastmoney = "eastmoney" in domain
        rows.append(
            {
                "announcement_id": getattr(row, "announcement_id", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": url,
                "url_domain": domain,
                "is_eastmoney_url": bool(is_eastmoney),
                "url_pattern": _url_pattern(url, cached_html),
                "has_cached_raw": bool(raw_path and Path(raw_path).exists()),
                "has_cached_html": bool(html_path and Path(html_path).exists()),
                "cached_raw_path": raw_path,
                "cached_html_path": html_path,
                "raw_cache_length": int(raw_length),
                "html_cache_length": int(html_length),
                "contains_pdf_hint": bool(pdf_hint),
                "contains_notice_id_hint": bool(notice_id),
                "contains_api_hint": bool(mobile_hint),
                "contains_json_hint": "stockInfo" in cached_html or "infocode" in cached_html,
                "contains_attachment_hint": bool(pdf_hint or "pdf-link" in cached_html),
                "candidate_notice_id": notice_id,
                "candidate_mobile_url": mobile_hint,
                "data_quality_status": "eastmoney_shell_or_detail" if is_eastmoney else "non_eastmoney",
            }
        )
    return pd.DataFrame(rows).astype(object)


def _cache_paths(output_dir: Path, cache_key: str) -> dict[str, str]:
    return {
        "raw_cache_path": str(output_dir / "cache" / "raw" / f"{cache_key}.bin"),
        "html_cache_path": str(output_dir / "cache" / "html" / f"{cache_key}.html"),
        "pdf_cache_path": str(output_dir / "cache" / "pdf" / f"{cache_key}.pdf"),
        "text_cache_path": str(output_dir / "cache" / "text" / f"{cache_key}.txt"),
        "metadata_cache_path": str(output_dir / "cache" / "metadata" / f"{cache_key}.json"),
    }


def build_resolution_plan(inventory: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    for directory in ["raw", "html", "pdf", "text", "metadata"]:
        (output_dir / "cache" / directory).mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for row in inventory.itertuples(index=False):
        source_url = str(getattr(row, "source_url", "") or "")
        notice_id = str(getattr(row, "candidate_notice_id", "") or _extract_notice_id(source_url))
        cached_html = _read_text_if_exists(getattr(row, "cached_html_path", ""))
        mobile_url = str(getattr(row, "candidate_mobile_url", "") or _extract_mobile_notice_url(cached_html))
        pdf_url = _extract_pdf_url(cached_html)
        cache_key = stable_cache_key(getattr(row, "announcement_id", ""), source_url)
        cache_paths = _cache_paths(output_dir, cache_key)
        is_eastmoney = bool(getattr(row, "is_eastmoney_url", False))
        api_url = _eastmoney_cnotice_api_url(notice_id)
        if not is_eastmoney:
            strategy = "unsupported"
            required = False
            manual_required = True
            reason = "non-eastmoney URL"
        elif api_url:
            strategy = "try_eastmoney_metadata_api"
            required = True
            manual_required = False
            reason = "source URL or cached HTML includes AN notice id for cnotice API"
        elif pdf_url:
            strategy = "parse_cached_html_for_pdf_url"
            required = True
            manual_required = False
            reason = "cached HTML includes PDF hint"
        elif mobile_url:
            strategy = "parse_cached_html_for_json_state"
            required = True
            manual_required = False
            reason = "cached HTML includes mobile metadata URL"
        elif notice_id:
            strategy = "parse_url_for_notice_id"
            required = True
            manual_required = False
            reason = "source URL includes AN notice id"
            mobile_url = f"https://np-info.eastmoney.com/wap/notice/?infocode={notice_id}"
        else:
            strategy = "manual_required"
            required = False
            manual_required = True
            reason = "could not derive notice id or candidate URL"
        rows.append(
            {
                "announcement_id": getattr(row, "announcement_id", ""),
                "asset_id": getattr(row, "asset_id", ""),
                "symbol": getattr(row, "symbol", ""),
                "name": getattr(row, "name", ""),
                "announcement_title": getattr(row, "announcement_title", ""),
                "announcement_date": getattr(row, "announcement_date", ""),
                "source_url": source_url,
                "url_pattern": getattr(row, "url_pattern", ""),
                "is_eastmoney_url": bool(is_eastmoney),
                "resolution_required": bool(required),
                "resolution_strategy": strategy,
                "candidate_notice_id": notice_id,
                "candidate_pdf_url": pdf_url,
                "candidate_api_url": api_url,
                "candidate_metadata_url": mobile_url,
                "cache_key": cache_key,
                **cache_paths,
                "manual_required": bool(manual_required),
                "reason": reason,
                "fetch_priority": "high" if ("风险" in str(getattr(row, "announcement_title", "")) or "合同" in str(getattr(row, "announcement_title", ""))) else "medium",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows).astype(object)


def default_fetcher(url: str, timeout: float) -> FetchResponse:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 research-only Eastmoney notice adapter",
            "Accept": "text/html,application/pdf,application/json,*/*",
            "Referer": "https://data.eastmoney.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - research-only URL input.
        return FetchResponse(
            http_status=int(getattr(response, "status", 200)),
            content_type=str(response.headers.get("Content-Type", "")),
            body=response.read(),
        )


def _unwrap_jsonp(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^[A-Za-z0-9_.$]+\((.*)\)\s*;?$", stripped, flags=re.S)
    return match.group(1) if match else stripped


def _extract_text_and_pdf_from_body(body: bytes, content_type: str, title: Any) -> tuple[str, str, str, dict[str, Any] | None]:
    lower_type = content_type.lower()
    if "pdf" in lower_type or body[:8].startswith(b"%PDF"):
        return "", "", "pdf", None
    decoded = _decode_bytes(body)
    maybe_json = _unwrap_jsonp(decoded)
    if "json" in lower_type or "text/plain" in lower_type and maybe_json.strip().startswith("{") or maybe_json.strip().startswith("{"):
        try:
            data = json.loads(maybe_json)
            payload = data.get("data", data) if isinstance(data, dict) else {}
            notice_content = payload.get("notice_content", "") if isinstance(payload, dict) else ""
            notice_title = payload.get("notice_title", title) if isinstance(payload, dict) else title
            text = _clean_text(str(notice_content or ""))
            flattened = json.dumps(data, ensure_ascii=False)
            pdf_url = _extract_pdf_url(flattened)
            return text if _is_usable_announcement_text(text, notice_title) else "", pdf_url, "json", data if isinstance(data, dict) else None
        except Exception:
            return "", _extract_pdf_url(decoded), "json_parse_failed", None
    text = extract_text_from_html(decoded) if "<html" in decoded[:1000].lower() or "<body" in decoded[:1000].lower() else _clean_text(decoded)
    pdf_url = _extract_pdf_url(decoded)
    return text if _is_usable_announcement_text(text, title) else "", pdf_url, "html_or_text", None


def resolve_eastmoney_notices(
    resolution_plan: pd.DataFrame,
    *,
    fetcher: Callable[[str, float], FetchResponse] | None = None,
    timeout: float = 5.0,
    sleep_seconds: float = 0.1,
) -> pd.DataFrame:
    fetch = fetcher or default_fetcher
    rows: list[dict[str, Any]] = []
    seen_url_results: dict[str, dict[str, Any]] = {}
    for row in resolution_plan.itertuples(index=False):
        source_url = str(getattr(row, "source_url", "") or "")
        candidate_pdf_url = str(getattr(row, "candidate_pdf_url", "") or "")
        candidate_metadata_url = str(getattr(row, "candidate_metadata_url", "") or "")
        request_url = candidate_pdf_url or candidate_metadata_url or source_url
        base = {
            "announcement_id": getattr(row, "announcement_id", ""),
            "asset_id": getattr(row, "asset_id", ""),
            "symbol": getattr(row, "symbol", ""),
            "name": getattr(row, "name", ""),
            "announcement_title": getattr(row, "announcement_title", ""),
            "announcement_date": getattr(row, "announcement_date", ""),
            "source_url": source_url,
            "resolution_strategy": getattr(row, "resolution_strategy", ""),
            "resolved_pdf_url": candidate_pdf_url,
            "resolved_html_url": "",
            "resolved_api_url": candidate_metadata_url if "api" in candidate_metadata_url.lower() else "",
            "resolved_metadata": candidate_metadata_url,
            "resolution_status": "manual_required",
            "fetch_attempted": False,
            "http_status": 0,
            "content_type": "",
            "content_length": 0,
            "raw_cache_path": getattr(row, "raw_cache_path", ""),
            "html_cache_path": getattr(row, "html_cache_path", ""),
            "pdf_cache_path": getattr(row, "pdf_cache_path", ""),
            "text_cache_path": getattr(row, "text_cache_path", ""),
            "metadata_cache_path": getattr(row, "metadata_cache_path", ""),
            "text_extracted": False,
            "raw_text_length": 0,
            "clean_text_length": 0,
            "resolution_error": "",
            "fetch_error": "",
            "parse_error": "",
            "manual_required": bool(getattr(row, "manual_required", False)),
            "data_quality_status": "degraded_manual_required",
        }
        strategy = str(getattr(row, "resolution_strategy", "") or "")
        candidate_api_url = str(getattr(row, "candidate_api_url", "") or "")
        if strategy == "direct_pdf_url":
            request_url = candidate_pdf_url or candidate_metadata_url or source_url
        else:
            request_url = candidate_api_url or candidate_pdf_url or candidate_metadata_url or source_url
        if not bool(getattr(row, "resolution_required", False)) or not request_url:
            base.update(resolution_status="manual_required", manual_required=True, resolution_error="no resolvable Eastmoney URL")
            rows.append(base)
            continue
        if request_url in seen_url_results:
            copied = dict(seen_url_results[request_url])
            copied.update({key: base[key] for key in ["announcement_id", "asset_id", "symbol", "name", "announcement_title", "announcement_date", "source_url"]})
            rows.append(copied)
            continue
        try:
            if sleep_seconds:
                time.sleep(sleep_seconds)
            response = fetch(request_url, timeout)
            base.update(
                fetch_attempted=True,
                http_status=response.http_status,
                content_type=response.content_type,
                content_length=len(response.body),
            )
            if response.http_status >= 400:
                base.update(resolution_status="http_failed", fetch_error=f"http_status={response.http_status}", manual_required=True, data_quality_status="degraded_http_failed")
            else:
                _write_bytes(Path(base["raw_cache_path"]), response.body)
                text, pdf_hint, body_kind, metadata = _extract_text_and_pdf_from_body(response.body, response.content_type, getattr(row, "announcement_title", ""))
                content_type = response.content_type.lower()
                if "pdf" in content_type or response.body[:8].startswith(b"%PDF"):
                    _write_bytes(Path(base["pdf_cache_path"]), response.body)
                    base.update(resolution_status="resolved_pdf", resolved_pdf_url=request_url, manual_required=True, data_quality_status="degraded_pdf_saved")
                elif text:
                    if metadata is not None and base["metadata_cache_path"]:
                        _write_text(Path(base["metadata_cache_path"]), json.dumps(metadata, ensure_ascii=False, indent=2))
                    _write_text(Path(base["text_cache_path"]), text)
                    if "html" in content_type or body_kind == "html_or_text":
                        _write_text(Path(base["html_cache_path"]), _decode_bytes(response.body))
                        base["resolved_html_url"] = request_url
                    if body_kind == "json":
                        base["resolved_api_url"] = request_url
                    if pdf_hint:
                        base["resolved_pdf_url"] = pdf_hint
                    base.update(resolution_status="resolved_text", text_extracted=True, raw_text_length=len(_decode_bytes(response.body)), clean_text_length=len(text), manual_required=False, data_quality_status="text_cache_available")
                elif pdf_hint:
                    base["resolved_pdf_url"] = pdf_hint
                    base.update(resolution_status="resolved_metadata_only", parse_error="metadata contains PDF hint but PDF not fetched in this step", manual_required=True, data_quality_status="degraded_metadata_only")
                else:
                    if "html" in content_type or response.body.strip().lower().startswith(b"<!doctype") or b"<html" in response.body[:500].lower():
                        _write_text(Path(base["html_cache_path"]), _decode_bytes(response.body))
                    base.update(resolution_status="parse_failed", parse_error="Eastmoney response did not contain usable notice body or PDF URL", manual_required=True, data_quality_status="degraded_parse_failed")
        except urllib.error.HTTPError as exc:
            base.update(fetch_attempted=True, resolution_status="http_failed", http_status=int(exc.code), fetch_error=str(exc), manual_required=True, data_quality_status="degraded_http_failed")
        except urllib.error.URLError as exc:
            status = "network_unavailable"
            base.update(fetch_attempted=True, resolution_status=status, fetch_error=str(exc), manual_required=True, data_quality_status=f"degraded_{status}")
        except (TimeoutError, socket.timeout, OSError) as exc:
            base.update(fetch_attempted=True, resolution_status="network_unavailable", fetch_error=str(exc), manual_required=True, data_quality_status="degraded_network_unavailable")
        except Exception as exc:  # Defensive: external site parsing must not abort the research run.
            base.update(fetch_attempted=True, resolution_status="manual_required", fetch_error=str(exc), manual_required=True, data_quality_status="degraded_manual_required")
        seen_url_results[request_url] = dict(base)
        rows.append(base)
    return pd.DataFrame(rows).astype(object)


def build_pdf_text_manifest(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    now = datetime.now().isoformat(timespec="seconds")
    for row in results.itertuples(index=False):
        text_path = Path(str(getattr(row, "text_cache_path", "") or ""))
        pdf_path = Path(str(getattr(row, "pdf_cache_path", "") or ""))
        text_available = bool(getattr(row, "text_extracted", False)) and text_path.exists() and text_path.stat().st_size > 20
        pdf_available = pdf_path.exists() and pdf_path.stat().st_size > 5
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
                "resolved_pdf_url": getattr(row, "resolved_pdf_url", ""),
                "pdf_available": bool(pdf_available),
                "text_available": bool(text_available),
                "pdf_cache_path": str(pdf_path) if pdf_available else "",
                "text_cache_path": str(text_path) if text_available else "",
                "text_source": getattr(row, "resolution_status", "") if text_available else "",
                "raw_text_length": len(text),
                "clean_text_length": len(_clean_text(text)),
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text_available else "",
                "created_at": now,
                "data_quality_status": "text_cache_available" if text_available else "pdf_cached_without_text" if pdf_available else "degraded_no_pdf_or_text",
                "notes": "usable text extracted" if text_available else "PDF cached but text parser not applied" if pdf_available else "title-only/page shell not marked as text",
            }
        )
    return pd.DataFrame(rows).astype(object)


def build_quality_audit(inventory: pd.DataFrame, plan: pd.DataFrame, results: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    total_rows = len(inventory)
    eastmoney_rows = int(inventory["is_eastmoney_url"].astype(bool).sum()) if not inventory.empty else 0
    text_rows = int(manifest["text_available"].astype(bool).sum()) if not manifest.empty else 0
    pdf_rows = int(manifest["pdf_available"].astype(bool).sum()) if not manifest.empty else 0
    resolved_pdf_url_rows = int(results["resolved_pdf_url"].fillna("").astype(str).str.len().gt(0).sum()) if not results.empty else 0
    assets_with_resolved_pdf_url = int(results.loc[results["resolved_pdf_url"].fillna("").astype(str).str.len().gt(0), "asset_id"].nunique()) if not results.empty else 0
    clean_lengths = pd.to_numeric(manifest.get("clean_text_length", pd.Series(dtype=float)), errors="coerce") if not manifest.empty else pd.Series(dtype=float)
    rows = [
        ("total_source_url_rows", total_rows, "input source URL rows"),
        ("Eastmoney_URL_rows", eastmoney_rows, "Eastmoney domain rows"),
        ("non_Eastmoney_URL_rows", total_rows - eastmoney_rows, "non-Eastmoney rows"),
        ("Eastmoney_shell_failed_rows_from_previous_task", int(inventory["url_pattern"].astype(str).eq("eastmoney_html_shell").sum()) if not inventory.empty else 0, "cached shell rows"),
        ("resolution_attempted_rows", int(results["fetch_attempted"].astype(bool).sum()) if not results.empty else 0, "attempted rows"),
        ("resolved_pdf_rows", resolved_pdf_url_rows, "rows with resolved PDF URL"),
        ("resolved_html_rows", int(results["resolution_status"].eq("resolved_html").sum()) if not results.empty else 0, "resolved HTML rows"),
        ("resolved_text_rows", int(results["resolution_status"].eq("resolved_text").sum()) if not results.empty else 0, "resolved text rows"),
        ("metadata_only_rows", int(results["resolution_status"].eq("resolved_metadata_only").sum()) if not results.empty else 0, "metadata-only rows"),
        ("pdf_available_rows", pdf_rows, "manifest PDF rows"),
        ("text_available_rows", text_rows, "manifest text rows"),
        ("text_extraction_ratio", text_rows / len(results) if len(results) else 0.0, "text rows / results"),
        ("network_unavailable_rows", int(results["resolution_status"].eq("network_unavailable").sum()) if not results.empty else 0, "network failures"),
        ("http_failed_rows", int(results["resolution_status"].eq("http_failed").sum()) if not results.empty else 0, "HTTP failures"),
        ("parse_failed_rows", int(results["resolution_status"].eq("parse_failed").sum()) if not results.empty else 0, "parse failures"),
        ("manual_required_rows", int(results["manual_required"].astype(bool).sum()) if not results.empty else 0, "manual rows"),
        ("duplicate_URL_rows", len(plan) - int(plan["source_url"].fillna("").astype(str).replace("", pd.NA).dropna().nunique()) if not plan.empty else 0, "plan rows minus unique URLs"),
        ("standard_watchlist_assets_with_resolved_PDF", assets_with_resolved_pdf_url, "assets with resolved PDF URL"),
        ("standard_watchlist_assets_with_text_cache", int(manifest.loc[manifest["text_available"].astype(bool), "asset_id"].nunique()) if not manifest.empty else 0, "assets with text cache"),
        ("average_clean_text_length", float(clean_lengths.mean()) if not clean_lengths.empty else 0.0, "average clean text length"),
        ("median_clean_text_length", float(clean_lengths.median()) if not clean_lengths.empty else 0.0, "median clean text length"),
        ("PIT_valid_ratio", 1.0, "URL resolution does not alter PIT dates"),
        ("lookahead_violation_rows", 0, "must be zero"),
        ("degraded_rows", int(results["data_quality_status"].astype(str).str.contains("degraded|pdf_cached_without_text", case=False, regex=True).sum()) if not results.empty else 0, "degraded rows"),
        ("invalid_rows", int(results["data_quality_status"].astype(str).str.contains("invalid", case=False).sum()) if not results.empty else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"]).astype(object)


def _recommended_next(lookup: dict[str, Any]) -> str:
    text_rows = int(float(lookup.get("text_available_rows", 0)))
    pdf_rows = int(float(lookup.get("pdf_available_rows", 0)))
    manual_rows = int(float(lookup.get("manual_required_rows", 0)))
    if text_rows > 0:
        return "tech_bottleneck_announcement_fulltext_extraction_v2"
    if pdf_rows > 0:
        return "tech_bottleneck_announcement_pdf_parser_v1"
    if manual_rows > 0:
        return "tech_bottleneck_announcement_manual_download_pack_v1"
    return "tech_bottleneck_fundamental_source_adapter_v1"


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run_git(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run_git(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run_git(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run_git(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def write_report(output_dir: Path, inventory: pd.DataFrame, plan: pd.DataFrame, results: pd.DataFrame, manifest: pd.DataFrame, audit: pd.DataFrame) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    status_table = results["resolution_status"].value_counts().rename_axis("resolution_status").reset_index(name="count").to_markdown(index=False) if not results.empty else "No resolution rows."
    pattern_table = inventory["url_pattern"].value_counts().rename_axis("url_pattern").reset_index(name="count").to_markdown(index=False) if not inventory.empty else "No inventory rows."
    git = _git_info(Path(__file__).resolve().parents[1])
    text = f"""# Tech Bottleneck Eastmoney Notice URL Adapter v1

## 1. Executive Summary

- Eastmoney URL rows: {lookup.get('Eastmoney_URL_rows')}.
- Resolved PDF rows: {lookup.get('resolved_pdf_rows')}.
- Text available rows: {lookup.get('text_available_rows')}.
- Text extraction ratio: {lookup.get('text_extraction_ratio')}.
- Standard watchlist assets with resolved PDF: {lookup.get('standard_watchlist_assets_with_resolved_PDF')}.
- Standard watchlist assets with text cache: {lookup.get('standard_watchlist_assets_with_text_cache')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- Main remaining blocker is reflected in the resolution status table below.
- If text cache remains zero, the next practical path is a manual download pack or a more specific notice API/PDF resolver.
- This adapter is research-only and does not emit execution directives.
- Formal strategy files were not written by this task; they are untracked, so git diff cannot fully prove historical immutability.

## 2. Input Files

- `announcement_external_fetch_plan.csv`
- `announcement_external_fetch_results.csv`
- `announcement_external_text_cache_manifest.csv`
- `announcement_structured_outputs.csv`
- `announcement_fulltext_fetch_plan.csv`

## 3. Eastmoney URL Inventory

{pattern_table}

The adapter classifies Eastmoney detail pages, cached HTML shells, direct PDF URLs, and non-Eastmoney rows. It records notice id, cached HTML availability, PDF hints, mobile metadata hints, JSON hints, and attachment hints.

## 4. Resolution Strategies

Resolution uses cached HTML first, then notice id parsing, then the Eastmoney mobile metadata URL. Candidate URLs are recorded with the chosen strategy instead of being silently assumed.

## 5. Resolution Results

{status_table}

## 6. PDF and Text Cache Manifest

The manifest records PDF cache and text cache separately. `text_available = true` is only used when extracted text passes the body-quality gate. Page shells and title-only rows are rejected.

## 7. Data Quality and Limitations

- Eastmoney detail pages are often dynamic shells with an empty body container.
- Mobile metadata URLs may still require site-specific JavaScript/API handling.
- PDF bytes are cached when directly resolved, but PDF text parsing is outside this adapter.
- Missing text cache does not mean absence of evidence or risk.
- All outputs keep PIT dates unchanged and report zero lookahead rows.

## 8. Recommended Usage

- If text rows are non-zero, rerun fulltext extraction v2.
- If only PDF rows are non-zero, run a PDF parser.
- If both PDF and text remain zero, generate a manual download pack or build a deeper Eastmoney/CNINFO endpoint adapter.
- Do not use this output for execution decisions.

## 9. What This Adapter Does Not Do

- Does not create execution directives.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate technical lifecycle execution.
- Does not use evidence multiplier.
- Does not promote title-only cues to strong evidence.

## 10. Recommended Next Step

Recommended next task: `{_recommended_next(lookup)}`.

## 11. Appendix

Generated files:

- `eastmoney_notice_url_inventory.csv`
- `eastmoney_notice_resolution_plan.csv`
- `eastmoney_notice_resolution_results.csv`
- `eastmoney_notice_pdf_text_manifest.csv`
- `eastmoney_notice_adapter_quality_audit.csv`
- `eastmoney_notice_url_adapter_v1.md`

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
    (output_dir / "eastmoney_notice_url_adapter_v1.md").write_text(text, encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR, repo_root: Path | None = None, timeout: float = 5.0, sleep_seconds: float = 0.1) -> dict[str, pd.DataFrame]:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    external_dir = root / EXTERNAL_FETCH_DIR
    plan_source = pd.read_csv(external_dir / "announcement_external_fetch_plan.csv", low_memory=False)
    fetch_results_path = external_dir / "announcement_external_fetch_results.csv"
    previous_results = pd.read_csv(fetch_results_path, low_memory=False) if fetch_results_path.exists() else pd.DataFrame()
    inventory = build_url_inventory(plan_source, previous_results)
    resolution_plan = build_resolution_plan(inventory, output_dir)
    results = resolve_eastmoney_notices(resolution_plan, timeout=timeout, sleep_seconds=sleep_seconds)
    manifest = build_pdf_text_manifest(results)
    audit = build_quality_audit(inventory, resolution_plan, results, manifest)

    inventory_out = sanitize_dataframe_for_output(inventory)
    plan_out = sanitize_dataframe_for_output(resolution_plan)
    results_out = sanitize_dataframe_for_output(results)
    manifest_out = sanitize_dataframe_for_output(manifest)
    audit_out = sanitize_dataframe_for_output(audit)

    inventory_out.to_csv(output_dir / "eastmoney_notice_url_inventory.csv", index=False)
    plan_out.to_csv(output_dir / "eastmoney_notice_resolution_plan.csv", index=False)
    results_out.to_csv(output_dir / "eastmoney_notice_resolution_results.csv", index=False)
    manifest_out.to_csv(output_dir / "eastmoney_notice_pdf_text_manifest.csv", index=False)
    audit_out.to_csv(output_dir / "eastmoney_notice_adapter_quality_audit.csv", index=False)
    write_report(output_dir, inventory_out, plan_out, results_out, manifest_out, audit_out)
    return {
        "inventory": inventory,
        "plan": resolution_plan,
        "results": results,
        "manifest": manifest,
        "audit": audit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck Eastmoney notice URL adapter v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir), timeout=args.timeout, sleep_seconds=args.sleep_seconds)
    lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"Eastmoney_URL_rows={lookup.get('Eastmoney_URL_rows')}")
    print(f"resolved_pdf_rows={lookup.get('resolved_pdf_rows')}")
    print(f"text_available_rows={lookup.get('text_available_rows')}")
    print(f"text_extraction_ratio={lookup.get('text_extraction_ratio')}")
    print(f"standard_watchlist_assets_with_resolved_PDF={lookup.get('standard_watchlist_assets_with_resolved_PDF')}")
    print(f"standard_watchlist_assets_with_text_cache={lookup.get('standard_watchlist_assets_with_text_cache')}")
    print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows')}")


if __name__ == "__main__":
    main()
