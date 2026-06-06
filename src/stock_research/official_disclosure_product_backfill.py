from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Iterable
from urllib import parse, request

import pandas as pd

from stock_research.tech_bottleneck_evidence_backfill import normalize_evidence_rows


PRODUCT_DISCLOSURE_COLUMNS = [
    "asset_id",
    "ts_code",
    "publish_date",
    "report_period",
    "announcement_title",
    "source_document_id",
    "source_document_url",
    "disclosure_type",
    "is_supported_product_disclosure",
]
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "http://static.cninfo.com.cn/"
CNINFO_CATEGORIES = ("category_ndbg_szsh", "category_bndbg_szsh")


class CninfoDisclosureIndexClient:
    def __init__(self, opener=None, timeout_seconds: int = 20):
        self._opener = opener or request.urlopen
        self._timeout_seconds = timeout_seconds

    def query_asset(
        self,
        asset_id: object,
        ts_code: object,
        start_date: object,
        end_date: object,
    ) -> pd.DataFrame:
        stock_code, exchange = _exchange_suffix(ts_code)
        column = "sse" if exchange == "SH" else "szse"
        plate = exchange.lower()
        rows = []

        for category in CNINFO_CATEGORIES:
            try:
                response_payload = self._query_category(
                    stock_code=stock_code,
                    exchange=exchange,
                    column=column,
                    plate=plate,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue

            announcements = response_payload.get("announcements", [])
            if not isinstance(announcements, list):
                continue
            for announcement in announcements:
                if not isinstance(announcement, dict):
                    continue
                publish_date = _announcement_time_to_date(announcement.get("announcementTime"))
                title = _safe_text(announcement.get("announcementTitle"))
                rows.append(
                    {
                        "asset_id": asset_id,
                        "ts_code": ts_code,
                        "publish_date": publish_date,
                        "report_period": _infer_report_period_from_title(title, publish_date),
                        "announcement_title": title,
                        "source_document_id": announcement.get("announcementId"),
                        "source_document_url": _cninfo_static_url(announcement.get("adjunctUrl")),
                    }
                )

        manifest = normalize_disclosure_manifest(rows)
        manifest = manifest[manifest["is_supported_product_disclosure"]].copy()
        return manifest.drop_duplicates(
            ["asset_id", "ts_code", "report_period", "source_document_id"],
            keep="first",
        ).reset_index(drop=True)

    def _query_category(
        self,
        *,
        stock_code: str,
        exchange: str,
        column: str,
        plate: str,
        category: str,
        start_date: object,
        end_date: object,
    ) -> dict[str, Any]:
        body = parse.urlencode(
            {
                "stock": f"{stock_code},{exchange}",
                "tabName": "fulltext",
                "pageSize": "30",
                "pageNum": "1",
                "column": column,
                "category": category,
                "plate": plate,
                "seDate": f"{_safe_text(start_date)}~{_safe_text(end_date)}",
                "isHLtitle": "true",
            }
        ).encode("utf-8")
        cninfo_request = request.Request(
            CNINFO_QUERY_URL,
            data=body,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch",
            },
            method="POST",
        )
        with self._opener(cninfo_request, timeout=self._timeout_seconds) as response:
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except json.JSONDecodeError:
                return {}
        return payload if isinstance(payload, dict) else {}


def is_supported_product_disclosure(title: object) -> bool:
    text = _safe_text(title)
    if not text:
        return False

    excluded_terms = [
        "摘要",
        "英文",
        "english",
        "取消",
        "撤销",
        "作废",
        "社会责任",
        "csr",
        "esg",
        "环境",
        "可持续",
        "问询",
        "回复",
        "回函",
        "监管函",
    ]
    lowered = text.lower()
    if any(term in lowered for term in excluded_terms):
        return False

    return _disclosure_type(text) in {"annual", "semiannual"}


