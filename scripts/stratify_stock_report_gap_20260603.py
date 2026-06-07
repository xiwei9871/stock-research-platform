from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


BASE = Path("outputs/research/stock_report_web_gap_20260603")
OUT = BASE / "remaining_gap_stratification_20260603"
START_DATE = "2025-01-01"
END_DATE = "2026-06-03"
TOTAL_A_SHARES = 5201


def _status_map(path: Path, provider: str) -> pd.DataFrame:
    columns = ["ts_code", f"{provider}_status", f"{provider}_note"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, dtype={"ts_code": "string"}, low_memory=False)
    if df.empty or "ts_code" not in df.columns:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, str]] = []
    for ts_code, group in df.groupby("ts_code", dropna=True):
        statuses = sorted(set(group.get("collection_status", pd.Series(dtype=str)).astype(str)))
        notes = sorted(set(group.get("collection_note", pd.Series(dtype=str)).dropna().astype(str)))[:3]
        rows.append(
            {
                "ts_code": ts_code,
                f"{provider}_status": ",".join(statuses),
                f"{provider}_note": " | ".join(notes),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _classify(row: pd.Series) -> str:
    if bool(row["in_sina_batch001"]):
        return "sina_slow_retry_low_2025plus_yield"
    if bool(row["in_sina_probe50"]):
        return "sina_probe_low_increment_after_date_filter"
    if bool(row["in_sina_http456_retry_pool"]):
        return "sina_http456_retry_candidate"
    sampled_statuses = [
        str(row.get("stockstar_sample_status", "")),
        str(row.get("cfi_head_sample_status", "")),
        str(row.get("cfi_random_sample_status", "")),
    ]
    if any(status and status != "nan" for status in sampled_statuses):
        return "sampled_third_sources_no_2025plus"
    sohu = str(row.get("sohu_full_status", ""))
    sina = str(row.get("sina_full_status", ""))
    if "no_result" in sohu and (not sina or sina == "nan"):
        return "sohu_no_result_sina_not_attempted_or_filtered"
    if bool(row["is_st_name"]):
        return "st_or_special_treatment_low_priority"
    return "unverified_remaining_gap"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_candidates = pd.read_csv(
        BASE / "akshare_no_result_candidates.csv",
        dtype={"ts_code": "string"},
        low_memory=False,
    ).drop_duplicates("ts_code")

    with connect(SETTINGS.research_service) as conn:
        covered_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT ts_code
            FROM research.stock_report_event
            WHERE report_date >= %s AND report_date <= %s
            """,
            [START_DATE, END_DATE],
        )
        total_rows = fetch_all(
            conn,
            """
            SELECT COUNT(*) AS rows, COUNT(DISTINCT ts_code) AS stocks
            FROM research.stock_report_event
            WHERE report_date >= %s AND report_date <= %s
            """,
            [START_DATE, END_DATE],
        )

    covered = {row["ts_code"] for row in covered_rows}
    remaining = all_candidates[~all_candidates["ts_code"].isin(covered)].copy()

    status_specs = [
        ("sina_full", BASE / "full_sina_report_page_2025_live/stock_report_web_source_collection.csv"),
        ("sohu_full", BASE / "full_sohu_jlp_rating_2025_live/stock_report_web_source_collection.csv"),
        ("sina_probe50", BASE / "sina_http456_probe50_sleep2_20260603/stock_report_web_source_collection.csv"),
        ("sina_batch001", BASE / "sina_missing_batch001_200_sleep2_20260603/stock_report_web_source_collection.csv"),
        ("stockstar_sample", BASE / "stockstar_rating_sample200_2025_live/stockstar_rating_collection_sample200.csv"),
        ("cfi_head_sample", BASE / "cfi_ybyl_sample200_2025_live/cfi_ybyl_collection_sample200.csv"),
        ("cfi_random_sample", BASE / "cfi_ybyl_random_sample200_2025_live/cfi_ybyl_collection_random_sample200.csv"),
    ]
    for provider, path in status_specs:
        remaining = remaining.merge(_status_map(path, provider), on="ts_code", how="left")

    retry_plan = pd.read_csv(BASE / "stock_report_search_plan_sina_http456_retry.csv", dtype={"ts_code": "string"}, low_memory=False)
    probe_plan = pd.read_csv(BASE / "stock_report_search_plan_sina_http456_probe50.csv", dtype={"ts_code": "string"}, low_memory=False)
    batch001_plan = pd.read_csv(BASE / "stock_report_search_plan_sina_missing_batch001_200.csv", dtype={"ts_code": "string"}, low_memory=False)
    remaining["in_sina_http456_retry_pool"] = remaining["ts_code"].isin(set(retry_plan["ts_code"].dropna()))
    remaining["in_sina_probe50"] = remaining["ts_code"].isin(set(probe_plan["ts_code"].dropna()))
    remaining["in_sina_batch001"] = remaining["ts_code"].isin(set(batch001_plan["ts_code"].dropna()))
    remaining["is_st_name"] = remaining["stock_name"].astype(str).str.contains("ST", case=False, na=False)
    remaining["gap_category"] = remaining.apply(_classify, axis=1)

    counts = remaining["gap_category"].value_counts().rename_axis("gap_category").reset_index(name="stocks")
    industry_counts = (
        remaining.groupby(["gap_category", "industry_name"], dropna=False)
        .size()
        .reset_index(name="stocks")
        .sort_values(["gap_category", "stocks"], ascending=[True, False])
    )

    summary = {
        "db_event_rows_2025_to_20260603": int(total_rows[0]["rows"]),
        "db_covered_stocks_2025_to_20260603": int(total_rows[0]["stocks"]),
        "db_coverage_pct": round(total_rows[0]["stocks"] / TOTAL_A_SHARES * 100, 2),
        "akshare_no_result_input_stocks": int(all_candidates["ts_code"].nunique()),
        "remaining_gap_stocks_after_all_writes": int(remaining["ts_code"].nunique()),
        "category_counts": dict(zip(counts["gap_category"], counts["stocks"])),
    }

    remaining.to_csv(OUT / "remaining_gap_stratification.csv", index=False)
    counts.to_csv(OUT / "remaining_gap_category_counts.csv", index=False)
    industry_counts.to_csv(OUT / "remaining_gap_category_industry_counts.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report = [
        "# A股研报剩余缺口分层报告",
        "",
        "## 当前覆盖",
        f"- 统计区间：{START_DATE} 至 {END_DATE}",
        f"- DB 研报事件：{summary['db_event_rows_2025_to_20260603']}",
        f"- DB 覆盖股票：{summary['db_covered_stocks_2025_to_20260603']} / {TOTAL_A_SHARES} = {summary['db_coverage_pct']}%",
        f"- akshare_no_result 输入股票：{summary['akshare_no_result_input_stocks']}",
        f"- 当前仍缺口股票：{summary['remaining_gap_stocks_after_all_writes']}",
        "",
        "## 缺口分层",
    ]
    for _, row in counts.iterrows():
        report.append(f"- {row['gap_category']}: {int(row['stocks'])}")
    report.extend(
        [
            "",
            "## 已验证源站结论",
            "- Sohu JLP：全量可跑，稳定；已入库有效结果。",
            "- Sina：并发会触发 HTTP 456；冷却后 workers=1 + sleep=2s 可稳定访问，但对仍缺口股票的 2025+ 增量偏低。",
            "- 证券之星：剩余缺口样本 200 只，0 命中，不建议全量。",
            "- 中财网：前 200 和随机 200 样本均 0 命中，不建议全量。",
            "- 同花顺 F10：直接访问 forbidden，不建议作为当前批量源。",
            "",
            "## 输出文件",
            "- remaining_gap_stratification.csv",
            "- remaining_gap_category_counts.csv",
            "- remaining_gap_category_industry_counts.csv",
            "- summary.json",
        ]
    )
    (OUT / "remaining_gap_stratification_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output_dir {OUT}")


if __name__ == "__main__":
    main()
