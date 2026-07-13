from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.stock_report_web_collection import upsert_stock_report_sources_events
from stock_research.yanbaoke_reports import YANBAOKE_SOURCE_NAME, YANBAOKE_SOURCE_TYPE


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COVERAGE_PATH = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_yanbaoke_report_backfill_v1"
    / "review_universe_report_coverage_after_backfill.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_report_pdf_platform_import_v1"
TASK_NAME = "tech_bottleneck_review_universe_report_pdf_platform_import_v1"


@dataclass(frozen=True)
class PlatformReportImportFrames:
    sources: pd.DataFrame
    events: pd.DataFrame
    skipped: pd.DataFrame
    summary: dict[str, Any]


def build_platform_report_import_frames(
    coverage: pd.DataFrame,
    *,
    coverage_path: str | Path | None = None,
    existing_local_pdf_paths: set[str] | None = None,
) -> PlatformReportImportFrames:
    existing = {_normalize_pdf_path(path) for path in (existing_local_pdf_paths or set()) if path}
    source_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    seen_input_paths: set[str] = set()
    seen_import_paths: set[str] = set()
    counts = {
        "coverage_stock_count": int(_stock_count(coverage)),
        "candidate_pdf_path_count": 0,
        "non_pdf_path_count": 0,
        "missing_pdf_path_count": 0,
        "duplicate_input_pdf_path_count": 0,
        "already_indexed_pdf_path_count": 0,
        "import_pdf_count": 0,
    }

    for row in coverage.fillna("").to_dict("records"):
        if not _truthy(row.get("has_report_pdf")):
            continue
        stock_code = _clean_code(row.get("stock_code"))
        stock_name = str(row.get("stock_name") or "").strip()
        paths = _split_paths(row.get("report_pdf_paths"))
        titles = _split_paths(row.get("report_titles"))
        for index, path_text in enumerate(paths):
            counts["candidate_pdf_path_count"] += 1
            raw_path = str(path_text or "").strip()
            if not raw_path.lower().endswith(".pdf"):
                counts["non_pdf_path_count"] += 1
                skipped_rows.append(_skipped(stock_code, stock_name, raw_path, "non_pdf_path"))
                continue
            normalized = _normalize_pdf_path(raw_path)
            if normalized in seen_input_paths:
                counts["duplicate_input_pdf_path_count"] += 1
                skipped_rows.append(_skipped(stock_code, stock_name, raw_path, "duplicate_input_pdf_path"))
                continue
            seen_input_paths.add(normalized)
            pdf_path = Path(normalized)
            if not pdf_path.exists() or not pdf_path.is_file():
                counts["missing_pdf_path_count"] += 1
                skipped_rows.append(_skipped(stock_code, stock_name, raw_path, "missing_pdf_path"))
                continue
            if normalized in existing:
                counts["already_indexed_pdf_path_count"] += 1
                skipped_rows.append(_skipped(stock_code, stock_name, raw_path, "already_indexed_pdf_path"))
                continue
            if normalized in seen_import_paths:
                counts["duplicate_input_pdf_path_count"] += 1
                skipped_rows.append(_skipped(stock_code, stock_name, raw_path, "duplicate_import_pdf_path"))
                continue
            seen_import_paths.add(normalized)

            title = str(titles[index] if index < len(titles) else "").strip() or pdf_path.name
            publish_date = _date_from_text(pdf_path.name)
            ts_code = _ts_code(stock_code)
            asset_id = _asset_id(stock_code)
            source_url = pdf_path.resolve().as_uri()
            report_id = f"tech_bottleneck_review_pdf_{_stable_token([normalized, stock_code])}"
            broker = _broker_from_title(title)
            metadata = {
                "yanbaoke": {
                    "local_pdf_path": normalized,
                    "filename": pdf_path.name,
                },
                "tech_bottleneck_review_universe_platform_import": {
                    "task_name": TASK_NAME,
                    "coverage_csv": str(coverage_path or ""),
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                },
                "local_pdf_path": normalized,
            }
            source_rows.append(
                {
                    "report_id": report_id,
                    "source_type": YANBAOKE_SOURCE_TYPE,
                    "source_name": YANBAOKE_SOURCE_NAME,
                    "broker": broker,
                    "analyst": "",
                    "report_title": title,
                    "publish_date": publish_date,
                    "source_url": source_url,
                    "public_access": False,
                    "copyright_note": "Downloaded from Yanbaoke API for internal research use only.",
                    "source_confidence": 0.85,
                    "raw_summary": "",
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                }
            )
            event_rows.append(
                {
                    "report_id": report_id,
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "industry_name": "",
                    "report_date": publish_date,
                    "rating": "",
                    "rating_change": "",
                    "target_price": pd.NA,
                    "target_upside": pd.NA,
                    "industry_view": "",
                    "company_view": "",
                    "risk_summary": "",
                    "effective_start_date": publish_date,
                    "effective_end_date": pd.NA,
                    "auto_trade_enabled": False,
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                }
            )

    counts["import_pdf_count"] = len(source_rows)
    return PlatformReportImportFrames(
        sources=pd.DataFrame(source_rows, dtype=object),
        events=pd.DataFrame(event_rows, dtype=object),
        skipped=pd.DataFrame(skipped_rows, dtype=object),
        summary=counts,
    )


