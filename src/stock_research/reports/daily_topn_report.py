from pathlib import Path

import pandas as pd


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

    pd.DataFrame(top_scores).to_csv(csv_path, index=False)
    lines = [f"# {trade_date} TopN", "", f"- Score version: `{score_version}`", ""]
    for row in top_scores:
        lines.append(f"{row['rank']}. {row['asset_id']} score={row['score_total']}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"markdown_path": str(markdown_path), "csv_path": str(csv_path)}
