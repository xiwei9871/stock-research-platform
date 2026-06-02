from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


BOARD_MAIN = "main"
BOARD_CHINEXT = "chinext"
BOARD_STAR = "star"
BOARD_BEIJING = "beijing"
BOARD_UNKNOWN = "unknown"

RESEARCH_DEFAULT_MIN_LISTED_DAYS = 120
INCLUDE_RECENT_IPO_MIN_LISTED_DAYS = 20
DEFAULT_MIN_AVG_TURNOVER_AMOUNT = 30_000_000.0
DEFAULT_LIQUIDITY_LOOKBACK_DAYS = 20
DEFAULT_MAX_SUSPENDED_DAYS = 5


@dataclass(frozen=True)
class UniverseConfig:
    as_of_date: str
    include_boards: tuple[str, ...] = (BOARD_MAIN, BOARD_CHINEXT)
    exclude_boards: tuple[str, ...] = (BOARD_STAR, BOARD_BEIJING)
    exclude_st: bool = True
    exclude_suspended: bool = True
    min_listed_days: int = RESEARCH_DEFAULT_MIN_LISTED_DAYS
    include_recent_ipo: bool = False
    min_avg_turnover_amount: float | None = DEFAULT_MIN_AVG_TURNOVER_AMOUNT
    min_avg_volume: float | None = None
    liquidity_lookback_days: int = DEFAULT_LIQUIDITY_LOOKBACK_DAYS
    exclude_long_suspended: bool = True
    max_suspended_days: int = DEFAULT_MAX_SUSPENDED_DAYS
    include_watchlist: bool = False
    watchlist_only: bool = False
    allow_missing_industry: bool = True
    allow_missing_valuation: bool = True
    preset: str = "research_default"
    watchlist_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class UniverseMember:
    trade_date: str
    asset_id: str
    stock_code: str
    stock_name: str
    board: str
    listed_days: int | None
    is_st: bool | None
    is_suspended: bool | None
    avg_turnover_amount: float | None
    avg_volume: float | None
    industry: str | None
    included: bool
    include_reasons: list[str] = field(default_factory=list)
    exclude_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UniverseResult:
    config: UniverseConfig
    as_of_date: str
    total_candidates: int
    included_count: int
    excluded_count: int
    members: list[UniverseMember]
    included_codes: list[str]
    excluded_codes: list[str]
    summary_by_reason: dict[str, dict[str, int]]
    warnings: list[str]

    @property
    def member_map(self) -> dict[str, UniverseMember]:
        return {member.stock_code: member for member in self.members}


@dataclass(frozen=True)
class UniverseFrames:
    assets: pd.DataFrame
    statuses: pd.DataFrame
    liquidity: pd.DataFrame
    industries: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


FrameLoader = Callable[[UniverseConfig, list[str] | None], UniverseFrames]


