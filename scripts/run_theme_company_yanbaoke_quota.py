#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.theme_company_yanbaoke_quota import (
    build_allocation_slots,
    company_download_cap,
    existing_readable_report_keys,
    load_downloaded_manifest_uuids,
    select_download_queue,
)
from stock_research.yanbaoke_reports import filter_yanbaoke_reports, search_yanbaoke_reports


DEFAULT_BASE_URL = "https://stock.manqiaotechnology.com/api/research/theme-decomposition"


def _report_type_score(title: object) -> int:
    text = str(title or "").lower()
    if any(token in text for token in ("首次覆盖", "深度报告", "深度研究", "公司深度", "initiation")):
        return 30
    if any(token in text for token in ("年报", "中报", "季报", "业绩点评", "公司研究")):
        return 20
    if any(token in text for token in ("事件点评", "更新报告", "行业研究", "专题研究")):
        return 12
    return 6


def _fetch_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def _load_mappings(base_url: str) -> pd.DataFrame:
    themes = list(_fetch_json(f"{base_url}/themes").get("items") or [])
    rows: list[dict[str, object]] = []
    for theme in themes:
        theme_id = str(theme["theme_id"])
        companies = list(_fetch_json(f"{base_url}/themes/{theme_id}/companies").get("items") or [])
        for company in companies:
            node = company.get("mapped_node") if isinstance(company.get("mapped_node"), dict) else {}
            rows.append(
                {
                    "theme_id": theme_id,
                    "theme_name": str(theme.get("theme_name") or ""),
                    "theme_company_count": int(theme.get("company_count") or 0),
                    "mapping_id": str(company.get("mapping_id") or ""),
                    "ts_code": str(company.get("company_code") or ""),
                    "stock_name": str(company.get("company_name") or ""),
                    "node_id": str(company.get("mapped_node_id") or ""),
                    "node_name": str(node.get("node_name") or ""),
                    "mapping_type": str(company.get("mapping_type") or ""),
                    "beneficiary_tier": str(company.get("beneficiary_tier") or ""),
                    "priority_score": float(company.get("company_research_priority_score") or 0),
                    "priority_band": str(company.get("priority_band") or ""),
                    "recommended_action": str(company.get("recommended_action") or ""),
                }
            )
    return pd.DataFrame(rows)


def _load_coverage(ts_codes: list[str], service: str) -> tuple[pd.DataFrame, set[str], set[tuple[str, str, str, str]]]:
    with connect(service) as conn:
        coverage = fetch_all(
            conn,
            """
            WITH targets AS (SELECT unnest(%s::text[]) AS ts_code)
            SELECT t.ts_code,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '30 days') AS index30,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '60 days') AS index60,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '90 days') AS index90,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '120 days') AS index120,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '30 days' AND NULLIF(COALESCE(s.metadata #>> '{yanbaoke,local_pdf_path}', s.metadata->>'local_pdf_path', s.metadata->>'pdf_path'), '') IS NOT NULL) AS pdf30,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '60 days' AND NULLIF(COALESCE(s.metadata #>> '{yanbaoke,local_pdf_path}', s.metadata->>'local_pdf_path', s.metadata->>'pdf_path'), '') IS NOT NULL) AS pdf60,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '90 days' AND NULLIF(COALESCE(s.metadata #>> '{yanbaoke,local_pdf_path}', s.metadata->>'local_pdf_path', s.metadata->>'pdf_path'), '') IS NOT NULL) AS pdf90,
              COUNT(DISTINCT s.report_id) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '120 days' AND NULLIF(COALESCE(s.metadata #>> '{yanbaoke,local_pdf_path}', s.metadata->>'local_pdf_path', s.metadata->>'pdf_path'), '') IS NOT NULL) AS pdf120
            FROM targets t
            LEFT JOIN research.stock_report_event e ON e.ts_code = t.ts_code
            LEFT JOIN research.stock_report_source s USING (report_id)
            GROUP BY t.ts_code
            ORDER BY t.ts_code
            """,
            [ts_codes],
        )
        existing = fetch_all(
            conn,
            """
            SELECT e.ts_code, s.broker, s.publish_date, s.report_title,
                   s.metadata #>> '{yanbaoke,uuid}' AS yanbaoke_uuid,
                   NULLIF(COALESCE(s.metadata #>> '{yanbaoke,local_pdf_path}', s.metadata->>'local_pdf_path', s.metadata->>'pdf_path'), '') IS NOT NULL AS has_pdf
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            WHERE e.ts_code = ANY(%s::text[])
              AND s.publish_date >= CURRENT_DATE - INTERVAL '730 days'
            """,
            [ts_codes],
        )
    coverage_frame = pd.DataFrame(coverage)
    for column in ("index30", "index60", "index90", "index120", "pdf30", "pdf60", "pdf90", "pdf120"):
        coverage_frame[column] = pd.to_numeric(coverage_frame[column], errors="coerce").fillna(0).astype(int)
    existing_uuids = {str(row["yanbaoke_uuid"]) for row in existing if row.get("yanbaoke_uuid")}
    existing_keys = existing_readable_report_keys(existing)
    return coverage_frame, existing_uuids, existing_keys


