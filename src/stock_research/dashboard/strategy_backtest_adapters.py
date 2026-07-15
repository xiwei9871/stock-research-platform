from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.dashboard.bars import normalize_market_asset_id
from stock_research.db import connect, fetch_all
from stock_research.strategy_backtest_read_model import (
    import_strategy_backtest_replay_payload,
    load_strategy_backtest_replay_payload,
    normalize_replay_payload_to_requested_window,
)


@dataclass(frozen=True)
class StrategyBacktestParams:
    start_date: str
    end_date: str
    score_version: str = "manual_v1"
    adjust_type: str = "hfq"


class StrategyBacktestAdapter(Protocol):
    strategy_id: str

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class ArtifactReplayConfig:
    strategy_id: str
    strategy_name: str
    combo_scheme: str
    evidence_source: str
    summary_path: str | Path
    summary_filters: dict[str, object]
    equity_path: str | Path | None = None
    equity_filters: dict[str, object] | None = None
    positions_path: str | Path | None = None
    positions_filters: dict[str, object] | None = None
    trades_path: str | Path | None = None
    trades_filters: dict[str, object] | None = None
    summary_aliases: dict[str, str] | None = None


class ArtifactReplayAdapter:
    def __init__(self, config: ArtifactReplayConfig):
        self.config = config
        self.strategy_id = config.strategy_id
        self.strategy_name = config.strategy_name
        self.combo_scheme = config.combo_scheme

    def run_replay(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        can_import_to_read_model = True
        try:
            stored = load_strategy_backtest_replay_payload(
                self.strategy_id,
                start_date=params.start_date,
                end_date=params.end_date,
                combo_scheme=self.combo_scheme,
            )
        except (psycopg_errors.InvalidSchemaName, psycopg_errors.UndefinedTable):
            stored = None
            can_import_to_read_model = False
        if stored is not None:
            return stored

        payload = normalize_replay_payload_to_requested_window(self._build_artifact_payload(params, run_config))
        if can_import_to_read_model:
            import_strategy_backtest_replay_payload(payload)
        return payload

    def run_validated_backtest(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_replay_payload_to_requested_window(self._build_artifact_payload(params, run_config))
        payload["read_only"] = False
        payload["source_kind"] = "validated_combo_artifact_rerun"
        return payload

    def _build_artifact_payload(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        summary = self._load_summary(params)
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "read_only": True,
            "config": {
                "start_date": params.start_date,
                "end_date": params.end_date,
                "score_version": params.score_version,
                "adjust_type": params.adjust_type,
                **run_config,
            },
            "source_kind": "artifact_bootstrap",
            "source_paths": _config_source_paths(self.config),
            "summary": summary,
            "equity_curve": _artifact_records(
                self.config.equity_path,
                self.config.equity_filters,
                params,
                date_columns=("date", "trade_date"),
            ),
            "positions": _artifact_records(
                self.config.positions_path,
                self.config.positions_filters,
                params,
                date_columns=("rebalance_date", "trade_date", "date"),
            ),
            "trades": _artifact_records(
                self.config.trades_path,
                self.config.trades_filters,
                params,
                date_columns=("trade_date", "execution_date", "date"),
            ),
        }

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise ValueError(f"{self.strategy_id} uses validated combo replay, not vectorized TopN scores")

    def _load_summary(self, params: StrategyBacktestParams) -> dict[str, Any]:
        frame = _read_artifact_frame(self.config.summary_path)
        row = _filter_artifact_frame(frame, self.config.summary_filters or {}).iloc[0].to_dict()
        aliases = self.config.summary_aliases or {}
        summary = {str(key): _jsonable(value) for key, value in row.items()}
        for target_key, source_key in aliases.items():
            if source_key in row:
                summary[target_key] = _jsonable(row[source_key])
        if "final_equity" in summary and "total_return" not in summary:
            summary["total_return"] = float(summary["final_equity"]) - 1.0
        summary["combo_scheme"] = self.config.combo_scheme
        summary["evidence_source"] = self.config.evidence_source
        summary["requested_start_date"] = params.start_date
        summary["requested_end_date"] = params.end_date
        return summary


class FreshReplayBacktestAdapter:
    def __init__(self, fresh_adapter: StrategyBacktestAdapter, replay_adapter: Any):
        if fresh_adapter.strategy_id != replay_adapter.strategy_id:
            raise ValueError("fresh and replay adapters must use the same strategy_id")
        self.fresh_adapter = fresh_adapter
        self.replay_adapter = replay_adapter
        self.strategy_id = fresh_adapter.strategy_id
        self.strategy_name = getattr(replay_adapter, "strategy_name", self.strategy_id)
        self.combo_scheme = getattr(replay_adapter, "combo_scheme", None)
        self.config = getattr(replay_adapter, "config", None)

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return self.fresh_adapter.load_scores(params)

    def run_replay(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        return self.replay_adapter.run_replay(params, run_config)

    def run_validated_backtest(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        return self.replay_adapter.run_validated_backtest(params, run_config)


class LHBPhase16CReplayAdapter(ArtifactReplayAdapter):
    def __init__(
        self,
        config: ArtifactReplayConfig,
        *,
        lifecycle_trades_path: str | Path,
        real_entry_trades_path: str | Path,
        replacement_return_column: str,
        adjust_reason: str,
    ):
        super().__init__(config)
        self.lifecycle_trades_path = lifecycle_trades_path
        self.real_entry_trades_path = real_entry_trades_path
        self.replacement_return_column = replacement_return_column
        self.adjust_reason = adjust_reason

    def _build_artifact_payload(self, params: StrategyBacktestParams, run_config: dict[str, Any]) -> dict[str, Any]:
        payload = super()._build_artifact_payload(params, run_config)
        lifecycle_trades = _read_artifact_frame(self.lifecycle_trades_path)
        real_entry_trades = _read_artifact_frame(self.real_entry_trades_path)
        account_trades, account_curve = build_lhb_phase16c_account_replay_frames(
            lifecycle_trades=lifecycle_trades,
            real_entry_trades=real_entry_trades,
            replacement_return_column=self.replacement_return_column,
            adjust_reason=self.adjust_reason,
        )
        if not account_curve.empty:
            equity_values = pd.to_numeric(account_curve["equity"], errors="coerce").dropna()
            drawdown_values = pd.to_numeric(account_curve["drawdown"], errors="coerce").dropna()
            if not equity_values.empty:
                payload["summary"]["final_equity"] = _jsonable(equity_values.iloc[-1])
                payload["summary"]["total_return"] = _jsonable(equity_values.iloc[-1] - 1.0)
            if not drawdown_values.empty:
                payload["summary"]["max_drawdown"] = _jsonable(drawdown_values.min())
            payload["summary"]["detail_source"] = "phase16c_rebuilt_cash_account"
            payload["summary"]["mark_to_market"] = False
            payload["summary"]["risk_metric_caveat"] = (
                "LHB lifecycle cash replay is event-based and not daily marked to market; "
                "drawdown, Sharpe, and turnover are not strict daily risk metrics."
            )
        if "ts_code" in account_trades.columns and "asset_id" not in account_trades.columns:
            account_trades = account_trades.copy()
            account_trades["asset_id"] = account_trades["ts_code"].map(normalize_market_asset_id)
        payload["equity_curve"] = _frame_records(
            _filter_artifact_dates(account_curve, params, ("trade_date",)),
        )
        payload["trades"] = _frame_records(
            _filter_artifact_dates(account_trades, params, ("trade_date", "entry_trade_date", "exit_trade_date")),
        )
        payload["source_paths"] = [
            *payload.get("source_paths", []),
            str(self.lifecycle_trades_path),
            str(self.real_entry_trades_path),
        ]
        return payload


def normalize_strategy_scores(frame: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")
    required = {"trade_date", "asset_id", "score_total"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{strategy_id} scores missing columns: {', '.join(sorted(missing))}")

    normalized = frame.copy()
    normalized["score_total"] = pd.to_numeric(normalized["score_total"], errors="coerce")
    normalized = normalized.dropna(subset=["trade_date", "asset_id", "score_total"])
    if normalized.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")

    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"]).dt.strftime("%Y-%m-%d")
    normalized["asset_id"] = normalized["asset_id"].map(normalize_market_asset_id)

    normalized = normalized.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    normalized["rank"] = normalized.groupby("trade_date").cumcount() + 1
    normalized["strategy_id"] = strategy_id
    if "score_components" not in normalized.columns:
        normalized["score_components"] = [{} for _ in range(len(normalized))]
    if "eligibility" not in normalized.columns:
        normalized["eligibility"] = True
    normalized["eligibility"] = normalized["eligibility"].map(lambda value: bool(value)).astype(object)
    if "eligibility_reason" not in normalized.columns:
        normalized["eligibility_reason"] = "eligible"
    if "exposure_scale" not in normalized.columns:
        normalized["exposure_scale"] = 1.0
    return normalized[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_components",
            "strategy_id",
            "eligibility",
            "eligibility_reason",
            "exposure_scale",
        ]
    ]


def _artifact_root() -> Path:
    for candidate in _artifact_root_candidates():
        if (candidate / "outputs" / "research").exists():
            return candidate
    return _artifact_root_candidates()[0]


def _artifact_root_candidates() -> list[Path]:
    return [
        Path.cwd(),
        Path(__file__).resolve().parents[3],
        Path.home() / "stock_research",
    ]


def _artifact_path(path: str | Path) -> Path:
    parsed = Path(path)
    if parsed.is_absolute():
        return parsed
    for candidate in _artifact_root_candidates():
        resolved = candidate / parsed
        if resolved.exists():
            return resolved
    return _artifact_root() / parsed


def _config_source_paths(config: ArtifactReplayConfig) -> list[str]:
    paths = [
        config.summary_path,
        config.equity_path,
        config.positions_path,
        config.trades_path,
    ]
    return [str(path) for path in paths if path is not None]


def _read_artifact_frame(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    resolved = _artifact_path(path)
    if not resolved.exists():
        raise ValueError(f"validated replay artifact not found: {resolved}")
    return pd.read_csv(resolved)


def _filter_artifact_frame(frame: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    filtered = frame.copy()
    for column, expected in filters.items():
        if column not in filtered.columns:
            raise ValueError(f"validated replay artifact missing filter column: {column}")
        filtered = filtered[filtered[column].astype(str) == str(expected)]
    if filtered.empty:
        raise ValueError(f"validated replay artifact has no rows for filters: {filters}")
    return filtered.reset_index(drop=True)


def _filter_artifact_dates(frame: pd.DataFrame, params: StrategyBacktestParams, date_columns: tuple[str, ...]) -> pd.DataFrame:
    for column in date_columns:
        if column in frame.columns:
            dates = pd.to_datetime(frame[column], errors="coerce")
            start = pd.Timestamp(params.start_date)
            end = pd.Timestamp(params.end_date)
            return frame[(dates >= start) & (dates <= end)].reset_index(drop=True)
    return frame


def _artifact_records(
    path: str | Path | None,
    filters: dict[str, object] | None,
    params: StrategyBacktestParams,
    *,
    date_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    if path is None:
        return []
    frame = _read_artifact_frame(path)
    filters = filters or {}
    if filters:
        frame = _filter_artifact_frame(frame, filters)
        frame = frame.drop(columns=[column for column in filters if column in frame.columns])
    frame = _filter_artifact_dates(frame, params, date_columns)
    return _frame_records(frame)


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict("records")]


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def build_lhb_phase16c_account_replay_frames(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    replacement_return_column: str,
    adjust_reason: str,
    max_positions: int = 10,
    position_pct: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    adjusted = _build_lhb_phase16c_adjusted_lifecycle_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        replacement_return_column=replacement_return_column,
        adjust_reason=adjust_reason,
    )
    return _build_lhb_cash_account_frames(
        lifecycle_trades=adjusted,
        max_positions=max_positions,
        position_pct=position_pct,
    )


def _build_lhb_phase16c_adjusted_lifecycle_frame(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    replacement_return_column: str,
    adjust_reason: str,
) -> pd.DataFrame:
    trades = lifecycle_trades.copy()
    for column in ["trade_date", "ts_code", "top_n", "fill_status", "exit_signal", "realized_return"]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["ts_code"] = trades["ts_code"].astype(str)
    trades["top_n"] = pd.to_numeric(trades["top_n"], errors="coerce")
    trades["realized_return"] = pd.to_numeric(trades["realized_return"], errors="coerce")

    real_entry = real_entry_trades.copy()
    for column in ["trade_date", "ts_code", "top_n", replacement_return_column]:
        if column not in real_entry.columns:
            real_entry[column] = pd.NA
    real_entry["trade_date"] = pd.to_datetime(real_entry["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    real_entry["ts_code"] = real_entry["ts_code"].astype(str)
    real_entry["top_n"] = pd.to_numeric(real_entry["top_n"], errors="coerce")
    real_entry[replacement_return_column] = pd.to_numeric(real_entry[replacement_return_column], errors="coerce")
    real_entry = real_entry.drop_duplicates(["trade_date", "ts_code", "top_n"])

    merged = trades.merge(
        real_entry[["trade_date", "ts_code", "top_n", replacement_return_column]],
        on=["trade_date", "ts_code", "top_n"],
        how="left",
    )
    replacement = pd.to_numeric(merged[replacement_return_column], errors="coerce")
    replace_mask = (
        merged["fill_status"].eq("filled")
        & merged["exit_signal"].eq("limit_break_failed")
        & replacement.notna()
    )
    merged["original_realized_return"] = merged["realized_return"]
    merged["phase16c_adjust_reason"] = ""
    merged.loc[replace_mask, "realized_return"] = replacement.loc[replace_mask]
    merged.loc[replace_mask, "phase16c_adjust_reason"] = adjust_reason
    return merged


def _build_lhb_cash_account_frames(
    *,
    lifecycle_trades: pd.DataFrame,
    max_positions: int,
    position_pct: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trade_columns = [
        "account_trade_status",
        "trade_date",
        "ts_code",
        "top_n",
        "phase12a_rule_layer",
        "entry_trade_date",
        "entry_price",
        "exit_trade_date",
        "exit_price",
        "realized_return",
        "position_notional",
        "pnl",
        "skip_reason",
    ]
    curve_columns = [
        "trade_date",
        "cash",
        "invested_notional",
        "equity",
        "drawdown",
        "open_position_count",
        "opened_count",
        "closed_count",
        "daily_realized_pnl",
    ]
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=trade_columns), pd.DataFrame(columns=curve_columns)

    trades = lifecycle_trades.copy()
    for column in [
        "fill_status",
        "entry_trade_date",
        "exit_trade_date",
        "ts_code",
        "realized_return",
        "top_n",
        "phase12a_rule_layer",
        "trade_date",
        "entry_price",
        "exit_price",
    ]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["entry_trade_date"] = pd.to_datetime(trades["entry_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["exit_trade_date"] = pd.to_datetime(trades["exit_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["realized_return"] = pd.to_numeric(trades["realized_return"], errors="coerce")
    candidates = trades[
        trades["fill_status"].eq("filled")
        & trades["entry_trade_date"].notna()
        & trades["exit_trade_date"].notna()
        & trades["realized_return"].notna()
    ].copy()
    candidates = candidates.sort_values(["entry_trade_date", "trade_date", "top_n", "ts_code"], kind="stable")

    dates = sorted(set(candidates["entry_trade_date"].dropna()) | set(candidates["exit_trade_date"].dropna()))
    cash = 1.0
    running_max = 1.0
    open_positions: dict[str, dict[str, Any]] = {}
    account_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    trade_records: dict[int, dict[str, Any]] = {}
    by_entry = {date: group for date, group in candidates.groupby("entry_trade_date", sort=False)}

    for date in dates:
        opened_count = 0
        closed_count = 0
        daily_pnl = 0.0

        for ts_code, position in list(open_positions.items()):
            if str(position["exit_trade_date"]) != str(date):
                continue
            pnl = float(position["position_notional"]) * float(position["realized_return"])
            cash += float(position["position_notional"]) + pnl
            daily_pnl += pnl
            closed_count += 1
            trade_records[int(position["trade_idx"])]["pnl"] = pnl
            open_positions.pop(ts_code, None)

        entries = by_entry.get(date)
        if entries is not None:
            for _idx, row in entries.iterrows():
                ts_code = str(row.get("ts_code") or "")
                base_record = _lhb_cash_account_trade_record(row)
                if ts_code in open_positions:
                    account_rows.append({
                        **base_record,
                        "account_trade_status": "duplicate_position_skipped",
                        "skip_reason": "duplicate_open_position",
                    })
                    continue
                if len(open_positions) >= int(max_positions):
                    account_rows.append({
                        **base_record,
                        "account_trade_status": "max_positions_skipped",
                        "skip_reason": "max_positions_reached",
                    })
                    continue
                equity_before_entry = cash + sum(float(pos["position_notional"]) for pos in open_positions.values())
                notional = min(equity_before_entry * float(position_pct), cash)
                if notional <= 0.0:
                    account_rows.append({
                        **base_record,
                        "account_trade_status": "cash_skipped",
                        "skip_reason": "insufficient_cash",
                    })
                    continue
                cash -= notional
                trade_idx = len(account_rows)
                record = {
                    **base_record,
                    "account_trade_status": "filled",
                    "position_notional": notional,
                    "pnl": pd.NA,
                    "skip_reason": "",
                }
                account_rows.append(record)
                trade_records[trade_idx] = record
                open_positions[ts_code] = {
                    "trade_idx": trade_idx,
                    "exit_trade_date": row.get("exit_trade_date"),
                    "realized_return": float(row.get("realized_return")),
                    "position_notional": notional,
                }
                opened_count += 1

        invested = sum(float(pos["position_notional"]) for pos in open_positions.values())
        equity = cash + invested
        running_max = max(running_max, equity)
        curve_rows.append(
            {
                "trade_date": date,
                "cash": cash,
                "invested_notional": invested,
                "equity": equity,
                "drawdown": equity / running_max - 1.0 if running_max else 0.0,
                "open_position_count": len(open_positions),
                "opened_count": opened_count,
                "closed_count": closed_count,
                "daily_realized_pnl": daily_pnl,
            }
        )

    return pd.DataFrame(account_rows).reindex(columns=trade_columns), pd.DataFrame(curve_rows).reindex(columns=curve_columns)


def _lhb_cash_account_trade_record(row: pd.Series) -> dict[str, Any]:
    return {
        "account_trade_status": "",
        "trade_date": row.get("trade_date", ""),
        "ts_code": row.get("ts_code", ""),
        "top_n": row.get("top_n", pd.NA),
        "phase12a_rule_layer": row.get("phase12a_rule_layer", ""),
        "entry_trade_date": row.get("entry_trade_date", pd.NA),
        "entry_price": row.get("entry_price", pd.NA),
        "exit_trade_date": row.get("exit_trade_date", pd.NA),
        "exit_price": row.get("exit_price", pd.NA),
        "realized_return": row.get("realized_return", pd.NA),
        "position_notional": pd.NA,
        "pnl": pd.NA,
        "skip_reason": "",
    }


def _fetch_frame(sql: str, params: list[object], service: str = SETTINGS.research_service) -> pd.DataFrame:
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def build_manual_v1_scores_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    strategy_id = "manual_v1_topn_rotation"
    if frame is None or frame.empty:
        return normalize_strategy_scores(frame, strategy_id=strategy_id)

    manual = _deduplicate_manual_scores(frame, strategy_id=strategy_id)
    normalized = normalize_strategy_scores(
        manual.copy(),
        strategy_id=strategy_id,
    )
    if "rank" not in manual.columns:
        return normalized

    manual_ranks = manual[["trade_date", "asset_id", "rank", "score_total"]].copy()
    manual_ranks["score_total"] = pd.to_numeric(manual_ranks["score_total"], errors="coerce")
    manual_ranks["rank"] = pd.to_numeric(manual_ranks["rank"], errors="coerce")
    manual_ranks = manual_ranks.dropna(subset=["trade_date", "asset_id", "rank", "score_total"])
    manual_ranks["trade_date"] = pd.to_datetime(manual_ranks["trade_date"]).dt.strftime("%Y-%m-%d")
    manual_ranks["asset_id"] = manual_ranks["asset_id"].astype(str)

    normalized = normalized.drop(columns=["rank"]).merge(
        manual_ranks[["trade_date", "asset_id", "rank"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    normalized = normalized.sort_values(
        ["trade_date", "rank", "asset_id"],
        ascending=[True, True, True],
    ).reset_index(drop=True)
    return normalized[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_components",
            "strategy_id",
            "eligibility",
            "eligibility_reason",
            "exposure_scale",
        ]
    ]


def _deduplicate_lhb_frame(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.copy()
    group_keys = ["trade_date", "asset_id"]
    grouped["asset_id"] = grouped["asset_id"].map(normalize_market_asset_id)
    numeric_columns = [
        "lhb_net_buy_ratio",
        "lhb_net_buy_amount",
        "institution_net_buy",
        "repeat_on_list_count_3d",
        "lhb_one_day_pump_risk",
    ]
    bool_columns = ["on_lhb", "lhb_after_reversal"]
    aggregations: dict[str, str] = {}

    for column in numeric_columns:
        if column in grouped.columns:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
            aggregations[column] = "max"
    for column in bool_columns:
        if column in grouped.columns:
            grouped[column] = grouped[column].fillna(False).astype(bool)
            aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def _deduplicate_technical_frame(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.copy()
    group_keys = ["trade_date", "asset_id"]
    grouped["asset_id"] = grouped["asset_id"].map(normalize_market_asset_id)
    aggregations: dict[str, str] = {}
    for column in ["amount_vs_20d", "high_to_close_drawdown"]:
        if column in grouped.columns:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
            aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def build_lhb_shortline_scores_from_frames(lhb: pd.DataFrame, technical: pd.DataFrame | None = None) -> pd.DataFrame:
    if lhb is None or lhb.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id="lhb_shortline")
    frame = _deduplicate_lhb_frame(lhb)
    if technical is not None and not technical.empty:
        technical = _deduplicate_technical_frame(
            technical[["trade_date", "asset_id", "amount_vs_20d", "high_to_close_drawdown"]]
        )
        frame = frame.merge(
            technical,
            on=["trade_date", "asset_id"],
            how="left",
        )
    net_ratio = _num(frame.get("lhb_net_buy_ratio", pd.Series(index=frame.index)))
    net_amount = _num(frame.get("lhb_net_buy_amount", pd.Series(index=frame.index))) / 100_000_000.0
    inst_buy = _num(frame.get("institution_net_buy", pd.Series(index=frame.index))) / 100_000_000.0
    repeat = _num(frame.get("repeat_on_list_count_3d", pd.Series(index=frame.index)))
    reversal = _bool(frame.get("lhb_after_reversal", pd.Series(index=frame.index))).astype(float)
    amount_confirmation = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    pump_risk = _num(frame.get("lhb_one_day_pump_risk", pd.Series(index=frame.index)))
    high_drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index)))

    frame["score_total"] = (
        50.0
        + net_ratio.clip(-1, 1) * 35.0
        + net_amount.clip(-1, 3) * 8.0
        + inst_buy.clip(-1, 2) * 6.0
        + repeat.clip(0, 5) * 2.5
        + reversal * 6.0
        + amount_confirmation * 2.0
        - pump_risk.clip(0, 1) * 25.0
        - high_drawdown.clip(0, 1) * 40.0
    )
    if "top5_eligible" in frame.columns:
        eligible = _bool(frame["top5_eligible"])
    else:
        eligible = _bool(frame.get("on_lhb", pd.Series(index=frame.index)))
    frame["eligibility"] = eligible.map(lambda value: bool(value)).astype(object)
    if "eligibility_status" in frame.columns:
        frame["eligibility_reason"] = frame["eligibility_status"].fillna("eligibility_unknown").astype(str)
    else:
        frame["eligibility_reason"] = eligible.map({True: "lhb_support", False: "missing_lhb"})
    frame["score_components"] = [
        {
            "lhb_net_buy_ratio": float(net_ratio.iloc[index]),
            "lhb_net_buy_amount": float(net_amount.iloc[index]),
            "institution_net_buy": float(inst_buy.iloc[index]),
            "lhb_one_day_pump_risk": float(pump_risk.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="lhb_shortline")


def _factor_pivot(factors: pd.DataFrame | None) -> pd.DataFrame:
    if factors is None or factors.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id"])
    pivot = factors.pivot_table(
        index=["trade_date", "asset_id"],
        columns="factor_name",
        values="factor_value",
        aggfunc="max",
    ).reset_index()
    pivot.columns = [str(column) for column in pivot.columns]
    return pivot


def _deduplicate_manual_scores(frame: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id=strategy_id)
    required = {"trade_date", "asset_id", "score_total"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{strategy_id} scores missing columns: {', '.join(sorted(missing))}")

    grouped = frame.copy()
    grouped["score_total"] = pd.to_numeric(grouped["score_total"], errors="coerce")
    aggregations = {"score_total": "max"}
    if "rank" in grouped.columns:
        grouped["rank"] = pd.to_numeric(grouped["rank"], errors="coerce")
        aggregations["rank"] = "min"
    grouped = grouped.dropna(subset=["trade_date", "asset_id", "score_total"])
    if grouped.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id=strategy_id)
    return grouped.groupby(["trade_date", "asset_id"], as_index=False, sort=False).agg(aggregations)


def _deduplicate_feature_frame(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return frame
    group_keys = ["trade_date", "asset_id"]
    grouped = frame.copy()
    aggregations: dict[str, str] = {}
    for column in grouped.columns:
        if column in group_keys:
            continue
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
        aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def _merge_manual_technical_factors(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    strategy_id: str,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    manual = _deduplicate_manual_scores(manual, strategy_id)
    base = manual[["trade_date", "asset_id", "score_total"]].copy()
    base = base.rename(columns={"score_total": "manual_score"})
    technical = _deduplicate_feature_frame(technical)
    if technical is not None and not technical.empty:
        base = base.merge(technical, on=["trade_date", "asset_id"], how="left")
    factor_wide = _factor_pivot(factors)
    if not factor_wide.empty:
        base = base.merge(factor_wide, on=["trade_date", "asset_id"], how="left")
    return base


def build_mid_trend_scores_from_frames(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="mid_trend", factors=factors)
    trend = _num(frame.get("trend_r2_20", pd.Series(index=frame.index))).clip(0, 1)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    frame["score_total"] = (
        manual_score * 0.35
        + trend * 35.0
        + ret_20d * 80.0
        + amount * 3.0
        - drawdown * 45.0
    )
    frame["eligibility"] = (trend >= 0.30) | (ret_20d > 0)
    frame["eligibility_reason"] = frame["eligibility"].map({True: "trend_candidate", False: "weak_trend"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "trend_r2_20": float(trend.iloc[index]),
            "ret_20d": float(ret_20d.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="mid_trend")


def build_tech_bottleneck_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="tech_bottleneck")
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 4)
    close_position = _num(frame.get("close_position_in_day", pd.Series(index=frame.index)), 0.5).clip(0, 1)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    frame["score_total"] = (
        manual_score * 0.20
        + ret_20d * 95.0
        + amount * 8.0
        + close_position * 18.0
        - drawdown * 35.0
    )
    frame["eligibility"] = amount >= 0.5
    frame["eligibility_reason"] = frame["eligibility"].map({True: "technical_confirmation", False: "weak_volume_price"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "ret_20d": float(ret_20d.iloc[index]),
            "amount_vs_20d": float(amount.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="tech_bottleneck")


def build_position_control_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="position_control")
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 5)
    risk_penalty = drawdown * 120.0 + (amount - 2.5).clip(lower=0) * 8.0
    frame["score_total"] = manual_score - risk_penalty
    # Current TopN execution is equal-weighted, so score_total carries the risk-control effect.
    # exposure_scale is retained as metadata for later engine-level position scaling.
    exposure_scale = (1.0 - drawdown * 2.0).clip(lower=0.25, upper=1.0)
    frame["exposure_scale"] = exposure_scale.mask(drawdown <= 0.02, 1.0)
    frame["eligibility"] = frame["exposure_scale"] >= 0.25
    frame["eligibility_reason"] = frame["eligibility"].map({True: "risk_scaled", False: "risk_excluded"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "risk_penalty": float(risk_penalty.iloc[index]),
            "exposure_scale": float(frame["exposure_scale"].iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="position_control")


def _load_manual_scores(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, rank, score_total
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, rank, asset_id
        """,
        [params.score_version, params.start_date, params.end_date],
    )


def _load_technical_features(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT
            trade_date,
            asset_id,
            ret_20d,
            amount_vs_20d,
            close_position_in_day,
            high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """,
        [params.adjust_type, params.start_date, params.end_date],
    )


def _load_factor_values(params: StrategyBacktestParams, factor_names: list[str]) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, factor_name, factor_value
        FROM factor.factor_daily
        WHERE trade_date BETWEEN %s AND %s
          AND factor_name = ANY(%s)
        """,
        [params.start_date, params.end_date, factor_names],
    )


def _filter_eligible_scores(scores: pd.DataFrame) -> pd.DataFrame:
    filtered = scores[scores["eligibility"].map(bool)].reset_index(drop=True).copy()
    filtered = filtered.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    filtered["rank"] = filtered.groupby("trade_date").cumcount() + 1
    filtered["eligibility"] = filtered["eligibility"].map(lambda value: bool(value)).astype(object)
    return filtered


class ManualV1TopNAdapter:
    strategy_id = "manual_v1_topn_rotation"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return build_manual_v1_scores_from_frame(_load_manual_scores(params))


class LHBShortlineAdapter:
    strategy_id = "lhb_shortline"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        lhb_sql = """
        SELECT
            l.trade_date,
            COALESCE(a.asset_id, l.ts_code) AS asset_id,
            l.on_lhb,
            l.lhb_net_buy_ratio,
            l.lhb_net_buy_amount,
            l.institution_net_buy,
            l.repeat_on_list_count_3d,
            l.lhb_after_reversal,
            l.lhb_one_day_pump_risk
        FROM factor.lhb_event_features_daily l
        LEFT JOIN core.asset_master a ON a.ts_code = l.ts_code
        WHERE l.trade_date BETWEEN %s AND %s
        """
        technical_sql = """
        SELECT trade_date, asset_id, amount_vs_20d, high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """
        lhb = _fetch_frame(lhb_sql, [params.start_date, params.end_date])
        technical = _fetch_frame(technical_sql, [params.adjust_type, params.start_date, params.end_date])
        scores = build_lhb_shortline_scores_from_frames(lhb, technical)
        return _filter_eligible_scores(scores)


class MidTrendAdapter:
    strategy_id = "mid_trend"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_mid_trend_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
            _load_factor_values(params, ["trend_r2_20", "ma20_slope", "ma60_slope"]),
        )
        return _filter_eligible_scores(scores)


class TechBottleneckAdapter:
    strategy_id = "tech_bottleneck"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_tech_bottleneck_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )
        return _filter_eligible_scores(scores)


class PositionControlAdapter:
    strategy_id = "position_control"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_position_control_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )
        return _filter_eligible_scores(scores)


LHB_SHORTLINE_COMBO_REPLAY = LHBPhase16CReplayAdapter(
    ArtifactReplayConfig(
        strategy_id="lhb_shortline",
        strategy_name="LHB Shortline Combo",
        combo_scheme="lhb_shortline_combo_v1",
        evidence_source=(
            "Phase14C lifecycle + strict limit-lock + Phase15 cash account + "
            "Phase16C limit-break-failed delayed exit"
        ),
        summary_path=(
            "outputs/research/lhb_phase16c_limit_break_failed_rule_scan_20250101_20260608/"
            "lhb_phase16c_limit_break_failed_rule_scan_summary_v1.csv"
        ),
        summary_filters={"rule_profile": "delay_all_limit_break_failed_to_5d"},
        summary_aliases={"final_equity": "account_final_equity", "max_drawdown": "account_max_drawdown"},
    ),
    lifecycle_trades_path=(
        "outputs/research/lhb_phase14c_top10_20250101_20260608_limitlock/"
        "lhb_phase14c_lifecycle_trades_v1.csv"
    ),
    real_entry_trades_path=(
        "outputs/research/lhb_phase14c_top10_20250101_20260608_limitlock/"
        "lhb_phase12a_real_entry_trades_v1.csv"
    ),
    replacement_return_column="exit_5d_return",
    adjust_reason="limit_break_failed_delay_to_5d",
)

MID_TREND_COMBO_REPLAY = ArtifactReplayAdapter(
    ArtifactReplayConfig(
        strategy_id="mid_trend",
        strategy_name="Mid Trend Combo",
        combo_scheme="mid_trend_combo_v1",
        evidence_source=(
            "report_mild_bonus + Top5 weekly max2 selective trend holding protection + "
            "C2 stock protection review"
        ),
        summary_path=(
            "outputs/research/mid_trend_research_overlay_after_2024q4_lookback/report_mild_bonus/"
            "mid_trend_shadow_weekly_control_summary.csv"
        ),
        summary_filters={"variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1"},
        equity_path=(
            "outputs/research/mid_trend_research_overlay_after_2024q4_lookback/report_mild_bonus/"
            "mid_trend_shadow_weekly_control_equity.csv"
        ),
        equity_filters={"variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1"},
        positions_path=(
            "outputs/research/mid_trend_research_overlay_after_2024q4_lookback/report_mild_bonus/"
            "mid_trend_shadow_weekly_control_positions.csv"
        ),
        positions_filters={"variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1"},
        trades_path=(
            "outputs/research/mid_trend_research_overlay_after_2024q4_lookback/report_mild_bonus/"
            "mid_trend_shadow_weekly_control_trades.csv"
        ),
        trades_filters={"variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1"},
    )
)

TECH_BOTTLENECK_COMBO_REPLAY = ArtifactReplayAdapter(
    ArtifactReplayConfig(
        strategy_id="tech_bottleneck",
        strategy_name="Tech Bottleneck Combo",
        combo_scheme="tech_bottleneck_combo_v1",
        evidence_source="tech_hard_filter + top5_adaptive_daily_check_max2_v1",
        summary_path=(
            "outputs/research/tech_bottleneck_mid_trend_overlay_20250101_20260605/"
            "overlay_weekly_control_all_variant_summary.csv"
        ),
        summary_filters={
            "overlay_name": "tech_hard_filter",
            "variant_name": "top5_adaptive_daily_check_max2_v1",
        },
        equity_path=(
            "outputs/research/tech_bottleneck_mid_trend_overlay_20250101_20260605/"
            "tech_hard_filter/mid_trend_shadow_weekly_control_equity.csv"
        ),
        equity_filters={"variant_name": "top5_adaptive_daily_check_max2_v1"},
        positions_path=(
            "outputs/research/tech_bottleneck_mid_trend_overlay_20250101_20260605/"
            "tech_hard_filter/mid_trend_shadow_weekly_control_positions.csv"
        ),
        positions_filters={"variant_name": "top5_adaptive_daily_check_max2_v1"},
        trades_path=(
            "outputs/research/tech_bottleneck_mid_trend_overlay_20250101_20260605/"
            "tech_hard_filter/mid_trend_shadow_weekly_control_trades.csv"
        ),
        trades_filters={"variant_name": "top5_adaptive_daily_check_max2_v1"},
    )
)


STRATEGY_BACKTEST_REGISTRY: dict[str, StrategyBacktestAdapter] = {
    "manual_v1_topn_rotation": ManualV1TopNAdapter(),
    "lhb_shortline": FreshReplayBacktestAdapter(LHBShortlineAdapter(), LHB_SHORTLINE_COMBO_REPLAY),
    "mid_trend": FreshReplayBacktestAdapter(MidTrendAdapter(), MID_TREND_COMBO_REPLAY),
    "tech_bottleneck": FreshReplayBacktestAdapter(TechBottleneckAdapter(), TECH_BOTTLENECK_COMBO_REPLAY),
    "position_control": PositionControlAdapter(),
}
