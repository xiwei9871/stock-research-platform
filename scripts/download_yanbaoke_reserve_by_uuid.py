#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.yanbaoke_reports import download_yanbaoke_report_pdf


def _load_api_key(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = payload.get("yanbaoke", {}).get("api_key", "")
    if not key:
        raise ValueError(f"Yanbaoke API key missing in {path}")
    return str(key)


def _load_manifest(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _existing_uuids(paths: list[Path]) -> set[str]:
    uuids: set[str] = set()
    for path in paths:
        frame = _load_manifest(path)
        if frame.empty or "uuid" not in frame.columns:
            continue
        status = frame.get("status", pd.Series(dtype=object)).astype(str)
        uuids.update(frame.loc[status.eq("downloaded"), "uuid"].dropna().astype(str))
    return uuids


def _select_candidates(
    reserve: pd.DataFrame,
    *,
    existing: set[str],
    max_downloads: int,
    max_per_stock: int,
    max_broker_share: float,
) -> pd.DataFrame:
    frame = reserve.copy()
    frame["uuid"] = frame.get("report_id", pd.Series(dtype=object)).astype(str)
    frame = frame[frame["uuid"].notna() & frame["uuid"].ne("") & frame["uuid"].ne("nan")].copy()
    frame = frame[~frame["uuid"].isin(existing)].copy()
    frame = frame.drop_duplicates(subset=["uuid"], keep="first").copy()
    if frame.empty:
        return frame

    sort_cols = [col for col in ["quota_score", "priority_score", "report_date"] if col in frame.columns]
    ascending = [False if col != "report_date" else False for col in sort_cols]
    if sort_cols:
        frame = frame.sort_values(sort_cols, ascending=ascending, na_position="last")

    broker_cap = max(1, int(max_downloads * max_broker_share)) if max_broker_share > 0 else max_downloads
    stock_counts: dict[str, int] = {}
    broker_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for row in frame.fillna("").to_dict("records"):
        if len(rows) >= max_downloads:
            break
        ts_code = str(row.get("ts_code") or row.get("stock_code") or "")
        broker = str(row.get("broker") or "")
        if ts_code and stock_counts.get(ts_code, 0) >= max_per_stock:
            continue
        if broker and broker_counts.get(broker, 0) >= broker_cap:
            continue
        rows.append(row)
        if ts_code:
            stock_counts[ts_code] = stock_counts.get(ts_code, 0) + 1
        if broker:
            broker_counts[broker] = broker_counts.get(broker, 0) + 1
    return pd.DataFrame(rows)


def _write_outputs(output_dir: Path, rows: list[dict[str, Any]], candidates: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_dir / "yanbaoke_direct_uuid_downloads.csv", index=False)
    candidates.to_csv(output_dir / "yanbaoke_direct_uuid_candidates.csv", index=False)
    downloaded = sum(1 for row in rows if row.get("status") == "downloaded")
    errors = sum(1 for row in rows if row.get("status") == "error")
    (output_dir / "yanbaoke_direct_uuid_report.md").write_text(
        "\n".join(
            [
                "# Yanbaoke Direct UUID Download",
                "",
                f"- Candidate rows: {len(candidates)}",
                f"- Attempted rows: {len(rows)}",
                f"- Downloaded PDFs: {downloaded}",
                f"- Errors: {errors}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _downloaded_uuid_count(rows: list[dict[str, Any]]) -> int:
    return len({str(row.get("uuid") or "") for row in rows if row.get("status") == "downloaded" and row.get("uuid")})


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Yanbaoke reports directly from reserve UUIDs.")
    parser.add_argument("--reserve-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--download-dir")
    parser.add_argument("--api-key-json", default="config/local_secrets.json")
    parser.add_argument("--existing-manifest", action="append", default=[])
    parser.add_argument("--max-downloads", type=int, default=100)
    parser.add_argument("--target-successes", type=int, default=None)
    parser.add_argument("--max-per-stock", type=int, default=3)
    parser.add_argument("--max-broker-share", type=float, default=0.25)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--flush-every", type=int, default=5)
    args = parser.parse_args()

    reserve = pd.read_csv(args.reserve_path)
    output_dir = Path(args.output_dir)
    download_dir = Path(args.download_dir) if args.download_dir else output_dir / "pdfs"
    existing = _existing_uuids([Path(path) for path in args.existing_manifest] + [output_dir / "yanbaoke_direct_uuid_downloads.csv"])
    candidates = _select_candidates(
        reserve,
        existing=existing,
        max_downloads=args.max_downloads,
        max_per_stock=args.max_per_stock,
        max_broker_share=args.max_broker_share,
    )
    api_key = _load_api_key(Path(args.api_key_json))
    rows: list[dict[str, Any]] = []
    prior = _load_manifest(output_dir / "yanbaoke_direct_uuid_downloads.csv")
    if not prior.empty:
        rows.extend(prior.fillna("").to_dict("records"))
    attempted_count = 0

    for idx, row in enumerate(candidates.fillna("").to_dict("records"), start=1):
        downloaded_so_far = _downloaded_uuid_count(rows)
        if args.target_successes is not None and downloaded_so_far >= args.target_successes:
            break
        attempted_count = idx
        uuid = str(row.get("uuid") or row.get("report_id") or "")
        record = dict(row)
        record["uuid"] = uuid
        record["attempted_at_epoch"] = time.time()
        try:
            download = download_yanbaoke_report_pdf(uuid=uuid, output_dir=download_dir, api_key=api_key)
            record.update(download)
        except Exception as exc:  # noqa: BLE001 - keep batch running and audit the failure.
            record.update({"status": "error", "error_type": type(exc).__name__, "error_message": str(exc)})
        rows.append(record)
        if idx % max(1, args.flush_every) == 0:
            _write_outputs(output_dir, rows, candidates)
            downloaded = sum(1 for item in rows if item.get("status") == "downloaded")
            print(f"progress attempted={idx}/{len(candidates)} downloaded={downloaded}", flush=True)
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    _write_outputs(output_dir, rows, candidates)
    downloaded = sum(1 for item in rows if item.get("status") == "downloaded")
    errors = sum(1 for item in rows if item.get("status") == "error")
    unique_downloaded = _downloaded_uuid_count(rows)
    print(f"done attempted={attempted_count} downloaded={downloaded} unique_downloaded={unique_downloaded} errors={errors}")


if __name__ == "__main__":
    main()
