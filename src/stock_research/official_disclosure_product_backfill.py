from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable
from urllib import parse, request

import pandas as pd

from stock_research.db import fetch_all
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
PRODUCT_MAIN_BUSINESS_COLUMNS = [
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
DOCUMENT_CACHE_INDEX_COLUMNS = [
    "asset_id",
    "ts_code",
    "source_document_id",
    "source_document_url",
]
PRODUCT_JOIN_DIAGNOSTIC_COLUMNS = [
    "asset_id",
    "ts_code",
    "report_period",
    "manifest_rows",
    "product_main_business_rows",
    "join_status",
]
MANIFEST_QUERY_ERROR_COLUMNS = [
    "asset_id",
    "ts_code",
    "error_type",
    "error_message",
]
SOURCE_GAP_REPORT_COLUMNS = [
    "run_id",
    "candidate_rows",
    "candidate_assets",
    "candidate_rows_with_safe_product_evidence",
    "candidate_rows_without_safe_product_evidence",
    "manifest_rows",
    "manifest_query_error_count",
    "main_business_rows",
    "product_main_business_rows",
    "joinable_product_report_periods",
    "evidence_rows",
    "safe_evidence_rows",
    "assets_with_safe_product_evidence",
    "assets_without_safe_product_evidence",
]
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "http://static.cninfo.com.cn/"
CNINFO_CATEGORIES = ("category_ndbg_szsh", "category_bndbg_szsh")


@dataclass(frozen=True)
class OfficialDisclosureProductBackfillResult:
    output_dir: Path
    candidate_rows: int
    candidate_assets: int
    manifest_rows: int
    evidence_rows: int
    safe_evidence_rows: int
    assets_with_safe_product_evidence: int


@dataclass(frozen=True)
class ManifestCollectionResult:
    manifest: pd.DataFrame
    errors: pd.DataFrame


class CninfoDisclosureQueryError(RuntimeError):
    pass


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
        stock_org_id = _cninfo_stock_org_id(stock_code=stock_code, exchange=exchange)
        column = "sse" if exchange == "SH" else "szse"
        plate = exchange.lower()
        rows = []
        category_errors = []

        for category in CNINFO_CATEGORIES:
            try:
                response_payload = self._query_category(
                    stock_code=stock_code,
                    stock_org_id=stock_org_id,
                    exchange=exchange,
                    column=column,
                    plate=plate,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as exc:
                category_errors.append((category, exc))
                continue

            rows.extend(
                _announcement_rows(
                    asset_id=asset_id,
                    ts_code=ts_code,
                    announcements=response_payload.get("announcements", []),
                )
            )

        if not rows and len(category_errors) == len(CNINFO_CATEGORIES):
            raise CninfoDisclosureQueryError(_cninfo_category_error_message(category_errors))
        if not rows:
            rows = self._query_asset_by_code_search(
                asset_id=asset_id,
                ts_code=ts_code,
                stock_code=stock_code,
                column=column,
                plate=plate,
                start_date=start_date,
                end_date=end_date,
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
        stock_org_id: str,
        exchange: str,
        column: str,
        plate: str,
        category: str,
        start_date: object,
        end_date: object,
    ) -> dict[str, Any]:
        body = parse.urlencode(
            {
                "stock": f"{stock_code},{stock_org_id}",
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

    def _query_asset_by_code_search(
        self,
        *,
        asset_id: object,
        ts_code: object,
        stock_code: str,
        column: str,
        plate: str,
        start_date: object,
        end_date: object,
    ) -> list[dict[str, Any]]:
        rows = []
        for category in CNINFO_CATEGORIES:
            try:
                response_payload = self._query_search_category(
                    stock_code=stock_code,
                    column=column,
                    plate=plate,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            rows.extend(
                _announcement_rows(
                    asset_id=asset_id,
                    ts_code=ts_code,
                    announcements=response_payload.get("announcements", []),
                    required_sec_code=stock_code,
                )
            )
        return rows

    def _query_search_category(
        self,
        *,
        stock_code: str,
        column: str,
        plate: str,
        category: str,
        start_date: object,
        end_date: object,
    ) -> dict[str, Any]:
        body = parse.urlencode(
            {
                "stock": "",
                "searchkey": stock_code,
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


def run_official_disclosure_product_backfill(
    *,
    candidates_csv: str | Path,
    output_dir: str | Path,
    run_id: str,
    manifest_client: Any | None = None,
    main_business_loader: Callable[[list[str], str, str], pd.DataFrame] | None = None,
    conn: Any | None = None,
    start_date: object | None = None,
    end_date: object | None = None,
) -> OfficialDisclosureProductBackfillResult:
    candidates = _normalize_candidates(pd.read_csv(candidates_csv, dtype=str))
    client = manifest_client or CninfoDisclosureIndexClient()
    asset_ids = sorted(candidates["asset_id"].dropna().astype(str).unique().tolist())
    business_start_date, business_end_date = _main_business_report_window(start_date, end_date)
    manifest_result = _collect_manifest(candidates, client, business_start_date, business_end_date)
    if main_business_loader is not None:
        main_business = main_business_loader(asset_ids, business_start_date, business_end_date)
    else:
        main_business = _load_main_business_from_db(asset_ids, business_start_date, business_end_date, conn)

    evidence = build_product_evidence_rows(candidates, manifest_result.manifest, main_business)
    if not evidence.empty:
        evidence = evidence.copy()
        evidence["run_id"] = _safe_text(run_id)
        evidence = normalize_evidence_rows(evidence)

    return _write_artifacts(
        output_dir=Path(output_dir),
        run_id=run_id,
        candidates=candidates,
        disclosure_manifest=manifest_result.manifest,
        main_business=main_business,
        manifest_query_errors=manifest_result.errors,
        product_evidence=evidence,
    )


def _load_main_business_from_db(
    asset_ids: Iterable[object],
    start_date: object,
    end_date: object,
    conn: Any | None,
) -> pd.DataFrame:
    ids = [_safe_text(asset_id) for asset_id in asset_ids if _safe_text(asset_id)]
    if conn is None or not ids:
        return pd.DataFrame(columns=PRODUCT_MAIN_BUSINESS_COLUMNS)

    rows = fetch_all(
        conn,
        """
        SELECT asset_id, ts_code, report_period, classify_type, item_name,
               revenue, revenue_ratio, cost, gross_profit, gross_margin, source
        FROM finance.main_business_composition
        WHERE asset_id = ANY(%s)
          AND report_period BETWEEN %s::date AND %s::date
        ORDER BY asset_id, ts_code, report_period, classify_type, item_name, source
        """,
        (ids, _date_text(start_date), _date_text(end_date)),
    )
    return pd.DataFrame(rows, columns=PRODUCT_MAIN_BUSINESS_COLUMNS)


def _collect_manifest(
    candidates: pd.DataFrame,
    client: Any,
    start_date: object,
    end_date: object,
) -> ManifestCollectionResult:
    normalized_candidates = _normalize_candidates(candidates)
    manifest_frames = []
    errors = []
    pairs = (
        normalized_candidates[["asset_id", "ts_code"]]
        .drop_duplicates()
        .sort_values(["asset_id", "ts_code"], kind="stable")
        .to_dict("records")
    )
    for pair in pairs:
        try:
            manifest = client.query_asset(
                asset_id=pair["asset_id"],
                ts_code=pair["ts_code"],
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            errors.append(
                {
                    "asset_id": pair["asset_id"],
                    "ts_code": pair["ts_code"],
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            continue
        if manifest is not None:
            manifest_frames.append(manifest)

    if not manifest_frames:
        manifest = normalize_disclosure_manifest(pd.DataFrame())
    else:
        manifest = normalize_disclosure_manifest(pd.concat(manifest_frames, ignore_index=True))
    return ManifestCollectionResult(manifest=manifest, errors=_normalize_manifest_query_errors(errors))


def _write_artifacts(
    *,
    output_dir: Path,
    run_id: str,
    candidates: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    main_business: pd.DataFrame,
    product_evidence: pd.DataFrame,
    manifest_query_errors: pd.DataFrame | None = None,
) -> OfficialDisclosureProductBackfillResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized_candidates = _normalize_candidates(candidates)
    manifest = normalize_disclosure_manifest(disclosure_manifest)
    product_join_diagnostics = _product_join_diagnostics(manifest, main_business)
    product_rows = _normalize_product_rows(main_business)
    errors = _normalize_manifest_query_errors(manifest_query_errors if manifest_query_errors is not None else [])
    evidence = normalize_evidence_rows(product_evidence)
    if not evidence.empty:
        evidence = evidence.sort_values(
            ["candidate_trade_date", "asset_id", "evidence_date", "source_id", "evidence_snippet"],
            kind="stable",
        ).reset_index(drop=True)

    document_cache_index = _document_cache_index(manifest)
    candidate_rows = int(len(normalized_candidates))
    candidate_assets = int(normalized_candidates["asset_id"].nunique()) if not normalized_candidates.empty else 0
    safe_evidence = evidence[evidence["as_of_safe"].eq(True)].copy()
    safe_evidence_rows = int(len(safe_evidence))
    assets_with_safe_product_evidence = int(safe_evidence["asset_id"].nunique()) if not safe_evidence.empty else 0
    assets_without_safe_product_evidence = max(candidate_assets - assets_with_safe_product_evidence, 0)
    candidate_rows_with_safe_product_evidence = _candidate_rows_with_safe_product_evidence(
        normalized_candidates,
        safe_evidence,
    )
    candidate_rows_without_safe_product_evidence = max(candidate_rows - candidate_rows_with_safe_product_evidence, 0)

    source_gap_report = pd.DataFrame(
        [
            {
                "run_id": _safe_text(run_id),
                "candidate_rows": candidate_rows,
                "candidate_assets": candidate_assets,
                "candidate_rows_with_safe_product_evidence": candidate_rows_with_safe_product_evidence,
                "candidate_rows_without_safe_product_evidence": candidate_rows_without_safe_product_evidence,
                "manifest_rows": int(len(manifest)),
                "manifest_query_error_count": int(len(errors)),
                "main_business_rows": int(len(main_business)),
                "product_main_business_rows": int(len(product_rows)),
                "joinable_product_report_periods": int(
                    product_join_diagnostics["join_status"].eq("joinable").sum()
                    if not product_join_diagnostics.empty
                    else 0
                ),
                "evidence_rows": int(len(evidence)),
                "safe_evidence_rows": safe_evidence_rows,
                "assets_with_safe_product_evidence": assets_with_safe_product_evidence,
                "assets_without_safe_product_evidence": assets_without_safe_product_evidence,
            }
        ],
        columns=SOURCE_GAP_REPORT_COLUMNS,
    )

    evidence.to_csv(output_dir / "product_evidence.csv", index=False)
    manifest.to_csv(output_dir / "disclosure_manifest.csv", index=False)
    errors.to_csv(output_dir / "manifest_query_errors.csv", index=False)
    product_join_diagnostics.to_csv(output_dir / "product_join_diagnostics.csv", index=False)
    document_cache_index.to_csv(output_dir / "document_cache_index.csv", index=False)
    source_gap_report.to_csv(output_dir / "source_gap_report.csv", index=False)
    (output_dir / "coverage_summary.md").write_text(
        _coverage_summary_markdown(source_gap_report.iloc[0].to_dict()),
        encoding="utf-8",
    )

    return OfficialDisclosureProductBackfillResult(
        output_dir=output_dir,
        candidate_rows=candidate_rows,
        candidate_assets=candidate_assets,
        manifest_rows=int(len(manifest)),
        evidence_rows=int(len(evidence)),
        safe_evidence_rows=safe_evidence_rows,
        assets_with_safe_product_evidence=assets_with_safe_product_evidence,
    )


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
    for column in ["asset_id", "ts_code", "stock_name", "trade_date", "candidate_trade_date", "as_of_date"]:
        if column not in normalized.columns:
            normalized[column] = ""
    if normalized.empty:
        return pd.DataFrame(columns=["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"])

    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized["ts_code"] = normalized.apply(
        lambda row: _safe_text(row["ts_code"]) or _derive_ts_code(row["asset_id"]),
        axis=1,
    )
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["candidate_trade_date"] = normalized.apply(
        lambda row: _first_date_value(row["candidate_trade_date"], row["trade_date"]),
        axis=1,
    )
    normalized["as_of_date"] = normalized.apply(
        lambda row: _first_date_value(row["as_of_date"], row["candidate_trade_date"], row["trade_date"]),
        axis=1,
    )
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


def _cninfo_stock_org_id(*, stock_code: str, exchange: str) -> str:
    org_prefix = "gssh" if exchange == "SH" else "gssz"
    return f"{org_prefix}{int(stock_code):07d}"


def _announcement_rows(
    *,
    asset_id: object,
    ts_code: object,
    announcements: object,
    required_sec_code: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(announcements, list):
        return []
    rows = []
    for announcement in announcements:
        if not isinstance(announcement, dict):
            continue
        if required_sec_code is not None and _safe_text(announcement.get("secCode")) != required_sec_code:
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
    return rows


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


def _derive_ts_code(asset_id: object) -> str:
    text = _safe_text(asset_id)
    if not text:
        return ""
    if re.fullmatch(r"\d+\.(SH|SZ|SSE|SZSE)", text, flags=re.IGNORECASE):
        stock_code, exchange = text.rsplit(".", 1)
        return f"{stock_code}.{_canonical_exchange(exchange)}"
    if text.upper().startswith("CN:"):
        parts = text.split(":")
        if len(parts) == 3 and parts[0].upper() == "CN":
            exchange = _canonical_exchange(parts[1])
            if exchange in {"SH", "SZ"} and re.fullmatch(r"\d+", parts[2]):
                return f"{parts[2]}.{exchange}"
    return ""


def _canonical_exchange(exchange: object) -> str:
    text = _safe_text(exchange).upper()
    return {"SSE": "SH", "SZSE": "SZ"}.get(text, text)


def _date_text(value: object) -> str:
    date_value = _date_value(value)
    return "" if date_value is None else date_value.isoformat()


def _main_business_report_window(start_date: object | None, end_date: object | None) -> tuple[str, str]:
    end = _date_value(end_date) or dt.date.today()
    start = _date_value(start_date)
    if start is None:
        start = dt.date(end.year - 2, 1, 1)
    else:
        start = dt.date(start.year - 2, 1, 1)
    return start.isoformat(), end.isoformat()


def _document_cache_index(manifest: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_disclosure_manifest(manifest)
    if normalized.empty:
        return pd.DataFrame(columns=DOCUMENT_CACHE_INDEX_COLUMNS)
    return (
        normalized[DOCUMENT_CACHE_INDEX_COLUMNS]
        .drop_duplicates()
        .sort_values(["asset_id", "ts_code", "source_document_id", "source_document_url"], kind="stable")
        .reset_index(drop=True)
    )


def _product_join_diagnostics(manifest: pd.DataFrame, main_business: pd.DataFrame) -> pd.DataFrame:
    normalized_manifest = normalize_disclosure_manifest(manifest)
    if normalized_manifest.empty:
        return pd.DataFrame(columns=PRODUCT_JOIN_DIAGNOSTIC_COLUMNS)

    manifest_counts = (
        normalized_manifest.groupby(["asset_id", "ts_code", "report_period"], dropna=False)
        .size()
        .reset_index(name="manifest_rows")
    )
    product_rows = _normalize_product_rows(main_business)
    if product_rows.empty:
        manifest_counts["product_main_business_rows"] = 0
    else:
        product_counts = (
            product_rows.groupby(["asset_id", "ts_code", "report_period"], dropna=False)
            .size()
            .reset_index(name="product_main_business_rows")
        )
        manifest_counts = manifest_counts.merge(
            product_counts,
            on=["asset_id", "ts_code", "report_period"],
            how="left",
        )
        manifest_counts["product_main_business_rows"] = (
            manifest_counts["product_main_business_rows"].fillna(0).astype(int)
        )

    manifest_counts["report_period"] = manifest_counts["report_period"].map(_date_text)
    manifest_counts["join_status"] = manifest_counts["product_main_business_rows"].map(
        lambda count: "joinable" if int(count) > 0 else "missing_product_report_period"
    )
    return (
        manifest_counts[PRODUCT_JOIN_DIAGNOSTIC_COLUMNS]
        .sort_values(["asset_id", "ts_code", "report_period"], kind="stable")
        .reset_index(drop=True)
    )


def _coverage_summary_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Official Disclosure Product Backfill", ""]
    for column in SOURCE_GAP_REPORT_COLUMNS:
        lines.append(f"- {column}: {summary.get(column, '')}")
    lines.append("")
    return "\n".join(lines)


def _cninfo_category_error_message(category_errors: list[tuple[str, Exception]]) -> str:
    details = [
        f"{category}: {type(error).__name__}: {_safe_text(error)}"
        for category, error in category_errors
    ]
    return "CNINFO query failed for all categories: " + "; ".join(details)


def _first_date_value(*values: object) -> dt.date | None:
    for value in values:
        parsed = _date_value(value)
        if parsed is not None:
            return parsed
    return None


def _normalize_manifest_query_errors(rows: Iterable[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    errors = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    for column in MANIFEST_QUERY_ERROR_COLUMNS:
        if column not in errors.columns:
            errors[column] = ""
    if errors.empty:
        return pd.DataFrame(columns=MANIFEST_QUERY_ERROR_COLUMNS)
    for column in MANIFEST_QUERY_ERROR_COLUMNS:
        errors[column] = errors[column].map(_safe_text)
    return (
        errors[MANIFEST_QUERY_ERROR_COLUMNS]
        .sort_values(["asset_id", "ts_code", "error_type", "error_message"], kind="stable")
        .reset_index(drop=True)
    )


def _candidate_rows_with_safe_product_evidence(candidates: pd.DataFrame, safe_evidence: pd.DataFrame) -> int:
    if candidates.empty or safe_evidence.empty:
        return 0
    safe_keys = {
        (
            _safe_text(row["asset_id"]),
            _date_text(row["candidate_trade_date"]),
            _date_text(row["as_of_date"]),
        )
        for row in safe_evidence[["asset_id", "candidate_trade_date", "as_of_date"]].to_dict("records")
    }
    count = 0
    for row in candidates[["asset_id", "candidate_trade_date", "as_of_date"]].to_dict("records"):
        key = (
            _safe_text(row["asset_id"]),
            _date_text(row["candidate_trade_date"]),
            _date_text(row["as_of_date"]),
        )
        if key in safe_keys:
            count += 1
    return count
