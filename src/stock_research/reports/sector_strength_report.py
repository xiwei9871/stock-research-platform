from pathlib import Path

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


SECTOR_STRENGTH_COLUMNS = [
    "trade_date",
    "industry_system",
    "industry_code",
    "industry_name",
    "ret_5d",
    "ret_20d",
    "amount_ratio_5_20",
    "strength_score",
    "strength_rank",
]


def load_sector_strength_bars(
    start_date: str,
    end_date: str,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT
            trade_date,
            industry_system,
            industry_code,
            industry_name,
            close,
            amount
        FROM market.industry_daily_bar
        WHERE industry_system = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY industry_code, trade_date
    """
    params = [industry_system, start_date, end_date]
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def calc_sector_strength(
    bars: pd.DataFrame,
    trade_date: str,
    top_n: int = 20,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=SECTOR_STRENGTH_COLUMNS)

    frame = bars.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame = frame.sort_values(["industry_system", "industry_code", "trade_date"])

    grouped = frame.groupby(["industry_system", "industry_code"], group_keys=False)
    frame["ret_5d"] = grouped["close"].pct_change(5)
    frame["ret_20d"] = grouped["close"].pct_change(20)
    amount_5 = grouped["amount"].rolling(5).mean().reset_index(level=[0, 1], drop=True)
    amount_20 = grouped["amount"].rolling(20).mean().reset_index(level=[0, 1], drop=True)
    frame["amount_ratio_5_20"] = amount_5 / amount_20

    latest = frame[frame["trade_date"] == _iso_date(trade_date)].copy()
    if latest.empty:
        return pd.DataFrame(columns=SECTOR_STRENGTH_COLUMNS)

    latest["ret_5d_rank_score"] = _rank_score(latest["ret_5d"])
    latest["ret_20d_rank_score"] = _rank_score(latest["ret_20d"])
    latest["amount_rank_score"] = _rank_score(latest["amount_ratio_5_20"])
    latest["strength_score"] = (
        latest["ret_20d_rank_score"] * 0.5
        + latest["ret_5d_rank_score"] * 0.3
        + latest["amount_rank_score"] * 0.2
    )
    latest = latest.sort_values(
        ["strength_score", "ret_20d", "ret_5d", "industry_code"],
        ascending=[False, False, False, True],
    ).head(top_n)
    latest["strength_rank"] = range(1, len(latest) + 1)
    return latest[SECTOR_STRENGTH_COLUMNS].reset_index(drop=True)


def write_sector_strength_report(
    strength: pd.DataFrame,
    trade_date: str,
    industry_system: str = "csrc",
    output_dir: str | Path = "reports/sector_strength",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_text = _iso_date(trade_date)
    stem = f"sector_strength_{date_text}_{industry_system}"
    markdown_path = output_path / f"{stem}.md"
    csv_path = output_path / f"{stem}.csv"

    ordered = _normalize_strength(strength)
    ordered.to_csv(csv_path, index=False)
    markdown_path.write_text(
        _render_markdown(ordered, date_text, industry_system),
        encoding="utf-8",
    )
    return {"markdown_path": markdown_path, "csv_path": csv_path}


def _normalize_strength(strength: pd.DataFrame) -> pd.DataFrame:
    if strength.empty:
        return pd.DataFrame(columns=SECTOR_STRENGTH_COLUMNS)
    return strength[SECTOR_STRENGTH_COLUMNS].copy()


def _render_markdown(
    strength: pd.DataFrame,
    trade_date: str,
    industry_system: str,
) -> str:
    lines = [
        f"# {trade_date} Sector Strength",
        "",
        f"- Industry system: `{industry_system}`",
        "- 仅作为研究观察，不构成交易指令。",
        "",
    ]
    if strength.empty:
        lines.append("No sector strength data available.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Rank | Code | Name | Ret 5D | Ret 20D | Amount 5/20 | Score |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in strength.itertuples(index=False):
        lines.append(
            "| "
            f"{row.strength_rank} | "
            f"{row.industry_code} | "
            f"{row.industry_name} | "
            f"{_format_pct(row.ret_5d)} | "
            f"{_format_pct(row.ret_20d)} | "
            f"{_format_number(row.amount_ratio_5_20)} | "
            f"{_format_number(row.strength_score)} |"
        )
    return "\n".join(lines) + "\n"


def _rank_score(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True, ascending=True).fillna(0.0) * 100.0


def _format_pct(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _format_number(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2f}"


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
