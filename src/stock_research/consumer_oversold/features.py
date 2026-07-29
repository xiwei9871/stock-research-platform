from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal

import numpy as np
import pandas as pd


STRICT_NUMERIC_TYPES = (int, float, np.integer, np.floating, Decimal)


BAR_COLUMNS = ("asset_id", "trade_date", "close")
MEMBERSHIP_COLUMNS = ("asset_id", "consumer_subindustry")
SCORE_COLUMNS = (
    "max_drawdown_12m",
    "return_6m",
    "relative_return_6m",
    "valuation_depression_percentile",
    "distance_ma120",
    "distance_ma250",
)
PRICE_OUTPUT_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "latest_close",
    "history_bars",
    "price_history_complete",
    "return_6m",
    "return_60d",
    "max_drawdown_12m",
    "rebound_from_low_60d",
    "ma120",
    "ma250",
    "distance_ma120",
    "distance_ma250",
    "consumer_subindustry",
    "industry_peer_count",
    "industry_peer_count_60d",
    "industry_return_6m",
    "relative_return_6m",
    "industry_return_60d",
    "relative_return_60d",
    "relative_return_coverage",
    "relative_return_coverage_60d",
]

FINANCE_COLUMNS = (
    "asset_id",
    "report_period",
    "announcement_date",
    "revenue_ttm",
    "revenue_growth",
    "np_parent_ttm",
    "profit_growth",
    "gross_margin",
    "net_margin",
    "roe",
    "ocf_to_np",
    "debt_ratio",
    "equity_parent",
    "operating_cash_flow",
)
FINANCE_NUMERIC_COLUMNS = FINANCE_COLUMNS[3:]
NORMAL_FUNDAMENTAL_COLUMNS = (
    "revenue_growth",
    "profit_growth",
    "gross_margin",
    "net_margin",
    "roe",
    "ocf_to_np",
    "debt_ratio",
    "equity_parent",
)
CURRENT_VALUATION_COLUMNS = (
    "asset_id",
    "as_of_date",
    "consumer_subindustry",
    "current_market_cap",
    "net_debt",
    "pe_ttm",
    "ps_ttm",
    "ev_ebitda",
    "revenue_ttm",
    "np_parent_ttm",
    "ebitda_ttm",
)
VALUATION_HISTORY_COLUMNS = (
    "asset_id",
    "valuation_date",
    "consumer_subindustry",
    "pe_ttm",
    "ps_ttm",
    "ev_ebitda",
)
VALUATION_FUNDAMENTAL_COLUMNS = (
    "asset_id",
    "latest_announcement_date",
    "latest_revenue_growth",
    "normal_revenue_growth",
    "latest_net_margin",
    "normal_net_margin",
    "positive_profit_periods",
    "stable_positive_earnings",
)
HARD_RISK_FUNDAMENTAL_COLUMNS = (
    "asset_id",
    "latest_equity_parent",
    "latest_debt_ratio",
    "latest_operating_cash_flow",
    "prior_operating_cash_flow",
    "second_prior_operating_cash_flow",
)
MANUAL_RISK_COLUMNS = (
    "asset_id",
    "audit_review_status",
    "pledge_debt_review_status",
    "permanent_impairment_status",
)


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _decimal_outside_range(value: object, lower: str, upper: str) -> bool:
    return isinstance(value, Decimal) and (
        not value.is_finite() or value < Decimal(lower) or value > Decimal(upper)
    )


def _meets_decimal_aware_threshold(value: object, number: float, threshold: str) -> bool:
    if isinstance(value, Decimal):
        return value >= Decimal(threshold)
    return number >= float(threshold)


def _parse_date_series(frame: pd.DataFrame, field: str, name: str) -> pd.Series:
    try:
        parsed = pd.to_datetime(frame[field], errors="raise", format="mixed").dt.normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} {field} contains an invalid date") from exc
    if parsed.isna().any():
        raise ValueError(f"{name} {field} contains an invalid date")
    return parsed