def get_universe_preset(
    as_of_date: object,
    preset: str,
    *,
    watchlist_codes: list[str] | tuple[str, ...] | None = None,
    **overrides: Any,
) -> UniverseConfig:
    date_text = _date_text(as_of_date)
    codes = tuple(_normalize_codes(watchlist_codes or []))
    normalized_preset = str(preset or "research_default")

    if normalized_preset == "research_default":
        config = UniverseConfig(
            as_of_date=date_text,
            preset=normalized_preset,
            include_boards=(BOARD_MAIN, BOARD_CHINEXT),
            exclude_boards=(BOARD_STAR, BOARD_BEIJING),
            exclude_st=True,
            exclude_suspended=True,
            min_listed_days=RESEARCH_DEFAULT_MIN_LISTED_DAYS,
            include_recent_ipo=False,
            min_avg_turnover_amount=DEFAULT_MIN_AVG_TURNOVER_AMOUNT,
            liquidity_lookback_days=DEFAULT_LIQUIDITY_LOOKBACK_DAYS,
            exclude_long_suspended=True,
            max_suspended_days=DEFAULT_MAX_SUSPENDED_DAYS,
            include_watchlist=False,
            watchlist_only=False,
            allow_missing_industry=True,
            allow_missing_valuation=True,
            watchlist_codes=codes,
        )
    elif normalized_preset == "include_recent_ipo":
        config = UniverseConfig(
            as_of_date=date_text,
            preset=normalized_preset,
            include_boards=(BOARD_MAIN, BOARD_CHINEXT),
            exclude_boards=(BOARD_STAR, BOARD_BEIJING),
            exclude_st=True,
            exclude_suspended=True,
            min_listed_days=INCLUDE_RECENT_IPO_MIN_LISTED_DAYS,
            include_recent_ipo=True,
            min_avg_turnover_amount=DEFAULT_MIN_AVG_TURNOVER_AMOUNT,
            liquidity_lookback_days=DEFAULT_LIQUIDITY_LOOKBACK_DAYS,
            exclude_long_suspended=True,
            max_suspended_days=DEFAULT_MAX_SUSPENDED_DAYS,
            include_watchlist=False,
            watchlist_only=False,
            allow_missing_industry=True,
            allow_missing_valuation=True,
            watchlist_codes=codes,
        )
    elif normalized_preset == "watchlist_check":
        config = UniverseConfig(
            as_of_date=date_text,
            preset=normalized_preset,
            include_boards=(BOARD_MAIN, BOARD_CHINEXT),
            exclude_boards=(BOARD_STAR, BOARD_BEIJING),
            exclude_st=True,
            exclude_suspended=True,
            min_listed_days=RESEARCH_DEFAULT_MIN_LISTED_DAYS,
            include_recent_ipo=False,
            min_avg_turnover_amount=DEFAULT_MIN_AVG_TURNOVER_AMOUNT,
            liquidity_lookback_days=DEFAULT_LIQUIDITY_LOOKBACK_DAYS,
            exclude_long_suspended=True,
            max_suspended_days=DEFAULT_MAX_SUSPENDED_DAYS,
            include_watchlist=True,
            watchlist_only=True,
            allow_missing_industry=True,
            allow_missing_valuation=True,
            watchlist_codes=codes,
        )
    else:
        raise ValueError(f"unsupported universe preset: {normalized_preset}")

    if overrides:
        config = UniverseConfig(**{**asdict(config), **overrides})
    return config


def build_universe_from_frames(
    *,
    assets: pd.DataFrame,
    statuses: pd.DataFrame,
    liquidity: pd.DataFrame,
    industries: pd.DataFrame,
    config: UniverseConfig,
) -> UniverseResult:
    warnings: list[str] = []
    prepared_assets = _prepare_assets_frame(assets)
    prepared_statuses = _prepare_statuses_frame(statuses)
    prepared_liquidity = _prepare_liquidity_frame(liquidity)
    prepared_industries, industry_warnings = _prepare_industries_frame(industries)
    warnings.extend(industry_warnings)

    if config.watchlist_only and config.watchlist_codes:
        watchlist_set = set(config.watchlist_codes)
        prepared_assets = prepared_assets[
            prepared_assets["stock_code"].isin(watchlist_set)
        ].copy()
        missing_watchlist_codes = sorted(watchlist_set - set(prepared_assets["stock_code"]))
        warnings.extend(
            [f"watchlist_code_not_found:{code}" for code in missing_watchlist_codes]
        )
    elif config.watchlist_only:
        warnings.append("watchlist_only_without_watchlist_codes")
        prepared_assets = prepared_assets.iloc[0:0].copy()

    merged = prepared_assets.merge(prepared_statuses, on="asset_id", how="left")
    merged = merged.merge(prepared_liquidity, on="asset_id", how="left")
    merged = merged.merge(prepared_industries, on="asset_id", how="left")

    if "valuation" not in merged.columns and not config.allow_missing_valuation:
        warnings.append("valuation_data_unavailable")

    members: list[UniverseMember] = []
    include_counter: Counter[str] = Counter()
    exclude_counter: Counter[str] = Counter()
    as_of = pd.Timestamp(config.as_of_date)
    watchlist_set = set(config.watchlist_codes)

    for record in merged.to_dict("records"):
        member = _build_universe_member(
            record=record,
            as_of=as_of,
            config=config,
            watchlist_codes=watchlist_set,
            warnings=warnings,
        )
        include_counter.update(member.include_reasons)
        exclude_counter.update(member.exclude_reasons)
        members.append(member)

    included_codes = [member.stock_code for member in members if member.included]
    excluded_codes = [member.stock_code for member in members if not member.included]
    return UniverseResult(
        config=config,
        as_of_date=config.as_of_date,
        total_candidates=len(members),
        included_count=len(included_codes),
        excluded_count=len(excluded_codes),
        members=members,
        included_codes=included_codes,
        excluded_codes=excluded_codes,
        summary_by_reason={
            "include": dict(include_counter),
            "exclude": dict(exclude_counter),
        },
        warnings=sorted(set(warnings)),
    )