def _company_inventory(mappings: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        mappings.groupby(["ts_code", "stock_name"], as_index=False)
        .agg(
            priority_score=("priority_score", "max"),
            theme_count=("theme_id", "nunique"),
            mapping_count=("mapping_id", "count"),
            themes=("theme_name", lambda values: "|".join(sorted(set(values)))),
        )
        .merge(coverage, on="ts_code", how="left")
    )
    theme_pdf = mappings[["theme_id", "ts_code"]].drop_duplicates().merge(
        coverage[["ts_code", "pdf120"]], on="ts_code", how="left"
    )
    theme_average = theme_pdf.groupby("theme_id")["pdf120"].mean().to_dict()
    scarcity_by_code: dict[str, float] = {}
    for row in mappings.to_dict("records"):
        score = 100.0 / (1.0 + float(theme_average.get(row["theme_id"], 0.0)))
        scarcity_by_code[row["ts_code"]] = max(scarcity_by_code.get(row["ts_code"], 0.0), score)
    grouped["scarcity_score"] = grouped["ts_code"].map(scarcity_by_code).fillna(0.0)
    grouped["company_cap"] = grouped.apply(company_download_cap, axis=1)
    return grouped.sort_values(["priority_score", "ts_code"], ascending=[False, True]).reset_index(drop=True)