def _strict_numeric_frame(
    frame: pd.DataFrame,
    fields: tuple[str, ...],
    *,
    name: str,
) -> pd.DataFrame:
    numeric = pd.DataFrame(index=frame.index)
    for field in fields:
        values: list[float] = []
        for index, value in frame[field].items():
            missing = value is None or value is pd.NA
            if isinstance(value, (float, np.floating)) and math.isnan(float(value)):
                missing = True
            if missing:
                values.append(math.nan)
                continue
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, STRICT_NUMERIC_TYPES
            ):
                asset_id = str(frame.at[index, "asset_id"])
                raise ValueError(f"{name} asset {asset_id} field {field} must be finite numeric")
            if isinstance(value, Decimal) and not value.is_finite():
                asset_id = str(frame.at[index, "asset_id"])
                raise ValueError(
                    f"{name} asset {asset_id} field {field} must be finite numeric"
                )
            try:
                number = float(value)
            except (OverflowError, ValueError):
                asset_id = str(frame.at[index, "asset_id"])
                raise ValueError(
                    f"{name} asset {asset_id} field {field} must be finite numeric"
                ) from None
            if not math.isfinite(number):
                asset_id = str(frame.at[index, "asset_id"])
                raise ValueError(f"{name} asset {asset_id} field {field} must be finite numeric")
            values.append(number)
        numeric[field] = values
    return numeric


def _assign_strict_numeric(
    frame: pd.DataFrame,
    fields: tuple[str, ...],
    *,
    name: str,
) -> None:
    numeric = _strict_numeric_frame(frame, fields, name=name)
    for field in fields:
        frame[field] = numeric[field]


