from __future__ import annotations

import io
from pathlib import Path
from typing import Callable
from urllib import request

import pandas as pd
from pypdf import PdfReader

from stock_research.tech_bottleneck_evidence_backfill import (
    classify_text_evidence,
    normalize_evidence_rows,
)


def build_official_report_semantic_evidence(
    *,
    candidates: pd.DataFrame,
    manifest: pd.DataFrame,
    run_id: str,
    lookback_days: int,
    text_loader: Callable[[str], str],
) -> pd.DataFrame:
    normalized_candidates = _normalize_candidates(candidates)
    normalized_manifest = _normalize_manifest(manifest)
    rows: list[dict[str, object]] = []
    text_cache: dict[str, str] = {}

    for candidate in normalized_candidates.to_dict("records"):
        asset_manifest = normalized_manifest[normalized_manifest["asset_id"].eq(candidate["asset_id"])]
        safe_manifest = _pit_safe_manifest_rows(
            asset_manifest,
            as_of_date=str(candidate["as_of_date"]),
            lookback_days=lookback_days,
        )
        for doc in safe_manifest.to_dict("records"):
            source_url = str(doc.get("source_document_url") or "")
            if not source_url:
                continue
            if source_url not in text_cache:
                text_cache[source_url] = text_loader(source_url)
            text = text_cache[source_url]
            if not text.strip():
                continue
            evidence_text = f"{doc.get('announcement_title', '')}\n{text}"
            for match in classify_text_evidence(
                text=evidence_text,
                source_type="official_disclosure_report_pdf",
                source_id=str(doc.get("source_document_id") or source_url),
                source_title=str(doc.get("announcement_title") or ""),
                source_date=str(doc.get("publish_date") or ""),
            ):
                rows.append(
                    {
                        **match,
                        "run_id": run_id,
                        "asset_id": candidate["asset_id"],
                        "stock_name": candidate["stock_name"],
                        "candidate_trade_date": candidate["trade_date"],
                        "as_of_date": candidate["as_of_date"],
                        "source_url": source_url,
                        "as_of_safe": True,
                        "metadata_json": {
                            "report_period": str(doc.get("report_period") or ""),
                            "ts_code": str(doc.get("ts_code") or ""),
                        },
                    }
                )

    return normalize_evidence_rows(pd.DataFrame(rows))


def load_pdf_text_from_url(url: str, *, timeout_seconds: int = 30, max_pages: int = 80) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=timeout_seconds) as response:
        content = response.read()
    return extract_pdf_text(content, max_pages=max_pages)


def extract_pdf_text(content: bytes, *, max_pages: int = 80) -> str:
    reader = PdfReader(io.BytesIO(content))
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def write_official_report_semantic_artifacts(*, evidence: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "evidence.csv"
    summary_path = output_dir / "summary.md"
    evidence.to_csv(csv_path, index=False)
    summary_path.write_text(_render_summary(evidence), encoding="utf-8")
    return {"csv": csv_path, "summary": summary_path}


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    if "trade_date" not in frame.columns and "candidate_trade_date" in frame.columns:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    for column in ["asset_id", "stock_name", "trade_date"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    frame["as_of_date"] = frame["trade_date"]
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = manifest.copy()
    for column in [
        "asset_id",
        "ts_code",
        "publish_date",
        "report_period",
        "announcement_title",
        "source_document_id",
        "source_document_url",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    for column in ["asset_id", "ts_code", "announcement_title", "source_document_id", "source_document_url"]:
        frame[column] = frame[column].astype("string").fillna("")
    frame["publish_date"] = pd.to_datetime(frame["publish_date"], errors="coerce")
    frame["report_period"] = pd.to_datetime(frame["report_period"], errors="coerce")
    return frame


def _pit_safe_manifest_rows(manifest: pd.DataFrame, *, as_of_date: str, lookback_days: int) -> pd.DataFrame:
    as_of = pd.Timestamp(as_of_date)
    start = as_of - pd.Timedelta(days=int(lookback_days))
    return manifest[
        manifest["publish_date"].notna()
        & manifest["report_period"].notna()
        & manifest["publish_date"].le(as_of)
        & manifest["publish_date"].ge(start)
        & manifest["report_period"].le(as_of)
    ].copy()


def _render_summary(evidence: pd.DataFrame) -> str:
    lines = ["# Official Report Semantic Evidence", "", f"Evidence rows: {len(evidence)}"]
    if evidence.empty:
        return "\n".join(lines) + "\n"
    lines += ["", "## Evidence Type Counts"]
    for evidence_type, count in evidence["evidence_type"].value_counts().items():
        lines.append(f"- {evidence_type}: {count}")
    lines += ["", "## Asset Count"]
    lines.append(f"- assets_with_evidence: {evidence['asset_id'].nunique()}")
    return "\n".join(lines) + "\n"
