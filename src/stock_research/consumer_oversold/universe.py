from __future__ import annotations

from datetime import date
import re
import unicodedata

import pandas as pd

from .contracts import ConsumerOversoldConfig


ASSET_COLUMNS = ("asset_id", "stock_code", "name", "list_date")
STATUS_COLUMNS = ("asset_id", "is_st", "is_delisting_risk", "is_suspended")
LIQUIDITY_COLUMNS = ("asset_id", "avg_turnover_amount")
INDUSTRY_COLUMNS = ("asset_id", "industry_system", "industry_name")
INDUSTRY_RULE_COLUMNS = (
    "priority",
    "industry_system",
    "industry_name_pattern",
    "consumer_subindustry",
    "action",
    "reason",
)
ASSET_OVERRIDE_COLUMNS = (
    "stock_code",
    "action",
    "consumer_subindustry",
    "reason",
    "effective_from",
    "effective_to",
)
OUTPUT_COLUMNS = [
    "asset_id",
    "stock_code",
    "name",
    "list_date",
    "industry_system",
    "industry_name",
    "consumer_subindustry",
    "included",
    "include_reasons",
    "exclude_reasons",
]


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], frame_name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{frame_name} missing required columns: {', '.join(missing)}")


def _text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalized(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", _text(value)))


def _joined(reasons: list[str]) -> str:
    return "|".join(sorted({_text(reason) for reason in reasons if _text(reason)}))


def _active_override(
    overrides: pd.DataFrame,
    *,
    stock_code: str,
    trade_date: date,
) -> pd.Series | None:
    candidates = overrides.loc[overrides["stock_code"].astype(str).str.strip().eq(stock_code)]
    for _, override in candidates.iterrows():
        effective_from = _text(override["effective_from"])
        effective_to = _text(override["effective_to"])
        if effective_from and date.fromisoformat(effective_from) > trade_date:
            continue
        if effective_to and trade_date >= date.fromisoformat(effective_to):
            continue
        return override
    return None


def _first_industry_rule(
    rules: pd.DataFrame,
    *,
    industry_system: str,
    industry_name: str,
) -> pd.Series | None:
    for _, rule in rules.sort_values("priority", kind="stable").iterrows():
        rule_system = _text(rule["industry_system"])
        if rule_system != "*" and _normalized(rule_system) != _normalized(industry_system):
            continue
        if re.search(_text(rule["industry_name_pattern"]), _normalized(industry_name)):
            return rule
    return None


def _listed_long_enough(list_date: object, *, trade_date: date, minimum_days: int) -> bool:
    try:
        listed_on = date.fromisoformat(_text(list_date))
    except ValueError:
        return False
    return (trade_date - listed_on).days >= minimum_days


def _validate_inputs(
    *,
    assets: pd.DataFrame,
    statuses: pd.DataFrame,
    liquidity: pd.DataFrame,
    industries: pd.DataFrame,
    industry_rules: pd.DataFrame,
    asset_overrides: pd.DataFrame,
) -> None:
    for frame, required, name in (
        (assets, ASSET_COLUMNS, "assets"),
        (statuses, STATUS_COLUMNS, "statuses"),
        (liquidity, LIQUIDITY_COLUMNS, "liquidity"),
        (industries, INDUSTRY_COLUMNS, "industries"),
        (industry_rules, INDUSTRY_RULE_COLUMNS, "industry_rules"),
        (asset_overrides, ASSET_OVERRIDE_COLUMNS, "asset_overrides"),
    ):
        _require_columns(frame, required, name)

    invalid_actions = sorted(
        action
        for action in {_text(value) for value in asset_overrides["action"]}
        if action not in {"include", "exclude"}
    )
    if invalid_actions:
        raise ValueError(f"asset_overrides action must be include/exclude: {', '.join(invalid_actions)}")
    missing_subindustry = asset_overrides["action"].astype(str).str.strip().eq("include") & asset_overrides[
        "consumer_subindustry"
    ].map(_text).eq("")
    if missing_subindustry.any():
        raise ValueError("asset_overrides include requires consumer_subindustry")


def build_consumer_universe_from_frames(
    *,
    assets: pd.DataFrame,
    statuses: pd.DataFrame,
    liquidity: pd.DataFrame,
    industries: pd.DataFrame,
    industry_rules: pd.DataFrame,
    asset_overrides: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    """Build the broad terminal-consumer universe and retain every asset decision."""
    _validate_inputs(
        assets=assets,
        statuses=statuses,
        liquidity=liquidity,
        industries=industries,
        industry_rules=industry_rules,
        asset_overrides=asset_overrides,
    )
    if assets.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    trade_date = date.fromisoformat(config.trade_date)
    status_by_asset = statuses.drop_duplicates("asset_id", keep="last").set_index("asset_id")
    liquidity_by_asset = liquidity.drop_duplicates("asset_id", keep="last").set_index("asset_id")
    industry_by_asset = industries.drop_duplicates("asset_id", keep="last").set_index("asset_id")
    rows: list[dict[str, object]] = []

    for asset in assets.itertuples(index=False):
        asset_id = _text(asset.asset_id)
        stock_code = _text(asset.stock_code)
        status = status_by_asset.loc[asset_id] if asset_id in status_by_asset.index else None
        liquid = liquidity_by_asset.loc[asset_id] if asset_id in liquidity_by_asset.index else None
        industry = industry_by_asset.loc[asset_id] if asset_id in industry_by_asset.index else None
        industry_system = _text(industry["industry_system"]) if industry is not None else ""
        industry_name = _text(industry["industry_name"]) if industry is not None else ""
        include_reasons: list[str] = []
        exclude_reasons: list[str] = []
        consumer_subindustry = ""

        override = _active_override(asset_overrides, stock_code=stock_code, trade_date=trade_date)
        if override is not None:
            action = _text(override["action"])
            reason = _text(override["reason"])
            if action == "include":
                consumer_subindustry = _text(override["consumer_subindustry"])
                include_reasons.append(reason)
            else:
                exclude_reasons.append(reason)
        elif not industry_name:
            exclude_reasons.append("missing_industry")
        else:
            rule = _first_industry_rule(
                industry_rules,
                industry_system=industry_system,
                industry_name=industry_name,
            )
            if rule is None:
                exclude_reasons.append("not_terminal_consumer")
            elif _text(rule["action"]) == "include":
                consumer_subindustry = _text(rule["consumer_subindustry"])
                include_reasons.append(_text(rule["reason"]))
            else:
                exclude_reasons.append(_text(rule["reason"]) or "not_terminal_consumer")

        if status is not None and (bool(status["is_st"]) or bool(status["is_delisting_risk"])):
            exclude_reasons.append("st_or_delisting_risk")
        if status is not None and bool(status["is_suspended"]):
            exclude_reasons.append("suspended")
        if not _listed_long_enough(asset.list_date, trade_date=trade_date, minimum_days=config.min_listed_days):
            exclude_reasons.append("listed_less_than_365_days")
        turnover = pd.to_numeric(liquid["avg_turnover_amount"], errors="coerce") if liquid is not None else float("nan")
        if pd.isna(turnover) or float(turnover) < config.min_avg_turnover_amount:
            exclude_reasons.append("low_liquidity")

        serialized_excludes = _joined(exclude_reasons)
        rows.append(
            {
                "asset_id": asset_id,
                "stock_code": stock_code,
                "name": _text(asset.name),
                "list_date": _text(asset.list_date),
                "industry_system": industry_system,
                "industry_name": industry_name,
                "consumer_subindustry": consumer_subindustry,
                "included": not serialized_excludes,
                "include_reasons": _joined(include_reasons),
                "exclude_reasons": serialized_excludes,
            }
        )

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