class UniverseService:
    def __init__(
        self,
        *,
        frame_loader: FrameLoader | None = None,
    ) -> None:
        self._frame_loader = frame_loader or self._load_frames_from_service

    def build_universe(self, config: UniverseConfig) -> UniverseResult:
        frames = self._frame_loader(config, list(config.watchlist_codes))
        result = build_universe_from_frames(
            assets=frames.assets,
            statuses=frames.statuses,
            liquidity=frames.liquidity,
            industries=frames.industries,
            config=config,
        )
        warnings = sorted(set([*result.warnings, *frames.warnings]))
        if warnings == result.warnings:
            return result
        return UniverseResult(
            config=result.config,
            as_of_date=result.as_of_date,
            total_candidates=result.total_candidates,
            included_count=result.included_count,
            excluded_count=result.excluded_count,
            members=result.members,
            included_codes=result.included_codes,
            excluded_codes=result.excluded_codes,
            summary_by_reason=result.summary_by_reason,
            warnings=warnings,
        )

    def explain_stock(
        self,
        stock_code: str,
        as_of_date: object,
        config: UniverseConfig | None = None,
    ) -> UniverseMember:
        effective_config = config or get_universe_preset(as_of_date, "research_default")
        if _date_text(as_of_date) != effective_config.as_of_date:
            effective_config = UniverseConfig(
                **{**asdict(effective_config), "as_of_date": _date_text(as_of_date)}
            )
        result = self.build_universe(effective_config)
        normalized_code = str(stock_code).strip().upper()
        for member in result.members:
            if member.stock_code == normalized_code or member.asset_id == normalized_code:
                return member
        raise KeyError(f"stock not found in evaluated universe: {stock_code}")

    def filter_dataframe(
        self,
        df: pd.DataFrame,
        config: UniverseConfig,
        code_col: str = "stock_code",
        date_col: str = "trade_date",
    ) -> pd.DataFrame:
        result = self.build_universe(config)
        filtered = filter_dataframe_by_universe(
            df,
            result,
            code_col=code_col,
        )
        if date_col in filtered.columns:
            filtered[date_col] = filtered[date_col].map(_date_text)
        return filtered.reset_index(drop=True)

    def summarize(self, result: UniverseResult) -> dict[str, Any]:
        return {
            "as_of_date": result.as_of_date,
            "preset": result.config.preset,
            "total_candidates": result.total_candidates,
            "included_count": result.included_count,
            "excluded_count": result.excluded_count,
            "summary_by_reason": result.summary_by_reason,
            "warnings": result.warnings,
        }

    def _load_frames_from_service(
        self,
        config: UniverseConfig,
        watchlist_codes: list[str] | None = None,
    ) -> UniverseFrames:
        watchlist_codes = watchlist_codes or []
        asset_sql = """
        SELECT
            asset_id,
            ts_code,
            symbol,
            name,
            exchange,
            board,
            list_date,
            delist_date,
            is_active,
            is_beijing,
            is_star,
            is_chinext
        FROM core.asset_master
        WHERE list_date IS NULL OR list_date <= %s
        ORDER BY asset_id
        """
        status_sql = """
        SELECT
            trade_date,
            asset_id,
            is_trade,
            is_st,
            is_suspended
        FROM core.asset_status_daily
        WHERE trade_date = %s
        ORDER BY asset_id
        """
        industry_sql = """
        SELECT DISTINCT ON (asset_id)
            asset_id,
            %s::date AS trade_date,
            industry_name AS industry
        FROM core.industry_membership
        WHERE start_date <= %s
          AND (end_date IS NULL OR end_date > %s)
        ORDER BY asset_id, start_date DESC
        """
        liquidity_sql = """
        WITH lookback_dates AS (
            SELECT DISTINCT trade_date
            FROM market_daily_bar
            WHERE adjust_type = 'hfq'
              AND trade_date <= %s
            ORDER BY trade_date DESC
            LIMIT %s
        ),
        liquidity AS (
            SELECT
                bars.asset_id,
                avg(bars.amount) AS avg_turnover_amount,
                avg(bars.volume) AS avg_volume
            FROM market_daily_bar bars
            JOIN lookback_dates dates
              ON dates.trade_date = bars.trade_date
            WHERE bars.adjust_type = 'hfq'
            GROUP BY bars.asset_id
        ),
        suspension AS (
            SELECT
                status.asset_id,
                count(*) FILTER (WHERE status.is_suspended) AS suspended_days_lookback
            FROM core.asset_status_daily status
            JOIN lookback_dates dates
              ON dates.trade_date = status.trade_date
            GROUP BY status.asset_id
        )
        SELECT
            coalesce(liquidity.asset_id, suspension.asset_id) AS asset_id,
            liquidity.avg_turnover_amount,
            liquidity.avg_volume,
            coalesce(suspension.suspended_days_lookback, 0) AS suspended_days_lookback,
            %s::date AS trade_date
        FROM liquidity
        FULL OUTER JOIN suspension
          ON suspension.asset_id = liquidity.asset_id
        ORDER BY asset_id
        """
        warnings: list[str] = []
        with connect(SETTINGS.research_service) as conn:
            assets = pd.DataFrame(fetch_all(conn, asset_sql, [config.as_of_date]))
            statuses = pd.DataFrame(fetch_all(conn, status_sql, [config.as_of_date]))
            industries = pd.DataFrame(
                fetch_all(
                    conn,
                    industry_sql,
                    [config.as_of_date, config.as_of_date, config.as_of_date],
                )
            )
            liquidity = pd.DataFrame(
                fetch_all(
                    conn,
                    liquidity_sql,
                    [config.as_of_date, config.liquidity_lookback_days, config.as_of_date],
                )
            )
        if config.watchlist_only and not watchlist_codes:
            warnings.append("watchlist_only_without_watchlist_codes")
        return UniverseFrames(
            assets=assets,
            statuses=statuses,
            liquidity=liquidity,
            industries=industries,
            warnings=warnings,
        )