def run_tech_bottleneck_review_universe_report_pdf_platform_import(
    *,
    coverage_paths: Iterable[str | Path] | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    write_db: bool = True,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = [Path(path) for path in (coverage_paths or [DEFAULT_COVERAGE_PATH])]
    existing_paths = load_existing_local_pdf_paths(service=service) if write_db else set()

    built_parts: list[PlatformReportImportFrames] = []
    missing_coverage_paths: list[str] = []
    for path in paths:
        if not path.exists():
            missing_coverage_paths.append(str(path))
            continue
        coverage = pd.read_csv(path, dtype={"stock_code": str}, low_memory=False)
        built_parts.append(
            build_platform_report_import_frames(coverage, coverage_path=path, existing_local_pdf_paths=existing_paths)
        )

    sources = _concat([part.sources for part in built_parts])
    events = _concat([part.events for part in built_parts])
    skipped = _concat([part.skipped for part in built_parts])
    aggregate = _aggregate_summaries([part.summary for part in built_parts])
    duplicate_report_ids = int(sources["report_id"].duplicated().sum()) if not sources.empty else 0
    if duplicate_report_ids:
        sources = sources.drop_duplicates("report_id", keep="first")
        events = events.drop_duplicates(["report_id", "ts_code"], keep="first")
    aggregate["import_pdf_count"] = int(len(sources))
    aggregate["event_row_count"] = int(len(events))
    aggregate["duplicate_report_id_count"] = duplicate_report_ids
    aggregate["missing_coverage_file_count"] = len(missing_coverage_paths)
    aggregate["missing_coverage_files"] = missing_coverage_paths

    source_path = output / "review_universe_report_pdf_platform_import_sources.csv"
    event_path = output / "review_universe_report_pdf_platform_import_events.csv"
    skipped_path = output / "review_universe_report_pdf_platform_import_skipped.csv"
    sources.to_csv(source_path, index=False)
    events.to_csv(event_path, index=False)
    skipped.to_csv(skipped_path, index=False)

    db_result = None
    if write_db and not sources.empty:
        db_result = upsert_stock_report_sources_events(sources=sources, events=events, service=service)
    summary = {
        **aggregate,
        "task_name": TASK_NAME,
        "db_write_performed": bool(write_db and not sources.empty),
        "db_result": db_result,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "auto_trade_enabled_count": 0,
        "acceptance_decision": "review_universe_report_pdf_platform_import_ready",
    }
    guardrails = {
        "platform_report_import_performed": bool(write_db and not sources.empty),
        "source_coverage_rows": int(aggregate.get("coverage_stock_count", 0)),
        "pdf_rows_imported": int(len(sources)),
        "primary_source_collection_performed": False,
        "new_pdf_download_count": 0,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": _strategy_file_diff_clean(),
    }
    _write_json(output / "review_universe_report_pdf_platform_import_summary.json", summary)
    _write_json(output / "review_universe_report_pdf_platform_import_guardrails.json", guardrails)
    (output / "tech_bottleneck_review_universe_report_pdf_platform_import_v1_report.md").write_text(
        "\n".join(
            [
                "# Tech Bottleneck Review Universe Report PDF Platform Import v1",
                "",
                f"- imported PDF rows: {len(sources)}",
                f"- event rows: {len(events)}",
                f"- already indexed PDF paths skipped: {aggregate.get('already_indexed_pdf_path_count', 0)}",
                f"- missing PDF paths skipped: {aggregate.get('missing_pdf_path_count', 0)}",
                f"- DB write performed: {summary['db_write_performed']}",
                f"- used_for_signal_count: {guardrails['used_for_signal_count']}",
                f"- used_for_admission_count: {guardrails['used_for_admission_count']}",
                f"- strategy_file_diff_clean: {guardrails['strategy_file_diff_clean']}",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "guardrails": guardrails,
        "sources": sources,
        "events": events,
        "skipped": skipped,
        "paths": {
            "summary": str(output / "review_universe_report_pdf_platform_import_summary.json"),
            "guardrails": str(output / "review_universe_report_pdf_platform_import_guardrails.json"),
            "sources": str(source_path),
            "events": str(event_path),
            "skipped": str(skipped_path),
        },
    }


def load_existing_local_pdf_paths(*, service: str = SETTINGS.research_service) -> set[str]:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT source_url, COALESCE(metadata, '{}'::jsonb) AS metadata
            FROM research.stock_report_source
            WHERE source_url LIKE 'file://%%'
               OR metadata ? 'local_pdf_path'
               OR metadata ? 'pdf_path'
               OR metadata ? 'yanbaoke'
            """,
        )
    paths: set[str] = set()
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        yanbaoke = metadata.get("yanbaoke") if isinstance(metadata.get("yanbaoke"), dict) else {}
        for value in (
            yanbaoke.get("local_pdf_path"),
            metadata.get("local_pdf_path"),
            metadata.get("pdf_path"),
            row.get("source_url"),
        ):
            normalized = _normalize_pdf_path(value)
            if normalized.lower().endswith(".pdf"):
                paths.add(normalized)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import existing tech-bottleneck local report PDFs into platform report tables.")
    parser.add_argument("--coverage-path", action="append", dest="coverage_paths", help="Coverage CSV path. Can be passed multiple times.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--service", default=SETTINGS.research_service)
    parser.add_argument("--no-write-db", action="store_true", help="Only write candidate CSVs, do not upsert DB.")
    args = parser.parse_args(argv)
    result = run_tech_bottleneck_review_universe_report_pdf_platform_import(
        coverage_paths=args.coverage_paths,
        output_dir=args.output_dir,
        write_db=not args.no_write_db,
        service=args.service,
    )
    print(f"review_universe_report_pdf_platform_import|summary|{result['paths']['summary']}")
    print(f"review_universe_report_pdf_platform_import|sources|{result['paths']['sources']}")
    print(f"review_universe_report_pdf_platform_import|events|{result['paths']['events']}")
    print(f"review_universe_report_pdf_platform_import|imported|{result['summary']['import_pdf_count']}")
    return 0


def _split_paths(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(" | ") if part.strip()]


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _normalize_pdf_path(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("file://"):
        from urllib.parse import unquote, urlparse

        text = unquote(urlparse(text).path)
    if not text:
        return ""
    return str(Path(text).expanduser().resolve(strict=False))


def _clean_code(value: Any) -> str:
    match = re.search(r"(\d{6})", str(value or ""))
    return match.group(1) if match else str(value or "").strip()


def _ts_code(stock_code: str) -> str:
    suffix = "SH" if stock_code.startswith(("5", "6", "9")) else "SZ"
    return f"{stock_code}.{suffix}"


def _asset_id(stock_code: str) -> str:
    suffix = "SH" if stock_code.startswith(("5", "6", "9")) else "SZ"
    return f"CN:{suffix}:{stock_code}"


def _date_from_text(text: str) -> str:
    match = re.search(r"(20\d{2})[-_年.]?(\d{2})[-_月.]?(\d{2})", text)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _broker_from_title(title: str) -> str:
    text = Path(title).stem
    match = re.match(r"^(?:.*?20\d{6}[-_])?([^\\-_/]+证券|[^\\-_/]+基金|[^\\-_/]+研究所)", text)
    if match:
        return match.group(1).strip()
    parts = re.split(r"[-_]", text)
    for part in parts:
        if "证券" in part or "研究所" in part:
            return part.strip()
    return ""


def _stable_token(parts: list[str] | tuple[str, ...]) -> str:
    joined = "||".join(str(part) for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def _skipped(stock_code: str, stock_name: str, path: str, reason: str) -> dict[str, str]:
    return {"stock_code": stock_code, "stock_name": stock_name, "pdf_path": path, "skip_reason": reason}


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    return pd.concat(usable, ignore_index=True) if usable else pd.DataFrame()


def _aggregate_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    keys = {
        "coverage_stock_count",
        "candidate_pdf_path_count",
        "non_pdf_path_count",
        "missing_pdf_path_count",
        "duplicate_input_pdf_path_count",
        "already_indexed_pdf_path_count",
        "import_pdf_count",
    }
    return {key: int(sum(int(summary.get(key, 0)) for summary in summaries)) for key in keys}


def _stock_count(frame: pd.DataFrame) -> int:
    if "stock_code" not in frame.columns:
        return int(len(frame))
    return int(frame["stock_code"].astype(str).str.extract(r"(\d{6})", expand=False).dropna().nunique())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_file_diff_clean() -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--",
                "src/stock_research/tech_bottleneck_v1.py",
                "src/stock_research/tech_bottleneck_candidates.py",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and not result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
