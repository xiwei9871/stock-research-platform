from pathlib import Path
from typing import Any

import pandas as pd


POSITION_REVIEW_COLUMNS = [
    "trade_date",
    "asset_id",
    "weight",
    "holding_days",
    "rank",
    "score_total",
    "review_status",
    "review_reasons",
    "risk_alerts",
]


def generate_position_review(
    trade_date: str,
    positions: list[dict[str, Any]],
    top_scores: list[dict[str, Any]],
    market_state: dict[str, Any] | None = None,
    risk_alerts: pd.DataFrame | None = None,
    top_n: int = 30,
) -> pd.DataFrame:
    date_text = _iso_date(trade_date)
    score_map = {str(row.get("asset_id")): row for row in top_scores}
    risk_map = _risk_alert_map(risk_alerts)
    market_defensive = _market_defensive(market_state)

    rows = []
    for position in positions:
        asset_id = str(position.get("asset_id", ""))
        score = score_map.get(asset_id, {})
        rank = _int_or_none(score.get("rank"))
        asset_risks = risk_map.get(asset_id, [])
        reasons = []
        if market_defensive:
            reasons.append("market_defensive")
        if rank is None:
            reasons.append("missing_score")
        elif rank > top_n:
            reasons.append("out_of_top_n")
        else:
            reasons.append("inside_top_n")
        if any(item["severity"] == "high" for item in asset_risks):
            reasons.append("high_risk_alert")

        rows.append(
            {
                "trade_date": date_text,
                "asset_id": asset_id,
                "weight": _float_or_none(position.get("weight")),
                "holding_days": _int_or_none(position.get("holding_days")),
                "rank": rank,
                "score_total": _float_or_none(score.get("score_total")),
                "review_status": _review_status(reasons),
                "review_reasons": ",".join(reasons),
                "risk_alerts": ",".join(item["alert_type"] for item in asset_risks),
            }
        )
    return pd.DataFrame(rows, columns=POSITION_REVIEW_COLUMNS)


def write_position_review_report(
    review: pd.DataFrame,
    trade_date: str,
    output_dir: str | Path = "reports/position_review",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_text = _iso_date(trade_date)
    markdown_path = output_path / f"position_review_{date_text}.md"
    csv_path = output_path / f"position_review_{date_text}.csv"

    normalized = _normalize_review(review)
    normalized.to_csv(csv_path, index=False)
    markdown_path.write_text(_render_markdown(normalized, date_text), encoding="utf-8")
    return {"markdown_path": markdown_path, "csv_path": csv_path}


def _review_status(reasons: list[str]) -> str:
    if "high_risk_alert" in reasons or "out_of_top_n" in reasons or "missing_score" in reasons:
        return "blocked"
    if "market_defensive" in reasons:
        return "monitor"
    return "review"


def _risk_alert_map(risk_alerts: pd.DataFrame | None) -> dict[str, list[dict[str, str]]]:
    if risk_alerts is None or risk_alerts.empty:
        return {}
    result: dict[str, list[dict[str, str]]] = {}
    for row in risk_alerts.to_dict("records"):
        asset_id = row.get("asset_id")
        if not asset_id:
            continue
        result.setdefault(str(asset_id), []).append(
            {
                "alert_type": str(row.get("alert_type", "")),
                "severity": str(row.get("severity", "")),
            }
        )
    return result


def _market_defensive(market_state: dict[str, Any] | None) -> bool:
    if not market_state:
        return False
    return market_state.get("market_state") == "defensive" or market_state.get("risk_level") == "high"


def _normalize_review(review: pd.DataFrame) -> pd.DataFrame:
    if review.empty:
        return pd.DataFrame(columns=POSITION_REVIEW_COLUMNS)
    return review[POSITION_REVIEW_COLUMNS].copy()


def _render_markdown(review: pd.DataFrame, trade_date: str) -> str:
    lines = [
        f"# {trade_date} Position Review",
        "",
        "- 持仓复核只作为人工检查清单，不构成交易指令。",
        "",
    ]
    if review.empty:
        lines.append("No positions to review.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Asset | Status | Rank | Score | Weight | Holding Days | Reasons | Risks |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in review.itertuples(index=False):
        lines.append(
            "| "
            f"{row.asset_id} | "
            f"{row.review_status} | "
            f"{_format_int(row.rank)} | "
            f"{_format_number(row.score_total)} | "
            f"{_format_pct(row.weight)} | "
            f"{_format_int(row.holding_days)} | "
            f"{row.review_reasons} | "
            f"{row.risk_alerts} |"
        )
    return "\n".join(lines) + "\n"


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _int_or_none(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _format_number(value: object) -> str:
    number = _float_or_none(value)
    return "" if number is None else f"{number:.2f}"


def _format_pct(value: object) -> str:
    number = _float_or_none(value)
    return "" if number is None else f"{number * 100:.2f}%"


def _format_int(value: object) -> str:
    number = _int_or_none(value)
    return "" if number is None else str(number)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