def load_watchlist_codes(path: str | Path) -> list[str]:
    frame = pd.read_csv(path)
    for column in ("stock_code", "ts_code", "code", "asset_id", "symbol"):
        if column in frame.columns:
            return _normalize_codes(frame[column].dropna().astype(str).tolist())
    raise ValueError("watchlist file must contain one of: stock_code, ts_code, code, asset_id, symbol")


def write_universe_artifacts(
    result: UniverseResult,
    output_dir: str | Path,
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    members_frame = pd.DataFrame(
        [
            {
                **asdict(member),
                "include_reasons": json.dumps(member.include_reasons, ensure_ascii=False),
                "exclude_reasons": json.dumps(member.exclude_reasons, ensure_ascii=False),
            }
            for member in result.members
        ]
    )
    included_frame = members_frame[members_frame["included"]].reset_index(drop=True)
    excluded_frame = members_frame[~members_frame["included"]].reset_index(drop=True)

    summary = {
        "as_of_date": result.as_of_date,
        "preset": result.config.preset,
        "total_candidates": result.total_candidates,
        "included_count": result.included_count,
        "excluded_count": result.excluded_count,
        "summary_by_reason": result.summary_by_reason,
        "warnings": result.warnings,
        "config": asdict(result.config),
    }

    members_path = out / "universe_members.csv"
    included_path = out / "universe_included.csv"
    excluded_path = out / "universe_excluded.csv"
    summary_path = out / "universe_summary.json"
    warnings_path = out / "universe_warnings.md"

    members_frame.to_csv(members_path, index=False)
    included_frame.to_csv(included_path, index=False)
    excluded_frame.to_csv(excluded_path, index=False)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    warning_lines = ["# Universe Warnings", ""]
    if result.warnings:
        warning_lines.extend([f"- {warning}" for warning in result.warnings])
    else:
        warning_lines.append("- none")
    warnings_path.write_text("\n".join(warning_lines) + "\n", encoding="utf-8")

    return {
        "members_path": str(members_path),
        "included_path": str(included_path),
        "excluded_path": str(excluded_path),
        "summary_path": str(summary_path),
        "warnings_path": str(warnings_path),
    }


def get_universe_allowed_ids(universe_result: UniverseResult | None) -> set[str] | None:
    if universe_result is None:
        return None
    return {
        str(identifier)
        for member in universe_result.members
        if member.included
        for identifier in (member.asset_id, member.stock_code)
    }


def filter_dataframe_by_universe(
    frame: pd.DataFrame,
    universe_result: UniverseResult | None,
    *,
    code_col: str | None = None,
    asset_id_col: str | None = None,
) -> pd.DataFrame:
    if universe_result is None or frame.empty:
        return frame.copy()

    candidate_columns = [
        asset_id_col,
        code_col,
        "asset_id",
        "stock_code",
        "ts_code",
        "code",
        "symbol",
    ]
    target_column = next(
        (column for column in candidate_columns if column and column in frame.columns),
        None,
    )
    if target_column is None:
        raise ValueError(
            "missing usable universe identifier column; expected one of: "
            "asset_id, stock_code, ts_code, code, symbol"
        )

    allowed = get_universe_allowed_ids(universe_result)
    if allowed is None:
        return frame.copy()
    if not allowed:
        return frame.iloc[0:0].copy()

    result = frame.copy()
    result[target_column] = result[target_column].astype(str).str.upper()
    return result[result[target_column].isin(allowed)].reset_index(drop=True)


def _prepare_assets_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"asset_id", "name", "exchange", "list_date", "is_beijing", "is_star", "is_chinext"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns in assets frame: {', '.join(missing)}")
    result = frame.copy()
    result["asset_id"] = result["asset_id"].astype(str)
    result["stock_code"] = result.apply(_stock_code_from_row, axis=1)
    result["stock_name"] = result["name"].astype(str)
    result["board_normalized"] = result.apply(_normalize_board, axis=1)
    result["list_date"] = pd.to_datetime(result["list_date"], errors="coerce")
    return result


def _prepare_statuses_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "is_trade", "is_st", "is_suspended"])
    required = {"asset_id", "is_trade", "is_st", "is_suspended"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns in statuses frame: {', '.join(missing)}")
    result = frame.copy()
    result["asset_id"] = result["asset_id"].astype(str)
    return result[["asset_id", "is_trade", "is_st", "is_suspended"]].drop_duplicates("asset_id")


def _prepare_liquidity_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=["asset_id", "avg_turnover_amount", "avg_volume", "suspended_days_lookback"]
        )
    required = {"asset_id"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns in liquidity frame: {', '.join(missing)}")
    result = frame.copy()
    result["asset_id"] = result["asset_id"].astype(str)
    for column in ("avg_turnover_amount", "avg_volume", "suspended_days_lookback"):
        if column not in result.columns:
            result[column] = None if column != "suspended_days_lookback" else 0
    return result[
        ["asset_id", "avg_turnover_amount", "avg_volume", "suspended_days_lookback"]
    ].drop_duplicates("asset_id")


def _prepare_industries_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "industry"]), ["industry_data_missing"]
    result = frame.copy()
    warnings: list[str] = []
    if "asset_id" not in result.columns:
        raise ValueError("missing required columns in industries frame: asset_id")
    if "industry" not in result.columns:
        if "industry_name" in result.columns:
            result["industry"] = result["industry_name"]
        else:
            warnings.append("industry_data_missing")
            result["industry"] = None
    result["asset_id"] = result["asset_id"].astype(str)
    return result[["asset_id", "industry"]].drop_duplicates("asset_id"), warnings