def _reject_duplicate_assets(frame: pd.DataFrame, name: str) -> None:
    duplicate = frame["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = frame.loc[duplicate, "asset_id"].astype(str).sort_values(kind="stable").iloc[0]
        raise ValueError(f"{name} contains duplicate asset_id {asset_id}")


def _winsorized_median(values: pd.Series) -> float:
    valid = values.loc[values.gt(0.0) & np.isfinite(values)].astype(float)
    if valid.empty:
        return math.nan
    lower, upper = valid.quantile([0.1, 0.9])
    return float(valid.clip(lower=lower, upper=upper).median())


def _select_valuation_method(
    row: object, stable_positive_earnings: bool
) -> list[tuple[str, str]]:
    pe_available = stable_positive_earnings and row.np_parent_ttm > 0.0 and row.pe_ttm > 0.0
    ev_available = row.ebitda_ttm > 0.0 and row.ev_ebitda > 0.0
    ps_available = row.revenue_ttm > 0.0 and row.ps_ttm > 0.0
    methods = {
        "pe": (pe_available, "pe_normalized_profit", "pe_ttm"),
        "ev": (ev_available, "ev_ebitda", "ev_ebitda"),
        "ps": (ps_available, "ps_normalized_margin", "ps_ttm"),
    }
    if row.consumer_subindustry in {"retail_duty_free", "tourism_hospitality"}:
        order = ("ev", "ps", "pe")
    elif row.consumer_subindustry == "auto_oem":
        order = ("ps", "pe", "ev")
    else:
        order = ("pe", "ev", "ps")
    return [
        (method, multiple_field)
        for candidate in order
        for available, method, multiple_field in [methods[candidate]]
        if available
    ]


def compute_fundamental_features(
    finance_rows: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Build point-in-time fundamental history summaries for each asset."""
    _require_columns(finance_rows, FINANCE_COLUMNS, "finance_rows")
    try:
        cutoff = pd.Timestamp(trade_date).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}") from exc
    if pd.isna(cutoff):
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}")

    frame = finance_rows.loc[:, FINANCE_COLUMNS].copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["report_period"] = _parse_date_series(frame, "report_period", "finance_rows")
    frame["announcement_date"] = _parse_date_series(frame, "announcement_date", "finance_rows")
    _assign_strict_numeric(frame, FINANCE_NUMERIC_COLUMNS, name="finance_rows")
    frame = frame.loc[frame["announcement_date"].le(cutoff)].copy()

    duplicate = frame.duplicated(
        ["asset_id", "report_period", "announcement_date"], keep=False
    )
    if duplicate.any():
        row = frame.loc[
            duplicate, ["asset_id", "report_period", "announcement_date"]
        ].sort_values(["asset_id", "report_period", "announcement_date"], kind="stable").iloc[0]
        raise ValueError(
            "duplicate finance announcement for asset "
            f"{row['asset_id']} report_period {row['report_period'].date().isoformat()} "
            f"announcement_date {row['announcement_date'].date().isoformat()}"
        )

    frame = frame.sort_values(
        ["asset_id", "report_period", "announcement_date"], kind="stable"
    ).drop_duplicates(["asset_id", "report_period"], keep="last")
    frame = frame.sort_values(["asset_id", "report_period"], ascending=[True, False], kind="stable")
    frame = frame.groupby("asset_id", sort=False, group_keys=False).head(8)

    output_columns = [
        "asset_id",
        "latest_report_period",
        "latest_announcement_date",
        "history_periods",
    ]
    output_columns.extend(f"latest_{field}" for field in NORMAL_FUNDAMENTAL_COLUMNS)
    output_columns.extend(f"normal_{field}" for field in NORMAL_FUNDAMENTAL_COLUMNS)
    output_columns.extend(
        ["latest_revenue_ttm", "latest_np_parent_ttm", "latest_operating_cash_flow"]
    )
    output_columns.extend(
        ["prior_operating_cash_flow", "second_prior_operating_cash_flow"]
    )
    output_columns.extend(["positive_profit_periods", "stable_positive_earnings"])
    output_columns.extend(f"{field}_delta_to_prior" for field in FINANCE_NUMERIC_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    rows: list[dict[str, object]] = []
    for asset_id, history in frame.groupby("asset_id", sort=True):
        history = history.sort_values("report_period", ascending=False, kind="stable").reset_index(drop=True)
        latest = history.iloc[0]
        row: dict[str, object] = {
            "asset_id": asset_id,
            "latest_report_period": latest["report_period"],
            "latest_announcement_date": latest["announcement_date"],
            "history_periods": len(history),
        }
        for field in NORMAL_FUNDAMENTAL_COLUMNS:
            row[f"latest_{field}"] = latest[field]
            row[f"normal_{field}"] = float(history[field].median(skipna=True))
        for field in ("revenue_ttm", "np_parent_ttm", "operating_cash_flow"):
            row[f"latest_{field}"] = latest[field]
        row["prior_operating_cash_flow"] = (
            history.at[1, "operating_cash_flow"] if len(history) >= 2 else math.nan
        )
        row["second_prior_operating_cash_flow"] = (
            history.at[2, "operating_cash_flow"] if len(history) >= 3 else math.nan
        )
        positive_profit_periods = int(history["np_parent_ttm"].gt(0.0).sum())
        row["positive_profit_periods"] = positive_profit_periods
        row["stable_positive_earnings"] = bool(
            pd.notna(latest["np_parent_ttm"])
            and latest["np_parent_ttm"] > 0.0
            and positive_profit_periods >= 4
        )
        for field in FINANCE_NUMERIC_COLUMNS:
            prior = history.at[1, field] if len(history) >= 2 else math.nan
            row[f"{field}_delta_to_prior"] = latest[field] - prior
        rows.append(row)
    return pd.DataFrame(rows).loc[:, output_columns].sort_values("asset_id", kind="stable").reset_index(drop=True)


def compute_valuation_features(
    current_valuation: pd.DataFrame,
    valuation_history: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate normalized valuation scenarios from point-in-time multiples."""
    _require_columns(current_valuation, CURRENT_VALUATION_COLUMNS, "current_valuation")
    _require_columns(valuation_history, VALUATION_HISTORY_COLUMNS, "valuation_history")
    _require_columns(fundamentals, VALUATION_FUNDAMENTAL_COLUMNS, "fundamentals")

    current = current_valuation.loc[:, CURRENT_VALUATION_COLUMNS].copy()
    current["asset_id"] = current["asset_id"].astype(str)
    _reject_duplicate_assets(current, "current_valuation")
    current["as_of_date"] = _parse_date_series(current, "as_of_date", "current_valuation")
    current_numeric_fields = CURRENT_VALUATION_COLUMNS[3:]
    _assign_strict_numeric(current, current_numeric_fields, name="current_valuation")
    invalid_market_cap = current["current_market_cap"].isna() | current["current_market_cap"].le(0.0)
    if invalid_market_cap.any():
        row = current.loc[invalid_market_cap].sort_values("asset_id", kind="stable").iloc[0]
        raise ValueError(
            f"current_valuation asset {row['asset_id']} field current_market_cap must be finite and > 0"
        )

    history = valuation_history.loc[:, VALUATION_HISTORY_COLUMNS].copy()
    history["asset_id"] = history["asset_id"].astype(str)
    history["valuation_date"] = _parse_date_series(history, "valuation_date", "valuation_history")
    duplicate_history = history.duplicated(["asset_id", "valuation_date"], keep=False)
    if duplicate_history.any():
        row = history.loc[duplicate_history, ["asset_id", "valuation_date"]].sort_values(
            ["asset_id", "valuation_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "duplicate valuation_history for asset "
            f"{row['asset_id']} on {row['valuation_date'].date().isoformat()}"
        )
    history_numeric_fields = ("pe_ttm", "ps_ttm", "ev_ebitda")
    _assign_strict_numeric(history, history_numeric_fields, name="valuation_history")

    fundamental = fundamentals.loc[:, VALUATION_FUNDAMENTAL_COLUMNS].copy()
    fundamental["asset_id"] = fundamental["asset_id"].astype(str)
    _reject_duplicate_assets(fundamental, "fundamentals")
    fundamental["latest_announcement_date"] = _parse_date_series(
        fundamental, "latest_announcement_date", "fundamentals"
    )
    fundamental_numeric_fields = VALUATION_FUNDAMENTAL_COLUMNS[2:7]
    _assign_strict_numeric(fundamental, fundamental_numeric_fields, name="fundamentals")
    invalid_profit_periods = (
        fundamental["positive_profit_periods"].isna()
        | fundamental["positive_profit_periods"].lt(0.0)
        | fundamental["positive_profit_periods"].gt(8.0)
        | fundamental["positive_profit_periods"].mod(1.0).ne(0.0)
    )
    if invalid_profit_periods.any():
        row = fundamental.loc[invalid_profit_periods].sort_values("asset_id", kind="stable").iloc[0]
        raise ValueError(
            f"fundamentals asset {row['asset_id']} field positive_profit_periods must be an integer from 0 to 8"
        )
    invalid_stable = ~fundamental["stable_positive_earnings"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    )
    if invalid_stable.any():
        row = fundamental.loc[invalid_stable].sort_values("asset_id", kind="stable").iloc[0]
        raise ValueError(
            f"fundamentals asset {row['asset_id']} field stable_positive_earnings must be bool"
        )
    fundamental_by_asset = fundamental.set_index("asset_id")

    rows: list[dict[str, object]] = []
    scenario_closures = {"pessimistic": 0.0, "base": 0.65, "optimistic": 0.80}
    for current_row in current.sort_values("asset_id", kind="stable").itertuples(index=False):
        asset_id = current_row.asset_id
        if asset_id not in fundamental_by_asset.index:
            raise ValueError(f"fundamentals missing asset_id {asset_id}")
        fundamental_row = fundamental_by_asset.loc[asset_id]
        if fundamental_row["latest_announcement_date"] > current_row.as_of_date:
            raise ValueError(
                f"asset {asset_id} latest_announcement_date must be on or before as_of_date"
            )

        candidates = _select_valuation_method(
            current_row, bool(fundamental_row["stable_positive_earnings"])
        )

        eligible = history.loc[history["valuation_date"].le(current_row.as_of_date)]
        method = "unavailable"
        multiple_field = ""
        current_multiple = math.nan
        company_values = pd.Series(dtype=float)
        reference_multiple = math.nan
        valuation_percentile = math.nan
        industry_peer_assets = 0
        for candidate_index, (candidate_method, candidate_field) in enumerate(candidates):
            candidate_multiple = float(getattr(current_row, candidate_field))
            method_history = eligible.loc[
                eligible[candidate_field].gt(0.0) & np.isfinite(eligible[candidate_field])
            ].copy()
            method_history["valuation_month"] = method_history["valuation_date"].dt.to_period("M")
            method_history = method_history.sort_values(
                ["asset_id", "valuation_date"], kind="stable"
            ).drop_duplicates(["asset_id", "valuation_month"], keep="last")
            candidate_company_values = method_history.loc[
                method_history["asset_id"].eq(asset_id), candidate_field
            ].astype(float)
            peer_history = method_history.loc[
                method_history["consumer_subindustry"].eq(current_row.consumer_subindustry)
                & method_history["asset_id"].ne(asset_id)
            ]
            candidate_peer_assets = int(peer_history["asset_id"].nunique())
            industry_median = _winsorized_median(peer_history[candidate_field])
            if len(candidate_company_values) >= 24:
                company_median = _winsorized_median(candidate_company_values)
                candidate_reference = (
                    min(company_median, industry_median)
                    if math.isfinite(industry_median)
                    else company_median
                )
            elif candidate_peer_assets >= 3:
                candidate_reference = industry_median
            else:
                candidate_reference = math.nan
            candidate_percentile = (
                float(candidate_company_values.le(candidate_multiple).mean())
                if len(candidate_company_values) >= 24
                else math.nan
            )
            if candidate_index == 0 or math.isfinite(candidate_reference):
                current_multiple = candidate_multiple
                company_values = candidate_company_values
                reference_multiple = candidate_reference
                valuation_percentile = candidate_percentile
                industry_peer_assets = candidate_peer_assets
            if math.isfinite(candidate_reference):
                method = candidate_method
                multiple_field = candidate_field
                break

        result: dict[str, object] = {
            "asset_id": asset_id,
            "valuation_method": method,
            "current_multiple": current_multiple,
            "reference_multiple": reference_multiple,
            "valuation_percentile": valuation_percentile,
            "valuation_depression_percentile": (
                1.0 - valuation_percentile if math.isfinite(valuation_percentile) else math.nan
            ),
            "valuation_percentile_coverage": len(company_values) >= 24,
            "valuation_self_history_insufficient": len(company_values) < 24,
            "self_history_insufficient": len(company_values) < 24,
            "valid_history_observations": len(company_values),
            "industry_peer_assets": industry_peer_assets,
        }
        for scenario, closure in scenario_closures.items():
            market_cap = math.nan
            if method != "unavailable":
                current_growth = fundamental_row["latest_revenue_growth"]
                normal_growth = fundamental_row["normal_revenue_growth"]
                growth_gap = max(normal_growth - current_growth, 0.0)
                scenario_revenue = current_row.revenue_ttm * (1.0 + closure * growth_gap)
                if scenario == "pessimistic":
                    multiple = min(current_multiple, reference_multiple * 0.8)
                elif scenario == "base":
                    multiple = reference_multiple * 0.85
                else:
                    multiple = reference_multiple
                if method == "pe_normalized_profit":
                    current_margin = fundamental_row["latest_net_margin"]
                    normal_margin = fundamental_row["normal_net_margin"]
                    scenario_margin = current_margin + closure * (normal_margin - current_margin)
                    scenario_profit = max(scenario_revenue * scenario_margin, 0.0)
                    market_cap = scenario_profit * multiple
                elif method == "ps_normalized_margin":
                    market_cap = scenario_revenue * multiple
                else:
                    scenario_ebitda = current_row.ebitda_ttm * (1.0 + closure * growth_gap)
                    market_cap = scenario_ebitda * multiple - current_row.net_debt
            result[f"{scenario}_market_cap"] = market_cap
            result[f"{scenario}_upside"] = (
                market_cap / current_row.current_market_cap - 1.0
                if math.isfinite(market_cap)
                else math.nan
            )
        rows.append(result)
    if not rows:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "valuation_method",
                "current_multiple",
                "reference_multiple",
                "valuation_percentile",
                "valuation_depression_percentile",
                "valuation_percentile_coverage",
                "valuation_self_history_insufficient",
                "self_history_insufficient",
                "valid_history_observations",
                "industry_peer_assets",
                "pessimistic_market_cap",
                "pessimistic_upside",
                "base_market_cap",
                "base_upside",
                "optimistic_market_cap",
                "optimistic_upside",
            ]
        )
    return pd.DataFrame(rows).sort_values("asset_id", kind="stable").reset_index(drop=True)


def compute_hard_risk_features(
    fundamentals: pd.DataFrame,
    manual_risk_reviews: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine automatic balance-sheet risks with non-defaulting manual reviews."""
    _require_columns(fundamentals, HARD_RISK_FUNDAMENTAL_COLUMNS, "fundamentals")
    frame = fundamentals.loc[:, HARD_RISK_FUNDAMENTAL_COLUMNS].copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    _reject_duplicate_assets(frame, "fundamentals")
    numeric_fields = HARD_RISK_FUNDAMENTAL_COLUMNS[1:]
    _assign_strict_numeric(frame, numeric_fields, name="fundamentals")

    reviews: dict[str, dict[str, str]] = {}
    if manual_risk_reviews is not None:
        _require_columns(manual_risk_reviews, MANUAL_RISK_COLUMNS, "manual_risk_reviews")
        manual = manual_risk_reviews.loc[:, MANUAL_RISK_COLUMNS].copy()
        manual["asset_id"] = manual["asset_id"].astype(str)
        _reject_duplicate_assets(manual, "manual_risk_reviews")
        allowed = {"clear", "triggered", "unknown"}
        for row in manual.itertuples(index=False):
            statuses: dict[str, str] = {}
            for field in MANUAL_RISK_COLUMNS[1:]:
                status = getattr(row, field)
                missing_marker = pd.isna(status)
                if (
                    isinstance(missing_marker, (bool, np.bool_))
                    and bool(missing_marker)
                ) or (isinstance(status, str) and not status.strip()):
                    status = "unknown"
                if status not in allowed:
                    raise ValueError(
                        f"manual_risk_reviews asset {row.asset_id} field {field} "
                        "must be clear, triggered, or unknown"
                    )
                statuses[field] = status
            reviews[row.asset_id] = statuses

    rows: list[dict[str, object]] = []
    unknown_statuses = {field: "unknown" for field in MANUAL_RISK_COLUMNS[1:]}
    for row in frame.sort_values("asset_id", kind="stable").itertuples(index=False):
        codes: set[str] = set()
        if pd.notna(row.latest_equity_parent) and row.latest_equity_parent <= 0.0:
            codes.add("negative_parent_equity")
        debt_pressure = pd.notna(row.latest_debt_ratio) and row.latest_debt_ratio >= 0.85
        if debt_pressure:
            codes.add("debt_pressure")
        cash_flows = (
            row.latest_operating_cash_flow,
            row.prior_operating_cash_flow,
            row.second_prior_operating_cash_flow,
        )
        if all(pd.notna(value) for value in cash_flows) and cash_flows[0] < cash_flows[1] < cash_flows[2]:
            codes.add("ocf_two_period_deterioration")
        automated_review_unknown = any(
            pd.isna(value)
            for value in (
                row.latest_equity_parent,
                row.latest_debt_ratio,
                *cash_flows,
            )
        )

        statuses = reviews.get(row.asset_id, unknown_statuses)
        if statuses["audit_review_status"] == "triggered":
            codes.add("audit_review_triggered")
        if statuses["pledge_debt_review_status"] == "triggered" and debt_pressure:
            codes.add("pledge_debt_combination")
        if statuses["permanent_impairment_status"] == "triggered":
            codes.add("permanent_impairment_flag")
        review_unknown = automated_review_unknown or "unknown" in statuses.values()
        if review_unknown:
            codes.add("hard_risk_review_unknown")
        triggered = bool(codes - {"hard_risk_review_unknown"})
        rows.append(
            {
                "asset_id": row.asset_id,
                "hard_risk_codes": "|".join(sorted(codes)),
                "hard_risk_triggered": triggered,
                "hard_risk_review_unknown": review_unknown,
                "automated_risk_review_unknown": automated_review_unknown,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "hard_risk_codes",
                "hard_risk_triggered",
                "hard_risk_review_unknown",
                "automated_risk_review_unknown",
            ]
        )
    return pd.DataFrame(rows).sort_values("asset_id", kind="stable").reset_index(drop=True)


def _window_return(close: pd.Series, bars: int) -> float:
    if len(close) < bars:
        return math.nan
    return float(close.iloc[-1] / close.iloc[-bars] - 1.0)


def _moving_average(close: pd.Series, bars: int) -> float:
    if len(close) < bars:
        return math.nan
    return float(close.tail(bars).mean())


def compute_price_features(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Compute point-in-time price and subindustry-relative oversold features."""
    _require_columns(bars, BAR_COLUMNS, "bars")
    _require_columns(membership, MEMBERSHIP_COLUMNS, "membership")

    try:
        cutoff = pd.Timestamp(trade_date).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}") from exc

    frame = bars.loc[:, BAR_COLUMNS].copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    try:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("bars trade_date contains an invalid date") from exc
    frame = frame.loc[frame["trade_date"].le(cutoff)].copy()

    duplicates = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicates.any():
        duplicate = frame.loc[duplicates, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "duplicate bar for asset "
            f"{duplicate['asset_id']} on {duplicate['trade_date'].date().isoformat()}"
        )

    numeric_close = pd.to_numeric(frame["close"], errors="coerce")
    invalid_close = numeric_close.isna() | ~np.isfinite(numeric_close) | numeric_close.le(0.0)
    if invalid_close.any():
        invalid = frame.loc[invalid_close, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            "invalid close for asset "
            f"{invalid['asset_id']} on {invalid['trade_date'].date().isoformat()}"
        )
    frame["close"] = numeric_close.astype(float)
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    member_frame = membership.loc[:, MEMBERSHIP_COLUMNS].copy()
    member_frame["asset_id"] = member_frame["asset_id"].astype(str)
    duplicate_members = member_frame["asset_id"].duplicated(keep=False)
    if duplicate_members.any():
        asset_id = member_frame.loc[duplicate_members, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"membership contains duplicate asset_id {asset_id}")
    invalid_subindustry = member_frame["consumer_subindustry"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid_subindustry.any():
        asset_id = member_frame.loc[invalid_subindustry, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"membership consumer_subindustry is empty for asset {asset_id}")
    rows: list[dict[str, object]] = []
    histories = {asset_id: history for asset_id, history in frame.groupby("asset_id", sort=False)}
    for membership_row in member_frame.sort_values("asset_id", kind="stable").itertuples(index=False):
        asset_id = membership_row.asset_id
        history = histories.get(asset_id)
        if history is None:
            close = pd.Series(dtype=float)
            latest_trade_date = pd.NaT
            latest_close = math.nan
        else:
            close = history["close"].reset_index(drop=True)
            latest_trade_date = history["trade_date"].iloc[-1]
            latest_close = float(close.iloc[-1])

        history_bars = len(close)
        return_6m = _window_return(close, 126)
        return_60d = _window_return(close, 60)
        ma120 = _moving_average(close, 120)
        ma250 = _moving_average(close, 250)
        max_drawdown_12m = (
            float(latest_close / close.tail(252).max() - 1.0)
            if history_bars >= 252
            else math.nan
        )
        rebound_from_low_60d = (
            float(latest_close / close.tail(60).min() - 1.0)
            if history_bars >= 60
            else math.nan
        )
        rows.append(
            {
                "asset_id": asset_id,
                "latest_trade_date": latest_trade_date,
                "latest_close": latest_close,
                "history_bars": history_bars,
                "price_history_complete": history_bars >= 252,
                "return_6m": return_6m,
                "return_60d": return_60d,
                "max_drawdown_12m": max_drawdown_12m,
                "rebound_from_low_60d": rebound_from_low_60d,
                "ma120": ma120,
                "ma250": ma250,
                "distance_ma120": latest_close / ma120 - 1.0 if math.isfinite(ma120) else math.nan,
                "distance_ma250": latest_close / ma250 - 1.0 if math.isfinite(ma250) else math.nan,
                "consumer_subindustry": membership_row.consumer_subindustry,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=PRICE_OUTPUT_COLUMNS)

    grouped = result.groupby("consumer_subindustry", dropna=False)
    peer_count_6m = grouped["return_6m"].transform("count")
    peer_count_60d = grouped["return_60d"].transform("count")
    result["industry_peer_count"] = peer_count_6m.astype(int)
    result["industry_peer_count_60d"] = peer_count_60d.astype(int)
    result["industry_return_6m"] = grouped["return_6m"].transform("mean")
    result["industry_return_60d"] = grouped["return_60d"].transform("mean")
    result["relative_return_6m"] = result["return_6m"] - result["industry_return_6m"]
    result["relative_return_60d"] = result["return_60d"] - result["industry_return_60d"]
    result["relative_return_coverage"] = peer_count_6m.ge(3) & result["return_6m"].notna()
    result["relative_return_coverage_60d"] = peer_count_60d.ge(3) & result["return_60d"].notna()
    result.loc[
        ~result["relative_return_coverage"],
        ["industry_return_6m", "relative_return_6m"],
    ] = np.nan
    result.loc[
        ~result["relative_return_coverage_60d"],
        ["industry_return_60d", "relative_return_60d"],
    ] = np.nan
    return result.loc[:, PRICE_OUTPUT_COLUMNS].sort_values("asset_id", kind="stable").reset_index(drop=True)


def compute_oversold_score(frame: pd.DataFrame) -> pd.Series:
    """Return the approved cross-sectional oversold score without filling gaps."""
    _require_columns(frame, SCORE_COLUMNS, "frame")
    raw_valuation = frame["valuation_depression_percentile"]
    valuation = pd.to_numeric(raw_valuation, errors="coerce").astype(float)
    invalid_decimal = raw_valuation.map(
        lambda value: _decimal_outside_range(value, "0", "1")
    )
    invalid_valuation = invalid_decimal | (
        raw_valuation.notna()
        & (valuation.isna() | ~np.isfinite(valuation) | ~valuation.between(0.0, 1.0))
    )
    if invalid_valuation.any():
        raise ValueError(
            "valuation_depression_percentile must be numeric, finite, and between 0 and 1"
        )

    numeric = frame.loc[:, SCORE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    numeric["valuation_depression_percentile"] = valuation
    drawdown_percentile = numeric["max_drawdown_12m"].rank(pct=True, ascending=False)
    return_6m_percentile = numeric["return_6m"].rank(pct=True, ascending=False)
    relative_return_percentile = numeric["relative_return_6m"].rank(pct=True, ascending=False)
    ma_distance = numeric[["distance_ma120", "distance_ma250"]].mean(axis=1, skipna=False)
    ma_distance_percentile = ma_distance.rank(pct=True, ascending=False)
    score = (
        30.0 * drawdown_percentile
        + 20.0 * return_6m_percentile
        + 20.0 * relative_return_percentile
        + 20.0 * valuation
        + 10.0 * ma_distance_percentile
    ).clip(0.0, 100.0)
    score.name = "oversold_score"
    return score


def _optional_number(row: Mapping[str, object] | pd.Series, field: str) -> tuple[float, bool]:
    value = row.get(field, math.nan)
    if value is None or value is pd.NA:
        return math.nan, False
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, STRICT_NUMERIC_TYPES):
        raise ValueError(f"{field} must be a finite int or float")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(f"{field} must be a finite int or float")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{field} must be a finite int or float") from None
    if math.isnan(number):
        if isinstance(value, Decimal):
            raise ValueError(f"{field} must be a finite int or float")
        return math.nan, False
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite int or float")
    return number, True


def compute_already_priced_features(
    price_row: Mapping[str, object] | pd.Series,
    valuation_row: Mapping[str, object] | pd.Series,
    *,
    evidence_revision_state: str = "",
) -> dict[str, object]:
    """Compute deterministic penalty flags for repair that the market already priced."""
    rebound, rebound_coverage = _optional_number(price_row, "rebound_from_low_60d")
    relative_return, relative_return_coverage = _optional_number(price_row, "relative_return_60d")
    valuation, valuation_coverage = _optional_number(valuation_row, "valuation_percentile")
    rebound_raw = price_row.get("rebound_from_low_60d", math.nan)
    relative_return_raw = price_row.get("relative_return_60d", math.nan)
    valuation_raw = valuation_row.get("valuation_percentile", math.nan)
    if valuation_coverage and (
        _decimal_outside_range(valuation_raw, "0", "1")
        or not 0.0 <= valuation <= 1.0
    ):
        raise ValueError("valuation_percentile must be between 0 and 1")

    rebound_trigger = rebound_coverage and _meets_decimal_aware_threshold(
        rebound_raw, rebound, "0.25"
    )
    relative_return_trigger = relative_return_coverage and _meets_decimal_aware_threshold(
        relative_return_raw, relative_return, "0.10"
    )
    valuation_trigger = valuation_coverage and _meets_decimal_aware_threshold(
        valuation_raw, valuation, "0.50"
    )
    evidence_revision_trigger = evidence_revision_state == "broadly_priced"
    penalty = min(
        20.0,
        6.0 * rebound_trigger
        + 4.0 * relative_return_trigger
        + 5.0 * valuation_trigger
        + 5.0 * evidence_revision_trigger,
    )
    return {
        "priced_in_penalty": penalty,
        "priced_in_rebound_trigger": bool(rebound_trigger),
        "priced_in_relative_return_trigger": bool(relative_return_trigger),
        "priced_in_valuation_trigger": bool(valuation_trigger),
        "priced_in_evidence_revision_trigger": bool(evidence_revision_trigger),
        "priced_in_rebound_coverage": rebound_coverage,
        "priced_in_relative_return_coverage": relative_return_coverage,
        "priced_in_valuation_coverage": valuation_coverage,
    }
