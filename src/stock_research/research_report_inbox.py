from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.hibor_reports import _exchange_from_symbol, _stable_token
from stock_research.stock_report_pdf_backfill import (
    build_stock_report_pdf_field_backfill,
    upsert_stock_report_pdf_fields,
)
from stock_research.stock_report_web_collection import upsert_stock_report_sources_events


DEFAULT_RESEARCH_REPORT_INBOX = Path("data/manual/research_report_inbox")
DEFAULT_RESEARCH_REPORT_INBOX_OUTPUT = Path("outputs/research/research_report_inbox")
INBOX_SOURCE_TYPE = "research_report_inbox"
INBOX_SOURCE_NAME = "本地研报收件箱"
INBOX_SOURCE_FILE = "research_report_inbox_sources.csv"
INBOX_EVENT_FILE = "research_report_inbox_events.csv"
INBOX_STATUS_FILE = "status.json"
INBOX_MANIFEST_FILE = "manifest.json"


def build_research_inbox_sources_events(pdf_paths: Iterable[str | Path]) -> dict[str, pd.DataFrame]:
    source_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for path_value in pdf_paths:
        pdf_path = Path(path_value).expanduser().resolve()
        meta = _parse_inbox_pdf_filename(pdf_path)
        if meta is None:
            continue
        source_url = pdf_path.as_uri()
        report_id = f"inbox_{_stable_token([source_url])}"
        metadata = {
            "research_report_inbox": {
                "local_pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "sha256": _file_sha256(pdf_path),
            }
        }
        source_rows.append(
            {
                "report_id": report_id,
                "source_type": INBOX_SOURCE_TYPE,
                "source_name": INBOX_SOURCE_NAME,
                "broker": meta["broker"],
                "analyst": "",
                "report_title": meta["report_title"],
                "publish_date": meta["publish_date"],
                "source_url": source_url,
                "public_access": False,
                "copyright_note": "Imported from local research report inbox for internal research use only.",
                "source_confidence": 0.85,
                "raw_summary": "",
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
        event_rows.append(
            {
                "report_id": report_id,
                "asset_id": meta["asset_id"],
                "ts_code": meta["ts_code"],
                "stock_name": meta["stock_name"],
                "industry_name": "",
                "report_date": meta["publish_date"],
                "rating": "",
                "rating_change": "",
                "target_price": pd.NA,
                "target_upside": pd.NA,
                "industry_view": "",
                "company_view": "",
                "risk_summary": "",
                "effective_start_date": meta["publish_date"],
                "effective_end_date": pd.NA,
                "auto_trade_enabled": False,
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
    return {
        "sources": pd.DataFrame(source_rows, dtype=object),
        "events": pd.DataFrame(event_rows, dtype=object),
    }


def sync_research_report_inbox(
    *,
    input_dir: str | Path = DEFAULT_RESEARCH_REPORT_INBOX,
    output_dir: str | Path = DEFAULT_RESEARCH_REPORT_INBOX_OUTPUT,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    run_pdf_backfill: bool = True,
) -> dict[str, Any]:
    input_path = Path(input_dir).expanduser()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / INBOX_MANIFEST_FILE
    manifest = _load_manifest(manifest_path)
    scanned = sorted(input_path.rglob("*.pdf")) if input_path.exists() else []
    new_paths: list[Path] = []
    new_hashes: dict[str, str] = {}
    for pdf_path in scanned:
        digest = _file_sha256(pdf_path)
        if digest in manifest:
            continue
        new_paths.append(pdf_path)
        new_hashes[str(pdf_path.resolve())] = digest

    built = build_research_inbox_sources_events(new_paths)
    sources = built["sources"]
    events = built["events"]
    imported_paths = {
        str(_metadata_path(row.get("metadata"))): str(_metadata_sha256(row.get("metadata")))
        for row in sources.fillna("").to_dict("records")
    }
    unsupported_paths = [path for path in new_paths if str(path.resolve()) not in imported_paths]
    source_path = output / INBOX_SOURCE_FILE
    event_path = output / INBOX_EVENT_FILE
    sources.to_csv(source_path, index=False)
    events.to_csv(event_path, index=False)

    db_result = None
    if write_db and not sources.empty:
        db_result = upsert_stock_report_sources_events(sources=sources, events=events, service=service)

    pdf_result = None
    if run_pdf_backfill and not sources.empty:
        pdf_result = build_stock_report_pdf_field_backfill(sources=sources, output_dir=output, resume=True)
        if write_db:
            pdf_result["db"] = upsert_stock_report_pdf_fields(pdf_result.get("fields", pd.DataFrame()), service=service)

    for digest in imported_paths.values():
        if digest:
            manifest[digest] = {"status": "imported"}
    for path in unsupported_paths:
        digest = new_hashes.get(str(path.resolve()))
        if digest:
            manifest[digest] = {"status": "unsupported", "path": str(path.resolve())}
    _write_manifest(manifest_path, manifest)

    summary = {
        "input_dir": str(input_path),
        "scanned_pdf_count": len(scanned),
        "new_pdf_count": len(new_paths),
        "imported_pdf_count": len(sources),
        "unsupported_pdf_count": len(unsupported_paths),
        "write_db": write_db,
    }
    status = {
        "summary": summary,
        "paths": {
            "sources": str(source_path),
            "events": str(event_path),
            "manifest": str(manifest_path),
            "status": str(output / INBOX_STATUS_FILE),
        },
        "db": db_result,
        "pdf": {
            "rows": len(pdf_result.get("fields", pd.DataFrame())) if pdf_result else 0,
            "paths": pdf_result.get("paths", {}) if pdf_result else {},
        },
    }
    (output / INBOX_STATUS_FILE).write_text(json.dumps(status, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return status


def _parse_inbox_pdf_filename(path: Path) -> dict[str, str] | None:
    stem = path.stem
    parts = stem.split("-")
    date_index = next((idx for idx, part in enumerate(parts) if re.fullmatch(r"\d{8}", part)), -1)
    if date_index >= 0 and len(parts) >= date_index + 5:
        date_raw = parts[date_index]
        broker = parts[date_index + 1]
        stock_name = parts[date_index + 2]
        symbol_text = parts[date_index + 3]
        title = "-".join(parts[date_index + 4:]).strip()
    elif len(parts) >= 5:
        broker, stock_name, symbol_text = parts[0], parts[1], parts[2]
        title = "-".join(parts[3:-1]).strip()
        date_short = parts[-1]
        if not re.fullmatch(r"\d{6}", date_short):
            return None
        date_raw = f"20{date_short}"
    else:
        return None

    symbol_match = re.fullmatch(r"(?P<symbol>\d{6})(?:\.(?P<exchange>SH|SZ))?", symbol_text, flags=re.IGNORECASE)
    if not symbol_match:
        return None
    symbol = symbol_match.group("symbol")
    exchange = (symbol_match.group("exchange") or _exchange_from_symbol(symbol)).upper()
    publish_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    return {
        "publish_date": publish_date,
        "broker": broker.strip(),
        "stock_name": stock_name.strip(),
        "symbol": symbol,
        "exchange": exchange,
        "ts_code": f"{symbol}.{exchange}",
        "asset_id": f"CN:{exchange}:{symbol}",
        "report_title": title,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_manifest(path: Path, manifest: dict[str, dict[str, str]]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _metadata_path(value: object) -> str:
    metadata = _metadata_dict(value)
    return str(metadata.get("research_report_inbox", {}).get("local_pdf_path") or "")


def _metadata_sha256(value: object) -> str:
    metadata = _metadata_dict(value)
    return str(metadata.get("research_report_inbox", {}).get("sha256") or "")


def _metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