def _build_universe_member(
    *,
    record: dict[str, Any],
    as_of: pd.Timestamp,
    config: UniverseConfig,
    watchlist_codes: set[str],
    warnings: list[str],
) -> UniverseMember:
    include_reasons: list[str] = []
    exclude_reasons: list[str] = []

    stock_code = str(record["stock_code"]).upper()
    board = str(record.get("board_normalized") or BOARD_UNKNOWN)
    list_date = record.get("list_date")
    listed_days = None
    if pd.notna(list_date):
        listed_days = int((as_of.normalize() - pd.Timestamp(list_date).normalize()).days)

    is_trade = _optional_bool(record.get("is_trade"))
    is_st = _optional_bool(record.get("is_st"))
    is_suspended = _optional_bool(record.get("is_suspended"))
    avg_turnover_amount = _optional_float(record.get("avg_turnover_amount"))
    avg_volume = _optional_float(record.get("avg_volume"))
    suspended_days_lookback = int(record.get("suspended_days_lookback") or 0)
    industry = _optional_text(record.get("industry"))
    valuation = record.get("valuation")
    is_watchlist = stock_code in watchlist_codes

    if is_watchlist and config.include_watchlist:
        include_reasons.append("watchlist_member")
    if config.watchlist_only and not is_watchlist:
        exclude_reasons.append("not_in_watchlist")

    if board in set(config.exclude_boards):
        exclude_reasons.append(f"excluded_board:{board}")
    elif config.include_boards and board not in set(config.include_boards):
        exclude_reasons.append(f"board_not_included:{board}")
    else:
        include_reasons.append(f"board_allowed:{board}")

    if config.exclude_st and is_st is True:
        exclude_reasons.append("st")

    if config.exclude_suspended:
        if is_trade is False or is_suspended is True:
            exclude_reasons.append("suspended")
        elif is_trade is None and is_suspended is None:
            warnings.append(f"missing_status:{stock_code}")
            exclude_reasons.append("missing_status")

    if listed_days is None:
        warnings.append(f"missing_list_date:{stock_code}")
        exclude_reasons.append("missing_list_date")
    elif listed_days < config.min_listed_days:
        if config.include_recent_ipo:
            include_reasons.append("recent_ipo_allowed")
        else:
            exclude_reasons.append(f"listed_days_below_min:{config.min_listed_days}")
    elif config.include_recent_ipo and listed_days < RESEARCH_DEFAULT_MIN_LISTED_DAYS:
        include_reasons.append("recent_ipo_allowed")

    if (
        config.min_avg_turnover_amount is not None
        and (avg_turnover_amount is None or avg_turnover_amount < config.min_avg_turnover_amount)
    ):
        exclude_reasons.append("low_turnover_amount")

    if config.min_avg_volume is not None and (
        avg_volume is None or avg_volume < config.min_avg_volume
    ):
        exclude_reasons.append("low_volume")

    if config.exclude_long_suspended and suspended_days_lookback > config.max_suspended_days:
        exclude_reasons.append("long_suspended")

    if not config.allow_missing_industry and not industry:
        exclude_reasons.append("missing_industry")
    elif industry:
        include_reasons.append("industry_present")

    if not config.allow_missing_valuation and valuation in (None, ""):
        exclude_reasons.append("missing_valuation")

    member = UniverseMember(
        trade_date=config.as_of_date,
        asset_id=str(record["asset_id"]),
        stock_code=stock_code,
        stock_name=str(record["stock_name"]),
        board=board,
        listed_days=listed_days,
        is_st=is_st,
        is_suspended=is_suspended,
        avg_turnover_amount=avg_turnover_amount,
        avg_volume=avg_volume,
        industry=industry,
        included=not exclude_reasons,
        include_reasons=sorted(set(include_reasons)),
        exclude_reasons=sorted(set(exclude_reasons)),
    )
    return member