def _discover_candidates(
    companies: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    search_size: int,
    sleep_seconds: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    audit: list[dict[str, object]] = []
    for index, company in enumerate(companies.to_dict("records"), start=1):
        code = str(company["ts_code"])
        name = str(company["stock_name"])
        try:
            result = search_yanbaoke_reports(
                keyword=name or code.split(".")[0],
                size=search_size,
                start_date=start_date,
                end_date=end_date,
            )
            filtered = filter_yanbaoke_reports(
                result["reports"],
                ts_code=code,
                stock_name=name,
                start_date=start_date,
                end_date=end_date,
            )
            for row in filtered.fillna("").to_dict("records"):
                publish_date = str(row.get("publish_date") or "")[:10]
                numeric_pages = pd.to_numeric(row.get("pagenum"), errors="coerce")
                pages = 0 if pd.isna(numeric_pages) else int(numeric_pages)
                report_score = _report_type_score(row.get("report_title") or row.get("title"))
                age = (date.fromisoformat(end_date) - date.fromisoformat(publish_date)).days if publish_date else 9999
                recency_score = 20 if age <= 120 else 8 if age <= 365 else 0
                page_score = 15 if pages >= 15 else 8 if pages >= 8 else 3 if pages >= 3 else 0
                enriched = dict(row)
                enriched.update(company)
                enriched["uuid"] = str(row.get("uuid") or "")
                enriched["report_title"] = str(row.get("report_title") or row.get("title") or "")
                enriched["publish_date"] = publish_date
                enriched["report_type_score"] = report_score
                enriched["candidate_score"] = round(
                    float(company["priority_score"]) + float(company["scarcity_score"]) * 0.15 + report_score + recency_score + page_score,
                    3,
                )
                candidates.append(enriched)
            audit.append(
                {
                    "ts_code": code,
                    "stock_name": name,
                    "status": "success",
                    "api_total": int(result.get("total") or 0),
                    "qualified_count": len(filtered),
                    "error": "",
                }
            )
        except Exception as exc:  # noqa: BLE001 - preserve discovery audit and continue.
            audit.append(
                {
                    "ts_code": code,
                    "stock_name": name,
                    "status": "error",
                    "api_total": 0,
                    "qualified_count": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
        print(f"discovery|{index}/{len(companies)}|{code}|qualified={audit[-1]['qualified_count']}", flush=True)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return pd.DataFrame(candidates), pd.DataFrame(audit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan Yanbaoke downloads for Theme Research companies.")
    parser.add_argument("--output-dir", default="outputs/research/theme_company_yanbaoke_20260723")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--service", default="stock_research")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--search-size", type=int, default=100)
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    parser.add_argument("--target-successes", type=int, default=474)
    parser.add_argument("--candidate-pool-size", type=int, default=550)
    parser.add_argument("--broker-cap", type=int, default=71)
    parser.add_argument("--reuse-discovered", action="store_true")
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    end = date.fromisoformat(args.end_date)
    start_date = args.start_date or (end - timedelta(days=365)).isoformat()

    mappings = _load_mappings(args.base_url)
    coverage, existing_uuids, existing_keys = _load_coverage(
        sorted(mappings["ts_code"].unique()), args.service
    )
    manifest_root = Path("outputs/research")
    manifest_paths: list[Path] = []
    for pattern in (
        "**/yanbaoke_downloaded_reports.csv",
        "**/yanbaoke_direct_uuid_downloads.csv",
        "**/yanbaoke_quota_burn_unique_downloads.csv",
        "**/yanbaoke_quota_burn_combined_downloads.csv",
    ):
        manifest_paths.extend(manifest_root.glob(pattern))
    existing_uuids.update(load_downloaded_manifest_uuids(manifest_paths))
    companies = _company_inventory(mappings, coverage)
    slots = build_allocation_slots(companies)
    discovered_path = output / "yanbaoke_discovered_candidates.csv"
    audit_path = output / "yanbaoke_discovery_audit.csv"
    if args.reuse_discovered and discovered_path.exists():
        discovered = pd.read_csv(discovered_path, dtype=object).fillna("")
        discovery_audit = (
            pd.read_csv(audit_path, dtype=object).fillna("")
            if audit_path.exists()
            else pd.DataFrame(columns=["ts_code", "stock_name", "status", "api_total", "qualified_count", "error"])
        )
        supplement_paths = [
            output / "yanbaoke_broker_supplement_candidates.csv",
            output / "yanbaoke_historical_supplement_candidates.csv",
            output / "yanbaoke_secondary_broker_candidates.csv",
            output / "yanbaoke_primary_broker_historical_candidates.csv",
        ]
        for supplement_path in supplement_paths:
            if supplement_path.exists() and supplement_path.stat().st_size:
                supplement = pd.read_csv(supplement_path, dtype=object).fillna("")
                discovered = pd.concat([discovered, supplement], ignore_index=True, sort=False).fillna("")
        discovered = discovered.drop_duplicates(subset=["uuid"], keep="first")
    else:
        discovered, discovery_audit = _discover_candidates(
            companies,
            start_date=start_date,
            end_date=args.end_date,
            search_size=args.search_size,
            sleep_seconds=args.sleep_seconds,
        )
    selected, replacements = select_download_queue(
        discovered,
        slots,
        target_successes=args.target_successes,
        candidate_pool_size=args.candidate_pool_size,
        broker_cap=args.broker_cap,
        existing_uuids=existing_uuids,
        existing_report_keys=existing_keys,
    )
    selected = selected.copy()
    replacements = replacements.copy()
    selected["queue_kind"] = "formal"
    replacements["queue_kind"] = "replacement"
    selected["quota_score"] = range(100000, 100000 - len(selected), -1)
    replacements["quota_score"] = range(10000, 10000 - len(replacements), -1)
    combined = pd.concat([selected, replacements], ignore_index=True, sort=False).fillna("")
    combined["report_id"] = combined["uuid"]
    combined["stock_code"] = combined["ts_code"]

    mappings.to_csv(output / "theme_company_mappings.csv", index=False)
    companies.to_csv(output / "theme_company_report_coverage.csv", index=False)
    slots.to_csv(output / "allocation_slots.csv", index=False)
    discovered.to_csv(output / "yanbaoke_discovered_candidates.csv", index=False)
    discovery_audit.to_csv(output / "yanbaoke_discovery_audit.csv", index=False)
    selected.to_csv(output / "yanbaoke_download_queue_474.csv", index=False)
    replacements.to_csv(output / "yanbaoke_replacement_queue.csv", index=False)
    combined.to_csv(output / "yanbaoke_download_candidate_pool.csv", index=False)

    summary = {
        "as_of": args.end_date,
        "theme_count": int(mappings["theme_id"].nunique()),
        "mapping_count": len(mappings),
        "company_count": int(companies["ts_code"].nunique()),
        "allocation_slots": len(slots),
        "allocation_buckets": slots["allocation_bucket"].value_counts().to_dict(),
        "discovered_candidates": len(discovered),
        "discovery_errors": int(discovery_audit["status"].eq("error").sum()),
        "formal_queue": len(selected),
        "replacement_queue": len(replacements),
        "candidate_pool": len(combined),
        "existing_uuid_exclusions": len(existing_uuids),
        "broker_max_formal": int(selected["broker"].value_counts().max()) if not selected.empty else 0,
    }
    (output / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "run_report.md").write_text(
        "\n".join(
            [
                "# Theme Company Yanbaoke Quota Plan",
                "",
                f"- Themes: {summary['theme_count']}",
                f"- Mappings: {summary['mapping_count']}",
                f"- Unique companies: {summary['company_count']}",
                f"- Allocation slots: {summary['allocation_slots']} ({summary['allocation_buckets']})",
                f"- Qualified candidates: {summary['discovered_candidates']}",
                f"- Formal queue: {summary['formal_queue']}",
                f"- Replacement queue: {summary['replacement_queue']}",
                f"- Discovery errors: {summary['discovery_errors']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    if len(selected) < args.target_successes:
        raise SystemExit(
            f"formal queue is short: selected={len(selected)} target={args.target_successes}"
        )


if __name__ == "__main__":
    main()
