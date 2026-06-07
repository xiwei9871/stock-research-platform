from __future__ import annotations

from pathlib import Path

import pandas as pd


OUT = Path("outputs/research/stock_report_web_gap_20260603/source_candidate_validation_20260603")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "source": "Sohu JLP rating page",
            "domain": "q.stock.sohu.com",
            "access_pattern": "https://q.stock.sohu.com/cn/{code}/index_kp.shtml",
            "status": "validated_full_run",
            "sample_or_full_result": "full run: 627 stocks, 1583 rows, 0 fetch_error",
            "incremental_value": "high for first gap fill; already ingested",
            "next_action": "keep as stable source; rerun periodically for new dates",
            "priority": 1,
        },
        {
            "source": "Sina research report page",
            "domain": "stock.finance.sina.com.cn",
            "access_pattern": "https://stock.finance.sina.com.cn/stock/go.php/vReport_List/kind/search/index.phtml?symbol={market}{code}&t1=all",
            "status": "validated_rate_limited",
            "sample_or_full_result": "full run hit HTTP456; slow probe 50/50 page hits; batch001 200 stocks only 3 stock increments after date filter",
            "incremental_value": "medium for record density, low-to-medium for remaining stock coverage",
            "next_action": "run low-priority batches with workers=1 sleep>=2s and fetch-error fuse",
            "priority": 2,
        },
        {
            "source": "Stockstar rating page",
            "domain": "stock.quote.stockstar.com",
            "access_pattern": "https://stock.quote.stockstar.com/corp/rating_{code}.shtml",
            "status": "validated_low_value_for_remaining_gap",
            "sample_or_full_result": "remaining-gap sample200: 0 found stocks",
            "incremental_value": "low after Sohu/Sina",
            "next_action": "do not full-run unless target universe changes",
            "priority": 8,
        },
        {
            "source": "CFI research overview",
            "domain": "quote.cfi.cn",
            "access_pattern": "https://quote.cfi.cn/quote.aspx?client=pc&contenttype=ybyl&searchcode={code}",
            "status": "validated_low_value_for_remaining_gap",
            "sample_or_full_result": "head sample200: 0 found; random sample200: 0 found",
            "incremental_value": "low after Sohu/Sina",
            "next_action": "do not full-run unless target universe changes",
            "priority": 8,
        },
        {
            "source": "10jqka F10 worth page",
            "domain": "basic.10jqka.com.cn",
            "access_pattern": "https://basic.10jqka.com.cn/{code}/worth.html",
            "status": "blocked",
            "sample_or_full_result": "direct curl returned Nginx forbidden",
            "incremental_value": "unknown",
            "next_action": "skip for batch collection unless a compliant public endpoint is found",
            "priority": 9,
        },
        {
            "source": "Bing/Baidu source-directed search",
            "domain": "search engines",
            "access_pattern": "site-directed public search",
            "status": "validated_low_precision",
            "sample_or_full_result": "Baidu security validation; Bing site search failed positive controls",
            "incremental_value": "low and expensive",
            "next_action": "do not use as full-run path",
            "priority": 10,
        },
        {
            "source": "Hexun stockdata / research pages",
            "domain": "hexun.com",
            "access_pattern": "stockdata.stock.hexun.com / yanbao.stock.hexun.com",
            "status": "invalid_access",
            "sample_or_full_result": "SSL hostname mismatch or unresolved host in quick validation",
            "incremental_value": "unknown",
            "next_action": "skip until a valid public URL pattern is identified",
            "priority": 9,
        },
        {
            "source": "CNINFO / exchange filings",
            "domain": "cninfo.com.cn / exchanges",
            "access_pattern": "company announcements and filings, not analyst reports",
            "status": "parallel_fundamental_source",
            "sample_or_full_result": "useful for annual/quarterly report PDFs, not brokerage-research coverage",
            "incremental_value": "high for fundamental fields, not counted as analyst-report coverage",
            "next_action": "keep separate from analyst report pipeline",
            "priority": 3,
        },
        {
            "source": "Paid or semi-paid report libraries",
            "domain": "hibor, wind, ifind, choice-like sources",
            "access_pattern": "often login/paywall/API contract required",
            "status": "requires_commercial_access_review",
            "sample_or_full_result": "not suitable for blind public scraping",
            "incremental_value": "potentially high if licensed",
            "next_action": "only evaluate through compliant/licensed access",
            "priority": 6,
        },
    ]
    frame = pd.DataFrame(rows).sort_values(["priority", "source"])
    frame.to_csv(OUT / "source_candidate_validation.csv", index=False)
    report = [
        "# 新研报源候选验证清单",
        "",
        "## 推荐执行顺序",
        "1. 保留 Sohu 为稳定源，后续增量刷新。",
        "2. Sina 只用低速批处理继续补充，不再并发全量打。",
        "3. 第三源暂不全量：证券之星、中财网对当前剩余缺口样本均 0 命中。",
        "4. 年报/季报 PDF 字段抽取继续作为独立基本面增强，不与券商研报覆盖混算。",
        "",
        "## 候选源表",
    ]
    for _, row in frame.iterrows():
        report.append(
            f"- {row['source']} ({row['status']}): {row['sample_or_full_result']}；next={row['next_action']}"
        )
    (OUT / "source_candidate_validation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"rows {len(frame)}")
    print(f"output_dir {OUT}")


if __name__ == "__main__":
    main()