def _normalize_board(row: pd.Series) -> str:
    if bool(row.get("is_star")):
        return BOARD_STAR
    if bool(row.get("is_beijing")):
        return BOARD_BEIJING
    if bool(row.get("is_chinext")):
        return BOARD_CHINEXT

    board_text = str(row.get("board") or "").strip().lower()
    exchange = str(row.get("exchange") or "").strip().upper()
    if "star" in board_text or "科创" in board_text:
        return BOARD_STAR
    if "beijing" in board_text or "北交" in board_text or exchange == "BSE":
        return BOARD_BEIJING
    if "chinext" in board_text or "创业" in board_text:
        return BOARD_CHINEXT
    if exchange in {"SSE", "SZSE"}:
        return BOARD_MAIN
    return BOARD_UNKNOWN


def _stock_code_from_row(row: pd.Series) -> str:
    ts_code = str(row.get("ts_code") or "").strip().upper()
    if ts_code:
        return ts_code
    asset_id = str(row.get("asset_id") or "").strip()
    symbol = str(row.get("symbol") or "").strip()
    exchange = str(row.get("exchange") or "").strip().upper()
    if symbol and exchange == "SSE":
        return f"{symbol}.SH"
    if symbol and exchange == "SZSE":
        return f"{symbol}.SZ"
    if symbol and exchange == "BSE":
        return f"{symbol}.BJ"
    return asset_id.upper()


def _date_text(value: object) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _normalize_codes(values: list[str] | tuple[str, ...]) -> list[str]:
    return [str(value).strip().upper() for value in values if str(value).strip()]


def _optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(value)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
