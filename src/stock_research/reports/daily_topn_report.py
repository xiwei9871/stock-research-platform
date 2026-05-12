import json
from pathlib import Path
from typing import Any

import pandas as pd


TOPN_REPORT_COLUMNS = [
    "rank",
    "asset_id",
    "score_total",
    "score_version",
    "score_components",
]


def write_daily_topn_report(
    trade_date: str,
    score_version: str,
    top_scores: list[dict],
    output_dir: str | Path = "/Users/xiwei/stock_research/reports",
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    base = f"daily_topn_{trade_date}_{score_version}"
    markdown_path = path / f"{base}.md"
    csv_path = path / f"{base}.csv"

    rows = [_normalize_row(row, score_version) for row in top_scores]
    pd.DataFrame(rows, columns=TOPN_REPORT_COLUMNS).to_csv(csv_path, index=False)
    lines = [
        f"# {trade_date} TopN",
        "",
        f"- Score version: `{score_version}`",
        "- TopN 只是候选股票池，不是买入信号。",
        "",
    ]
    if rows:
        lines.extend(
            [
                "| Rank | Asset | Score | Components |",
                "| ---: | --- | ---: | --- |",
            ]
        )
        for row in rows:
            lines.append(
                f"| {row['rank']} | {row['asset_id']} | "
                f"{float(row['score_total']):.2f} | "
                f"{_format_components(json.loads(row['score_components']))} |"
            )
    else:
        lines.append("No TopN scores available.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"markdown_path": str(markdown_path), "csv_path": str(csv_path)}


def _normalize_row(row: dict[str, Any], score_version: str) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "asset_id": str(row["asset_id"]),
        "score_total": float(row["score_total"]),
        "score_version": str(row.get("score_version") or score_version),
        "score_components": json.dumps(
            row.get("score_components") or {},
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def _format_components(components: dict[str, Any]) -> str:
    if not components:
        return ""
    parts = []
    for name, value in sorted(components.items()):
        try:
            parts.append(f"{name}={float(value):.2f}")
        except (TypeError, ValueError):
            parts.append(f"{name}={value}")
    return ", ".join(parts)
