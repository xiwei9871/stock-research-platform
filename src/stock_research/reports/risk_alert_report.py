from pathlib import Path
from typing import Any

import pandas as pd


RISK_ALERT_COLUMNS = [
    "trade_date",
    "scope",
    "asset_id",
    "alert_type",
    "severity",
    "message",
    "metric_name",
    "metric_value",
]

def generate_risk_alerts(
    trade_date: str,
    top_scores: list[dict[str, Any]],
    market_state: dict[str, Any] | None = None,
    sector_strength: pd.DataFrame | None = None,
    feature_snapshot: pd.DataFrame | None = None,
    weak_sector_rank_threshold: int = 20,
) -> pd.DataFrame:
    alerts: list[dict[str, Any]] = []
    date_text = _iso_date(trade_date)

    if market_state and _is_market_defensive(market_state):
        alerts.append(
            _alert(
                date_text,
                scope="market",
                asset_id="",
                alert_type="market_defensive",
                severity="high",
                message=f"Market state is {market_state.get('market_state')} with risk {market_state.get('risk_level')}.",
                metric_name="risk_level",
                metric_value=market_state.get("risk_level"),
            )
        )

    sectors = _sector_strength_map(sector_strength)
    features = _feature_map(feature_snapshot)
    for score in top_scores:
        asset_id = str(score.get("asset_id", ""))
        industry_code = score.get("industry_code")
        if industry_code and industry_code in sectors:
            sector = sectors[industry_code]
            rank = _float_or_none(sector.get("strength_rank"))
            if rank is not None and rank > weak_sector_rank_threshold:
                alerts.append(
                    _alert(
                        date_text,
                        scope="candidate",
                        asset_id=asset_id,
                        alert_type="sector_weak",
                        severity="medium",
                        message=f"Candidate industry {industry_code} ranks outside top {weak_sector_rank_threshold}.",
                        metric_name="strength_rank",
                        metric_value=rank,
                    )
                )
        alerts.extend(_candidate_feature_alerts(date_text, asset_id, features.get(asset_id, {})))

    if not alerts:
        return pd.DataFrame(columns=RISK_ALERT_COLUMNS)
    return pd.DataFrame(alerts, columns=RISK_ALERT_COLUMNS).reset_index(drop=True)


def write_risk_alert_report(
    alerts: pd.DataFrame,
    trade_date: str,
    output_dir: str | Path = "reports/risk_alerts",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_text = _iso_date(trade_date)
    markdown_path = output_path / f"risk_alerts_{date_text}.md"
    csv_path = output_path / f"risk_alerts_{date_text}.csv"

    ordered = _normalize_alerts(alerts)
    ordered.to_csv(csv_path, index=False)
    markdown_path.write_text(_render_markdown(ordered, date_text), encoding="utf-8")
    return {"markdown_path": markdown_path, "csv_path": csv_path}


def _candidate_feature_alerts(
    trade_date: str,
    asset_id: str,
    features: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts = []
    ret_5d = _float_or_none(features.get("ret_5d"))
    if ret_5d is not None and ret_5d >= 0.18:
        alerts.append(
            _alert(
                trade_date,
                "candidate",
                asset_id,
                "candidate_overheat",
                "medium",
                "5-day return is elevated; avoid chasing short-term heat.",
                "ret_5d",
                ret_5d,
            )
        )
    volatility = _float_or_none(features.get("volatility_20d"))
    if volatility is not None and volatility >= 0.05:
        alerts.append(
            _alert(
                trade_date,
                "candidate",
                asset_id,
                "candidate_high_volatility",
                "medium",
                "20-day volatility is elevated.",
                "volatility_20d",
                volatility,
            )
        )
    drawdown = _float_or_none(features.get("max_drawdown_20d"))
    if drawdown is not None and drawdown <= -0.15:
        alerts.append(
            _alert(
                trade_date,
                "candidate",
                asset_id,
                "candidate_deep_drawdown",
                "high",
                "20-day drawdown is deep.",
                "max_drawdown_20d",
                drawdown,
            )
        )
    amount = _float_or_none(features.get("amount_20d_avg"))
    if amount is not None and amount < 30_000_000.0:
        alerts.append(
            _alert(
                trade_date,
                "candidate",
                asset_id,
                "candidate_low_liquidity",
                "high",
                "20-day average amount is below liquidity floor.",
                "amount_20d_avg",
                amount,
            )
        )
    return alerts


def _alert(
    trade_date: str,
    scope: str,
    asset_id: str,
    alert_type: str,
    severity: str,
    message: str,
    metric_name: str,
    metric_value: Any,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "scope": scope,
        "asset_id": asset_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "metric_name": metric_name,
        "metric_value": metric_value,
    }


def _is_market_defensive(market_state: dict[str, Any]) -> bool:
    return market_state.get("market_state") == "defensive" or market_state.get("risk_level") == "high"


def _sector_strength_map(sector_strength: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if sector_strength is None or sector_strength.empty:
        return {}
    return {
        str(row["industry_code"]): row
        for row in sector_strength.to_dict("records")
        if row.get("industry_code") is not None
    }


def _feature_map(feature_snapshot: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if feature_snapshot is None or feature_snapshot.empty:
        return {}
    if {"asset_id", "feature_name", "feature_value"}.issubset(feature_snapshot.columns):
        wide = feature_snapshot.pivot_table(
            index="asset_id",
            columns="feature_name",
            values="feature_value",
            aggfunc="last",
        )
        return {str(asset_id): row.dropna().to_dict() for asset_id, row in wide.iterrows()}
    return {
        str(row["asset_id"]): {key: value for key, value in row.items() if key != "asset_id"}
        for row in feature_snapshot.to_dict("records")
        if row.get("asset_id") is not None
    }


def _normalize_alerts(alerts: pd.DataFrame) -> pd.DataFrame:
    if alerts.empty:
        return pd.DataFrame(columns=RISK_ALERT_COLUMNS)
    return alerts[RISK_ALERT_COLUMNS].copy()


def _render_markdown(alerts: pd.DataFrame, trade_date: str) -> str:
    lines = [
        f"# {trade_date} Risk Alerts",
        "",
        "- 风险提示只作为研究过滤器，不构成交易指令。",
        "",
    ]
    if alerts.empty:
        lines.append("No risk alerts.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Severity | Scope | Asset | Type | Metric | Value | Message |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in alerts.itertuples(index=False):
        lines.append(
            "| "
            f"{row.severity} | "
            f"{row.scope} | "
            f"{row.asset_id} | "
            f"{row.alert_type} | "
            f"{row.metric_name} | "
            f"{_format_value(row.metric_value)} | "
            f"{row.message} |"
        )
    return "\n".join(lines) + "\n"


def _format_value(value: Any) -> str:
    number = _float_or_none(value)
    if number is not None:
        return f"{number:.4f}"
    return "" if value is None else str(value)


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