def normalize_disclosure_manifest(rows: Iterable[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    manifest = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    for column in PRODUCT_DISCLOSURE_COLUMNS:
        if column not in manifest.columns:
            manifest[column] = ""
    if manifest.empty:
        return pd.DataFrame(columns=PRODUCT_DISCLOSURE_COLUMNS)

    manifest["asset_id"] = manifest["asset_id"].map(_safe_text)
    manifest["ts_code"] = manifest["ts_code"].map(_safe_text)
    manifest["publish_date"] = manifest["publish_date"].map(_date_value)
    manifest["report_period"] = manifest["report_period"].map(_date_value)
    manifest["announcement_title"] = manifest["announcement_title"].map(_safe_text)
    manifest["source_document_id"] = manifest["source_document_id"].map(_safe_text)
    manifest["source_document_url"] = manifest["source_document_url"].map(_safe_text)
    manifest["disclosure_type"] = manifest["announcement_title"].map(_disclosure_type)
    manifest["is_supported_product_disclosure"] = manifest["announcement_title"].map(is_supported_product_disclosure)

    manifest = manifest[
        manifest["asset_id"].ne("")
        & manifest["ts_code"].ne("")
        & manifest["publish_date"].notna()
        & manifest["report_period"].notna()
    ].copy()

    return (
        manifest[PRODUCT_DISCLOSURE_COLUMNS]
        .sort_values(["asset_id", "ts_code", "report_period", "publish_date", "source_document_id"], kind="stable")
        .reset_index(drop=True)
    )


def build_product_evidence_rows(
    candidates: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    main_business: pd.DataFrame,
) -> pd.DataFrame:
    normalized_candidates = _normalize_candidates(candidates)
    manifest = normalize_disclosure_manifest(disclosure_manifest)
    product_rows = _normalize_product_rows(main_business)

    manifest = manifest[manifest["is_supported_product_disclosure"]].copy()
    if normalized_candidates.empty or manifest.empty or product_rows.empty:
        return normalize_evidence_rows(pd.DataFrame())

    joined = normalized_candidates.merge(manifest, on=["asset_id", "ts_code"], how="inner")
    joined = joined.merge(product_rows, on=["asset_id", "ts_code", "report_period"], how="inner")

    evidence_rows = []
    for row in joined.to_dict("records"):
        as_of_safe = row["publish_date"] <= row["as_of_date"] and row["report_period"] <= row["as_of_date"]
        metadata = {
            "report_period": row["report_period"],
            "publish_date": row["publish_date"],
            "classify_type": row["classify_type"],
            "item_name": row["item_name"],
            "revenue": row["revenue"],
            "revenue_ratio": row["revenue_ratio"],
            "cost": row["cost"],
            "gross_profit": row["gross_profit"],
            "gross_margin": row["gross_margin"],
            "source": row["source"],
            "source_document_id": row["source_document_id"],
            "source_document_url": row["source_document_url"],
            "extraction_method": "official_manifest_join_main_business_composition",
            "extraction_confidence": "strong",
        }
        evidence_rows.append(
            {
                "asset_id": row["asset_id"],
                "stock_name": row.get("stock_name", ""),
                "candidate_trade_date": row["candidate_trade_date"],
                "as_of_date": row["as_of_date"],
                "evidence_date": row["publish_date"],
                "source_type": "official_disclosure_product_backfill",
                "source_id": row["source_document_id"],
                "source_title": row["announcement_title"],
                "source_url": row["source_document_url"],
                "evidence_type": "product_revenue_exposure",
                "evidence_snippet": _evidence_snippet(row),
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": as_of_safe,
                "metadata_json": metadata,
            }
        )

    return normalize_evidence_rows(_sort_product_evidence_rows(pd.DataFrame(evidence_rows)))


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in ["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]:
        if column not in normalized.columns:
            normalized[column] = ""
    if normalized.empty:
        return pd.DataFrame(columns=["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"])

    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized["ts_code"] = normalized["ts_code"].map(_safe_text)
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["candidate_trade_date"] = normalized["candidate_trade_date"].map(_date_value)
    normalized["as_of_date"] = normalized["as_of_date"].map(_date_value)
    normalized = normalized[
        normalized["asset_id"].ne("")
        & normalized["ts_code"].ne("")
        & normalized["candidate_trade_date"].notna()
        & normalized["as_of_date"].notna()
    ].copy()
    return normalized[["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]]


def _normalize_product_rows(main_business: pd.DataFrame) -> pd.DataFrame:
    product_rows = main_business.copy()
    product_columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "classify_type",
        "item_name",
        "revenue",
        "revenue_ratio",
        "cost",
        "gross_profit",
        "gross_margin",
        "source",
    ]
    for column in product_columns:
        if column not in product_rows.columns:
            product_rows[column] = ""
    if product_rows.empty:
        return pd.DataFrame(columns=product_columns)

    product_rows["asset_id"] = product_rows["asset_id"].map(_safe_text)
    product_rows["ts_code"] = product_rows["ts_code"].map(_safe_text)
    product_rows["report_period"] = product_rows["report_period"].map(_date_value)
    product_rows["classify_type"] = product_rows["classify_type"].map(_safe_text)
    product_rows["item_name"] = product_rows["item_name"].map(_safe_text)
    product_rows["source"] = product_rows["source"].map(_safe_text)
    product_rows = product_rows[
        product_rows["asset_id"].ne("")
        & product_rows["ts_code"].ne("")
        & product_rows["report_period"].notna()
        & product_rows["classify_type"].str.contains("产品", na=False)
    ].copy()
    return product_rows[product_columns]


def _sort_product_evidence_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    return rows.sort_values(
        ["candidate_trade_date", "as_of_date", "asset_id", "evidence_date", "source_id", "evidence_snippet"],
        kind="stable",
    ).reset_index(drop=True)


def _disclosure_type(title: object) -> str:
    text = _safe_text(title)
    if "年半年度报告" in text or "半年度报告" in text:
        return "semiannual"
    if "年年度报告" in text or "年度报告" in text:
        return "annual"
    return "other"


def _exchange_suffix(ts_code: object) -> tuple[str, str]:
    text = _safe_text(ts_code)
    if not text:
        raise ValueError("CNINFO ts_code is required")

    if text.upper().startswith("CN:"):
        parts = text.split(":")
        if len(parts) != 3 or parts[0].upper() != "CN":
            raise ValueError(f"Unsupported CNINFO ts_code format: {text}")
        exchange = parts[1].upper()
        stock_code = parts[2]
    elif "." in text:
        stock_code, exchange = text.rsplit(".", 1)
        exchange = exchange.upper()
    else:
        raise ValueError(f"Unsupported CNINFO ts_code format: {text}")

    exchange = {"SSE": "SH", "SZSE": "SZ"}.get(exchange, exchange)
    if exchange not in {"SH", "SZ"} or not re.fullmatch(r"\d+", stock_code):
        raise ValueError(f"Unsupported CNINFO ts_code format: {text}")
    return stock_code, exchange


def _announcement_time_to_date(value: object) -> dt.date | None:
    if isinstance(value, (int, float)) and not pd.isna(value):
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone(dt.timedelta(hours=8))).date()
    text = _safe_text(value)
    if re.fullmatch(r"\d{13}", text):
        return dt.datetime.fromtimestamp(int(text) / 1000, tz=dt.timezone(dt.timedelta(hours=8))).date()
    return _date_value(value)


def _infer_report_period_from_title(title: object, publish_date: object) -> dt.date | None:
    del publish_date
    text = _safe_text(title)
    match = re.search(r"(20\d{2})", text)
    if not match:
        return None

    year = int(match.group(1))
    disclosure_type = _disclosure_type(text)
    if disclosure_type == "annual":
        return dt.date(year, 12, 31)
    if disclosure_type == "semiannual":
        return dt.date(year, 6, 30)
    return None


def _cninfo_static_url(adjunct_url: object) -> str:
    text = _safe_text(adjunct_url)
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    return parse.urljoin(CNINFO_STATIC_BASE_URL, text.lstrip("/"))


def _date_value(value: object) -> dt.date | None:
    if value is None or pd.isna(value) or value == "":
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.date()


def _safe_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _evidence_snippet(row: dict[str, Any]) -> str:
    ratio = row.get("revenue_ratio")
    ratio_text = "" if ratio is None or pd.isna(ratio) else f"，收入占比{ratio}%"
    return f"{row.get('announcement_title', '')}披露{row.get('item_name', '')}{ratio_text}"
