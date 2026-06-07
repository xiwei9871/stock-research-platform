from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.dragon_case_library import (
    build_failure_event_rule_v21_curated_view,
    build_failure_event_rule_v21_transition_matrix,
)


TOP_LIST_COLUMNS = [
    "trade_date",
    "ts_code",
    "name",
    "close",
    "pct_change",
    "turnover_rate",
    "amount",
    "l_sell",
    "l_buy",
    "l_amount",
    "net_amount",
    "net_rate",
    "amount_rate",
    "float_values",
    "reason",
    "source",
]

TOP_INST_COLUMNS = [
    "trade_date",
    "ts_code",
    "exalter",
    "buy",
    "buy_rate",
    "sell",
    "sell_rate",
    "net_buy",
    "reason",
    "source",
]

LHB_ALIGNMENT_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "case_type",
    "event_type",
    "event_date",
    "lhb_on_event_date",
    "lhb_before_event_3d",
    "lhb_after_event_3d",
    "lhb_reason",
    "lhb_net_buy_amount",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "repeat_on_list_count_5d",
    "lhb_one_day_pump_risk",
    "lhb_alignment_status",
]

LHB_EVENT_FEATURE_COLUMNS = [
    "trade_date",
    "ts_code",
    "on_lhb",
    "lhb_reason",
    "lhb_net_buy_amount",
    "lhb_net_buy_ratio",
    "lhb_buy_amount",
    "lhb_sell_amount",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "repeat_on_list_count_5d",
    "lhb_after_limit_up",
    "lhb_after_break_limit",
    "lhb_after_reversal",
    "lhb_one_day_pump_risk",
    "source",
]

FUTURE_DIAGNOSTIC_COLUMNS = [
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]


def normalize_top_list_rows(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_LIST_COLUMNS)
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    data["ts_code"] = data["ts_code"].fillna("").astype(str).str.upper()
    data["source"] = source
    return data.reindex(columns=TOP_LIST_COLUMNS)


def normalize_top_inst_rows(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_INST_COLUMNS)
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    data["ts_code"] = data["ts_code"].fillna("").astype(str).str.upper()
    data["source"] = source
    return data.reindex(columns=TOP_INST_COLUMNS)


def normalize_top_list_rows_akshare(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_LIST_COLUMNS)
    data = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame["上榜日"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "ts_code": frame["代码"].map(_code_to_ts_code),
            "name": frame.get("名称"),
            "close": frame.get("收盘价"),
            "pct_change": frame.get("涨跌幅"),
            "turnover_rate": frame.get("换手率"),
            "amount": frame.get("市场总成交额"),
            "l_sell": frame.get("龙虎榜卖出额"),
            "l_buy": frame.get("龙虎榜买入额"),
            "l_amount": frame.get("龙虎榜成交额"),
            "net_amount": frame.get("龙虎榜净买额"),
            "net_rate": frame.get("净买额占总成交比"),
            "amount_rate": frame.get("成交额占总成交比"),
            "float_values": frame.get("流通市值"),
            "reason": frame.get("上榜原因"),
            "source": "akshare",
        }
    )
    return data.reindex(columns=TOP_LIST_COLUMNS)


def normalize_top_inst_rows_akshare(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_INST_COLUMNS)
    data = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame["上榜日期"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "ts_code": frame["代码"].map(_code_to_ts_code),
            "exalter": "机构汇总",
            "buy": frame.get("机构买入总额"),
            "buy_rate": None,
            "sell": frame.get("机构卖出总额"),
            "sell_rate": None,
            "net_buy": frame.get("机构买入净额"),
            "reason": frame.get("上榜原因"),
            "source": "akshare",
        }
    )
    return data.reindex(columns=TOP_INST_COLUMNS)


def build_tushare_client(token: str | None = None):
    actual_token = token or os.getenv("TUSHARE_TOKEN", "").strip()
    if not actual_token:
        raise RuntimeError("TUSHARE_TOKEN is required for LHB sample import")
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("tushare package is required for LHB sample import") from exc
    return ts.pro_api(actual_token)


def build_akshare_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("akshare package is required for LHB sample import") from exc
    return ak


def fetch_lhb_sample(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None = None,
    client: Any = None,
    provider: str = "tushare",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    provider_name = str(provider or "tushare").strip().lower()
    if provider_name == "akshare":
        ak = client or build_akshare_client()
        top_list = normalize_top_list_rows_akshare(ak.stock_lhb_detail_em(start_date=_compact_date(start_date), end_date=_compact_date(end_date)))
        top_inst = normalize_top_inst_rows_akshare(ak.stock_lhb_jgmmtj_em(start_date=_compact_date(start_date), end_date=_compact_date(end_date)))
        if ts_codes:
            codes = {code.strip().upper() for code in ts_codes if code.strip()}
            top_list = top_list[top_list["ts_code"].isin(codes)].reset_index(drop=True)
            top_inst = top_inst[top_inst["ts_code"].isin(codes)].reset_index(drop=True)
        return top_list, top_inst

    pro = client or build_tushare_client()
    top_list_frames: list[pd.DataFrame] = []
    top_inst_frames: list[pd.DataFrame] = []
    codes = [code.strip().upper() for code in (ts_codes or []) if code.strip()]
    if codes:
        for code in codes:
            top_list_frames.append(pd.DataFrame(pro.top_list(ts_code=code, start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
            top_inst_frames.append(pd.DataFrame(pro.top_inst(ts_code=code, start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
    else:
        top_list_frames.append(pd.DataFrame(pro.top_list(start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
        top_inst_frames.append(pd.DataFrame(pro.top_inst(start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
    top_list = pd.concat(top_list_frames, ignore_index=True) if top_list_frames else pd.DataFrame()
    top_inst = pd.concat(top_inst_frames, ignore_index=True) if top_inst_frames else pd.DataFrame()
    return normalize_top_list_rows(top_list, source="tushare"), normalize_top_inst_rows(top_inst, source="tushare")


def upsert_lhb_sample(
    *,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> None:
    top_list_sql = """
        INSERT INTO market.lhb_top_list_daily (
            trade_date, ts_code, name, close, pct_change, turnover_rate, amount,
            l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values,
            reason, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, reason, source) DO UPDATE SET
            name = EXCLUDED.name,
            close = EXCLUDED.close,
            pct_change = EXCLUDED.pct_change,
            turnover_rate = EXCLUDED.turnover_rate,
            amount = EXCLUDED.amount,
            l_sell = EXCLUDED.l_sell,
            l_buy = EXCLUDED.l_buy,
            l_amount = EXCLUDED.l_amount,
            net_amount = EXCLUDED.net_amount,
            net_rate = EXCLUDED.net_rate,
            amount_rate = EXCLUDED.amount_rate,
            float_values = EXCLUDED.float_values,
            updated_at = now()
    """
    top_inst_sql = """
        INSERT INTO market.lhb_top_inst_daily (
            trade_date, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, reason, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, exalter, source) DO UPDATE SET
            buy = EXCLUDED.buy,
            buy_rate = EXCLUDED.buy_rate,
            sell = EXCLUDED.sell,
            sell_rate = EXCLUDED.sell_rate,
            net_buy = EXCLUDED.net_buy,
            reason = EXCLUDED.reason,
            updated_at = now()
    """
    with connect(service) as conn:
        if not top_list.empty:
            execute_many(conn, top_list_sql, _top_list_rows(top_list))
        if not top_inst.empty:
            execute_many(conn, top_inst_sql, _top_inst_rows(top_inst))


def run_lhb_sample_import(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None,
    output_dir: str | Path,
    client: Any = None,
    provider: str = "tushare",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    top_list, top_inst = fetch_lhb_sample(
        start_date=start_date,
        end_date=end_date,
        ts_codes=ts_codes,
        client=client,
        provider=provider,
    )
    upsert_lhb_sample(top_list=top_list, top_inst=top_inst, service=service)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    top_list_path = out / "lhb_top_list_sample.csv"
    top_inst_path = out / "lhb_top_inst_sample.csv"
    top_list.to_csv(top_list_path, index=False)
    top_inst.to_csv(top_inst_path, index=False)
    return {
        "top_list": top_list,
        "top_inst": top_inst,
        "paths": {"top_list": str(top_list_path), "top_inst": str(top_inst_path)},
    }


def load_lhb_from_db(
    *,
    ts_codes: list[str] | None,
    start_date: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    code_filter = ""
    params = [start_date, end_date]
    if ts_codes:
        placeholders = ",".join(["%s"] * len(ts_codes))
        code_filter = f"AND ts_code IN ({placeholders})"
        params.extend(ts_codes)
    top_list_sql = f"""
        SELECT trade_date::text, ts_code, name, close, pct_change, turnover_rate, amount,
               l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values, reason, source
        FROM market.lhb_top_list_daily
        WHERE trade_date BETWEEN %s::date AND %s::date
          {code_filter}
        ORDER BY trade_date, ts_code
    """
    top_inst_sql = f"""
        SELECT trade_date::text, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, reason, source
        FROM market.lhb_top_inst_daily
        WHERE trade_date BETWEEN %s::date AND %s::date
          {code_filter}
        ORDER BY trade_date, ts_code
    """
    with connect(service) as conn:
        top_list = pd.DataFrame(fetch_all(conn, top_list_sql, params))
        top_inst = pd.DataFrame(fetch_all(conn, top_inst_sql, params))
    return top_list.reindex(columns=TOP_LIST_COLUMNS), top_inst.reindex(columns=TOP_INST_COLUMNS)


def build_lhb_event_features_daily(
    *,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
) -> pd.DataFrame:
    list_frame = top_list.copy().reindex(columns=TOP_LIST_COLUMNS)
    inst_frame = top_inst.copy().reindex(columns=TOP_INST_COLUMNS)
    list_frame = _normalize_date_code_frame(list_frame, "trade_date", "ts_code")
    inst_frame = _normalize_date_code_frame(inst_frame, "trade_date", "ts_code")

    key_columns = ["trade_date", "ts_code", "source"]
    keys: list[tuple[str, str, str]] = []
    if not list_frame.empty:
        keys.extend(list_frame[key_columns].drop_duplicates().itertuples(index=False, name=None))
    if not inst_frame.empty:
        keys.extend(inst_frame[key_columns].drop_duplicates().itertuples(index=False, name=None))
    unique_keys = sorted(set(keys))
    if not unique_keys:
        return pd.DataFrame(columns=LHB_EVENT_FEATURE_COLUMNS)

    rows: list[dict[str, Any]] = []
    for trade_date, ts_code, source in unique_keys:
        day_list = list_frame[
            (list_frame["trade_date"] == trade_date)
            & (list_frame["ts_code"] == ts_code)
            & (list_frame["source"] == source)
        ]
        day_inst = inst_frame[
            (inst_frame["trade_date"] == trade_date)
            & (inst_frame["ts_code"] == ts_code)
            & (inst_frame["source"] == source)
        ]
        amount = _numeric_scalar(day_list["amount"], aggregator="max")
        l_amount = _numeric_scalar(day_list["l_amount"], aggregator="max")
        lhb_net_buy_amount = _numeric_scalar(day_list["net_amount"], aggregator="max")
        lhb_buy_amount = _numeric_scalar(day_list["l_buy"], aggregator="max")
        lhb_sell_amount = _numeric_scalar(day_list["l_sell"], aggregator="max")
        pct_change = _numeric_scalar(day_list["pct_change"], aggregator="max")
        turnover_rate = _numeric_scalar(day_list["turnover_rate"], aggregator="max")
        net_rate = _numeric_scalar(day_list["net_rate"], aggregator="max")
        amount_rate = _numeric_scalar(day_list["amount_rate"], aggregator="max")
        institution_net_buy = _numeric_scalar(day_inst["net_buy"], aggregator="sum")
        repeat_3d = _repeat_on_list_count(list_frame, ts_code=ts_code, source=source, trade_date=trade_date, lookback_days=3)
        repeat_5d = _repeat_on_list_count(list_frame, ts_code=ts_code, source=source, trade_date=trade_date, lookback_days=5)
        lhb_net_buy_ratio = _coerce_ratio(net_rate)
        if lhb_net_buy_ratio is None:
            lhb_net_buy_ratio = _coerce_ratio((lhb_net_buy_amount / amount) if amount not in (None, 0) and lhb_net_buy_amount is not None else None, clamp=False)
        top_seat_concentration = _coerce_ratio(amount_rate)
        if top_seat_concentration is None:
            top_seat_concentration = _coerce_ratio((l_amount / amount) if amount not in (None, 0) and l_amount is not None else None)
        lhb_after_limit_up = bool(pct_change is not None and pct_change >= 9.5)
        lhb_after_break_limit = bool(
            not lhb_after_limit_up
            and repeat_3d >= 1
            and pct_change is not None
            and pct_change >= -3.0
        )
        lhb_after_reversal = bool(
            not lhb_after_limit_up
            and repeat_5d >= 1
            and pct_change is not None
            and pct_change >= 5.0
        )
        risk_score = 0.0
        if pct_change is not None and pct_change >= 9.5:
            risk_score += 0.30
        if amount_rate is not None and amount_rate >= 0.20:
            risk_score += 0.20
        if turnover_rate is not None and turnover_rate >= 20.0:
            risk_score += 0.20
        if lhb_net_buy_amount is not None and lhb_net_buy_amount < 0:
            risk_score += 0.20
        if repeat_3d <= 1:
            risk_score += 0.10
        rows.append(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "on_lhb": True,
                "lhb_reason": _join_unique(day_list["reason"]) or _join_unique(day_inst["reason"]),
                "lhb_net_buy_amount": lhb_net_buy_amount,
                "lhb_net_buy_ratio": lhb_net_buy_ratio,
                "lhb_buy_amount": lhb_buy_amount,
                "lhb_sell_amount": lhb_sell_amount,
                "institution_net_buy": institution_net_buy,
                "top_seat_concentration": top_seat_concentration,
                "repeat_on_list_count_3d": repeat_3d,
                "repeat_on_list_count_5d": repeat_5d,
                "lhb_after_limit_up": lhb_after_limit_up,
                "lhb_after_break_limit": lhb_after_break_limit,
                "lhb_after_reversal": lhb_after_reversal,
                "lhb_one_day_pump_risk": min(risk_score, 1.0),
                "source": source,
            }
        )
    features = pd.DataFrame(rows).reindex(columns=LHB_EVENT_FEATURE_COLUMNS)
    return features.sort_values(["trade_date", "ts_code", "source"]).reset_index(drop=True)


def upsert_lhb_event_features_daily(
    *,
    features: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> None:
    if features.empty:
        return
    sql = """
        INSERT INTO factor.lhb_event_features_daily (
            trade_date, ts_code, on_lhb, lhb_reason, lhb_net_buy_amount, lhb_net_buy_ratio,
            lhb_buy_amount, lhb_sell_amount, institution_net_buy, top_seat_concentration,
            repeat_on_list_count_3d, repeat_on_list_count_5d, lhb_after_limit_up,
            lhb_after_break_limit, lhb_after_reversal, lhb_one_day_pump_risk, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, source) DO UPDATE SET
            on_lhb = EXCLUDED.on_lhb,
            lhb_reason = EXCLUDED.lhb_reason,
            lhb_net_buy_amount = EXCLUDED.lhb_net_buy_amount,
            lhb_net_buy_ratio = EXCLUDED.lhb_net_buy_ratio,
            lhb_buy_amount = EXCLUDED.lhb_buy_amount,
            lhb_sell_amount = EXCLUDED.lhb_sell_amount,
            institution_net_buy = EXCLUDED.institution_net_buy,
            top_seat_concentration = EXCLUDED.top_seat_concentration,
            repeat_on_list_count_3d = EXCLUDED.repeat_on_list_count_3d,
            repeat_on_list_count_5d = EXCLUDED.repeat_on_list_count_5d,
            lhb_after_limit_up = EXCLUDED.lhb_after_limit_up,
            lhb_after_break_limit = EXCLUDED.lhb_after_break_limit,
            lhb_after_reversal = EXCLUDED.lhb_after_reversal,
            lhb_one_day_pump_risk = EXCLUDED.lhb_one_day_pump_risk,
            updated_at = now()
    """
    with connect(service) as conn:
        execute_many(conn, sql, _event_feature_rows(features))


def run_lhb_event_features_build(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    top_list, top_inst = load_lhb_from_db(
        ts_codes=ts_codes or [],
        start_date=start_date,
        end_date=end_date,
        service=service,
    )
    features = build_lhb_event_features_daily(top_list=top_list, top_inst=top_inst)
    upsert_lhb_event_features_daily(features=features, service=service)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lhb_event_features_daily_sample.csv"
    features.to_csv(path, index=False)
    return {"lhb_event_features": features, "paths": {"lhb_event_features": str(path)}}


def build_dragon_case_lhb_alignment_audit(
    curated: pd.DataFrame,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    features = build_lhb_event_features_daily(top_list=top_list, top_inst=top_inst)
    features = _normalize_date_code_frame(features, "trade_date", "ts_code")
    for record in curated.fillna("").to_dict("records"):
        ts_code = str(record.get("ts_code") or "").upper()
        case_type = str(record.get("case_type") or record.get("verified_case_type") or "")
        for event_type, field in [
            ("first_limit_up", "first_limit_up_date"),
            ("break_limit", "break_limit_date"),
            ("reversal", "reversal_date"),
            ("second_wave_start", "second_wave_start_date"),
            ("peak", "peak_date"),
            ("a_kill_start", "a_kill_start_date"),
        ]:
            event_date = str(record.get(field) or "").strip()
            if not event_date:
                continue
            rows_for_code = features[features["ts_code"] == ts_code] if not features.empty else pd.DataFrame(columns=LHB_EVENT_FEATURE_COLUMNS)
            on_date = rows_for_code[rows_for_code["trade_date"] == event_date]
            before = rows_for_code[(rows_for_code["trade_date"] < event_date) & (rows_for_code["trade_date"] >= _shift_date(event_date, -3))]
            after = rows_for_code[(rows_for_code["trade_date"] > event_date) & (rows_for_code["trade_date"] <= _shift_date(event_date, 3))]
            rows.append(
                {
                    "case_id": record.get("case_id"),
                    "ts_code": ts_code,
                    "stock_name": record.get("stock_name"),
                    "case_type": case_type,
                    "event_type": event_type,
                    "event_date": event_date,
                    "lhb_on_event_date": not on_date.empty,
                    "lhb_before_event_3d": not before.empty,
                    "lhb_after_event_3d": not after.empty,
                    "lhb_reason": str(on_date.iloc[0]["lhb_reason"]) if not on_date.empty else "",
                    "lhb_net_buy_amount": _float_or_none(on_date.iloc[0]["lhb_net_buy_amount"]) if not on_date.empty else None,
                    "institution_net_buy": _float_or_none(on_date.iloc[0]["institution_net_buy"]) if not on_date.empty else None,
                    "top_seat_concentration": _float_or_none(on_date.iloc[0]["top_seat_concentration"]) if not on_date.empty else None,
                    "repeat_on_list_count_3d": int(on_date.iloc[0]["repeat_on_list_count_3d"]) if not on_date.empty and pd.notna(on_date.iloc[0]["repeat_on_list_count_3d"]) else 0,
                    "repeat_on_list_count_5d": int(on_date.iloc[0]["repeat_on_list_count_5d"]) if not on_date.empty and pd.notna(on_date.iloc[0]["repeat_on_list_count_5d"]) else 0,
                    "lhb_one_day_pump_risk": _float_or_none(on_date.iloc[0]["lhb_one_day_pump_risk"]) if not on_date.empty else None,
                    "lhb_alignment_status": "matched" if (not on_date.empty or not before.empty or not after.empty) else "missing",
                }
            )
    audit = pd.DataFrame(rows).reindex(columns=LHB_ALIGNMENT_COLUMNS)
    result = {"alignment_audit": audit}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "dragon_case_lhb_alignment_audit_2024_2026.csv"
        audit.to_csv(path, index=False)
        result["paths"] = {"alignment_audit": str(path)}
    return result


def run_dragon_case_lhb_alignment_audit(
    *,
    curated_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    curated = pd.read_csv(curated_path, low_memory=False)
    ts_codes = sorted({str(value).upper() for value in curated.get("ts_code", pd.Series(dtype="object")).dropna().astype(str) if value})
    dates = []
    for field in ["first_limit_up_date", "break_limit_date", "reversal_date", "second_wave_start_date", "peak_date", "a_kill_start_date"]:
        if field in curated.columns:
            dates.extend([str(value) for value in curated[field].dropna().astype(str) if str(value).strip()])
    start_date = min(dates) if dates else "2024-01-01"
    end_date = max(dates) if dates else "2026-05-13"
    warnings: list[str] = []
    try:
        top_list, top_inst = load_lhb_from_db(ts_codes=ts_codes, start_date=start_date, end_date=end_date, service=service)
    except Exception as exc:
        if "lhb_top_list_daily" in str(exc) or "lhb_top_inst_daily" in str(exc):
            warnings.append(str(exc))
            top_list = pd.DataFrame(columns=TOP_LIST_COLUMNS)
            top_inst = pd.DataFrame(columns=TOP_INST_COLUMNS)
        else:
            raise
    result = build_dragon_case_lhb_alignment_audit(curated, top_list, top_inst, output_dir=output_dir)
    result["warnings"] = warnings
    return result


def build_dragon_case_lhb_summary_report(
    *,
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    summary = _build_lhb_case_summary(alignment_audit)
    comparison = _build_lhb_case_comparison(curated, alignment_audit)
    report = _lhb_case_summary_report(summary=summary, comparison=comparison)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "dragon_case_lhb_summary_2024_2026.csv"
    comparison_path = out / "dragon_case_lhb_comparison_2024_2026.csv"
    report_path = out / "dragon_case_lhb_report_2024_2026.md"
    summary.to_csv(summary_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    report_path.write_text(report, encoding="utf-8")
    return {
        "summary": summary,
        "comparison": comparison,
        "paths": {
            "summary": str(summary_path),
            "comparison": str(comparison_path),
            "markdown_report": str(report_path),
        },
    }


def run_dragon_case_lhb_summary_report(
    *,
    curated_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    curated = pd.read_csv(curated_path, low_memory=False)
    audit_result = run_dragon_case_lhb_alignment_audit(
        curated_path=curated_path,
        output_dir=output_dir,
        service=service,
    )
    result = build_dragon_case_lhb_summary_report(
        curated=curated,
        alignment_audit=audit_result["alignment_audit"],
        output_dir=output_dir,
    )
    result["alignment_audit"] = audit_result["alignment_audit"]
    result["warnings"] = audit_result.get("warnings", [])
    result["paths"]["alignment_audit"] = audit_result["paths"]["alignment_audit"]
    return result


def build_lhb_case_difference_report(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    if curated.empty:
        warnings.append("curated case library is empty")
    if alignment_audit.empty:
        warnings.append("LHB alignment audit is empty")
    if lhb_features.empty:
        warnings.append("LHB event features are empty")
    factor_review = factor_review if factor_review is not None else pd.DataFrame()

    detail = _build_lhb_case_event_detail(curated, alignment_audit, factor_review, lhb_features=lhb_features)
    case_type_summary = _build_lhb_case_type_difference_summary(detail)
    event_window = _build_lhb_event_window_difference(curated, alignment_audit, lhb_features, factor_review)
    risk = _build_lhb_signal_effectiveness(detail, signal_kind="risk")
    positive = _build_lhb_signal_effectiveness(detail, signal_kind="positive")
    coverage = _build_lhb_case_coverage_summary(curated, alignment_audit)
    report = _lhb_case_difference_markdown(
        case_type_summary=case_type_summary,
        event_window=event_window,
        risk=risk,
        positive=positive,
        coverage=coverage,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "case_type_difference_summary": str(out / "lhb_case_type_difference_summary.csv"),
        "event_window_difference": str(out / "lhb_event_window_difference.csv"),
        "risk_signal_effectiveness": str(out / "lhb_risk_signal_effectiveness.csv"),
        "positive_signal_effectiveness": str(out / "lhb_positive_signal_effectiveness.csv"),
        "case_event_detail": str(out / "lhb_case_event_detail.csv"),
        "coverage_summary": str(out / "lhb_case_coverage_summary.csv"),
        "markdown_report": str(out / "lhb_case_difference_report.md"),
    }
    case_type_summary.to_csv(paths["case_type_difference_summary"], index=False)
    event_window.to_csv(paths["event_window_difference"], index=False)
    risk.to_csv(paths["risk_signal_effectiveness"], index=False)
    positive.to_csv(paths["positive_signal_effectiveness"], index=False)
    detail.to_csv(paths["case_event_detail"], index=False)
    coverage.to_csv(paths["coverage_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "case_type_difference_summary": case_type_summary,
        "event_window_difference": event_window,
        "risk_signal_effectiveness": risk,
        "positive_signal_effectiveness": positive,
        "case_event_detail": detail,
        "coverage_summary": coverage,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_case_difference_report(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = Path(output_dir) / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    return build_lhb_case_difference_report(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
    )


def build_lhb_risk_feature_diagnostics(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
    optional_diagnostics: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    factor_review = factor_review if factor_review is not None else pd.DataFrame()
    optional_diagnostics = optional_diagnostics or {}
    if curated.empty:
        warnings.append("curated case library is empty")
    if alignment_audit.empty:
        warnings.append("LHB alignment audit is empty")
    if not optional_diagnostics:
        warnings.append("Dragon diagnostics were not available; dragon risk cross table is empty")

    base_detail = _build_lhb_case_event_detail(
        curated,
        alignment_audit,
        factor_review,
        lhb_features=lhb_features,
    )
    risk_detail = _standardize_lhb_risk_features(base_detail)
    bucket = _build_lhb_risk_score_bucket_effectiveness(risk_detail)
    cross = _build_lhb_risk_failure_type_cross(risk_detail)
    dragon_cross = _build_lhb_dragon_risk_cross(risk_detail, optional_diagnostics)
    gaps = _build_lhb_coverage_gap_recommendations(risk_detail)
    report = _lhb_risk_feature_markdown(
        risk_detail=risk_detail,
        bucket=bucket,
        cross=cross,
        dragon_cross=dragon_cross,
        gaps=gaps,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "risk_feature_case_detail": str(out / "lhb_risk_feature_case_detail.csv"),
        "risk_score_bucket_effectiveness": str(out / "lhb_risk_score_bucket_effectiveness.csv"),
        "risk_failure_type_cross": str(out / "lhb_risk_failure_type_cross.csv"),
        "dragon_risk_cross_diagnostics": str(out / "lhb_dragon_risk_cross_diagnostics.csv"),
        "coverage_gap_recommendations": str(out / "lhb_coverage_gap_recommendations.csv"),
        "markdown_report": str(out / "lhb_risk_feature_diagnostics_report.md"),
    }
    risk_detail.to_csv(paths["risk_feature_case_detail"], index=False)
    bucket.to_csv(paths["risk_score_bucket_effectiveness"], index=False)
    cross.to_csv(paths["risk_failure_type_cross"], index=False)
    dragon_cross.to_csv(paths["dragon_risk_cross_diagnostics"], index=False)
    gaps.to_csv(paths["coverage_gap_recommendations"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "risk_feature_case_detail": risk_detail,
        "risk_score_bucket_effectiveness": bucket,
        "risk_failure_type_cross": cross,
        "dragon_risk_cross_diagnostics": dragon_cross,
        "coverage_gap_recommendations": gaps,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_risk_feature_diagnostics(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {
        name: pd.read_csv(path, low_memory=False)
        for name, path in optional_paths.items()
        if path.exists()
    }
    return build_lhb_risk_feature_diagnostics(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
    )


def build_lhb_diagnostics_after_failure_rule_v21(
    *,
    curated: pd.DataFrame,
    failure_v21_view: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    factor_review: pd.DataFrame,
    optional_diagnostics: dict[str, pd.DataFrame] | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    optional_diagnostics = optional_diagnostics or {}
    curated_failure_v21 = _merge_failure_v21_view(curated, failure_v21_view)
    alignment_v21 = _apply_failure_v21_labels_to_alignment(alignment_audit, curated_failure_v21)
    detail = _build_lhb_case_event_detail(curated_failure_v21, alignment_v21, factor_review, lhb_features=lhb_features)
    case_type_summary = _build_lhb_case_type_difference_summary(detail)
    event_window = _build_lhb_event_window_difference(curated_failure_v21, alignment_v21, lhb_features, factor_review)
    coverage = _build_lhb_case_coverage_summary(curated_failure_v21, alignment_v21)
    risk_detail = _standardize_lhb_risk_features(detail)
    risk_bucket = _build_lhb_risk_score_bucket_effectiveness(risk_detail)
    risk_cross = _build_lhb_risk_failure_type_cross(risk_detail)
    dragon_cross = _build_lhb_dragon_risk_cross(risk_detail, optional_diagnostics)
    coverage_gaps = _build_lhb_coverage_gap_recommendations(risk_detail)
    transition_matrix = build_failure_event_rule_v21_transition_matrix(failure_v21_view)
    comparison = _build_lhb_v2_vs_v21_comparison(
        output_dir=output_dir,
        new_detail=detail,
        curated=curated,
        failure_v21_view=failure_v21_view,
    )
    report = _lhb_after_failure_rule_v21_markdown(
        transition_matrix=transition_matrix,
        case_type_summary=case_type_summary,
        risk_cross=risk_cross,
        comparison=comparison,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "curated_failure_v21": str(out / "dragon_case_curated_library_failure_v2_1.csv"),
        "transition_matrix": str(out / "failure_event_rule_v2_1_transition_matrix.csv"),
        "case_type_difference_summary": str(out / "lhb_case_type_difference_summary_v2_1.csv"),
        "event_window_difference": str(out / "lhb_event_window_difference_v2_1.csv"),
        "case_event_detail": str(out / "lhb_case_event_detail_v2_1.csv"),
        "coverage_summary": str(out / "lhb_case_coverage_summary_v2_1.csv"),
        "risk_feature_case_detail": str(out / "lhb_risk_feature_case_detail_v2_1.csv"),
        "risk_score_bucket_effectiveness": str(out / "lhb_risk_score_bucket_effectiveness_v2_1.csv"),
        "risk_failure_type_cross": str(out / "lhb_risk_failure_type_cross_v2_1.csv"),
        "dragon_risk_cross_diagnostics": str(out / "lhb_dragon_risk_cross_diagnostics_v2_1.csv"),
        "coverage_gap_recommendations": str(out / "lhb_coverage_gap_recommendations_v2_1.csv"),
        "comparison": str(out / "lhb_risk_diagnostics_v2_vs_v2_1_comparison.csv"),
        "markdown_report": str(out / "lhb_risk_diagnostics_after_failure_rule_v2_1_report.md"),
    }
    curated_failure_v21.to_csv(paths["curated_failure_v21"], index=False)
    transition_matrix.to_csv(paths["transition_matrix"], index=False)
    case_type_summary.to_csv(paths["case_type_difference_summary"], index=False)
    event_window.to_csv(paths["event_window_difference"], index=False)
    detail.to_csv(paths["case_event_detail"], index=False)
    coverage.to_csv(paths["coverage_summary"], index=False)
    risk_detail.to_csv(paths["risk_feature_case_detail"], index=False)
    risk_bucket.to_csv(paths["risk_score_bucket_effectiveness"], index=False)
    risk_cross.to_csv(paths["risk_failure_type_cross"], index=False)
    dragon_cross.to_csv(paths["dragon_risk_cross_diagnostics"], index=False)
    coverage_gaps.to_csv(paths["coverage_gap_recommendations"], index=False)
    comparison.to_csv(paths["comparison"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "curated_failure_v21": curated_failure_v21,
        "transition_matrix": transition_matrix,
        "case_type_difference_summary": case_type_summary,
        "event_window_difference": event_window,
        "case_event_detail": detail,
        "coverage_summary": coverage,
        "risk_feature_case_detail": risk_detail,
        "risk_score_bucket_effectiveness": risk_bucket,
        "risk_failure_type_cross": risk_cross,
        "dragon_risk_cross_diagnostics": dragon_cross,
        "coverage_gap_recommendations": coverage_gaps,
        "comparison": comparison,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_diagnostics_after_failure_rule_v21(
    *,
    case_path: str | Path,
    failure_audit_path: str | Path,
    snapshot_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    failure_audit = pd.read_csv(failure_audit_path, low_memory=False)
    snapshot = pd.read_csv(snapshot_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {name: pd.read_csv(path, low_memory=False) for name, path in optional_paths.items() if path.exists()}
    failure_v21_view = build_failure_event_rule_v21_curated_view(
        curated=curated,
        case_factor_snapshot=snapshot,
        failure_rule_audit=failure_audit,
    )
    return build_lhb_diagnostics_after_failure_rule_v21(
        curated=curated,
        failure_v21_view=failure_v21_view,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
        output_dir=output_dir,
    )


def build_lhb_coverage_and_failure_rule_plan(
    *,
    coverage_gaps: pd.DataFrame,
    curated: pd.DataFrame,
    case_factor_snapshot: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    if coverage_gaps.empty:
        warnings.append("LHB coverage gap recommendations are empty")
    if curated.empty:
        warnings.append("curated case library is empty")
    if case_factor_snapshot.empty:
        warnings.append("case factor snapshot is empty")

    plan = _build_lhb_coverage_expansion_plan(coverage_gaps)
    summary = _build_lhb_coverage_expansion_summary(coverage_gaps, plan)
    commands = _lhb_coverage_expansion_commands(plan)
    audit = _build_failure_event_rule_refinement_audit(curated, case_factor_snapshot)
    suggestions = _build_failure_event_rule_refinement_suggestions(curated, audit)
    report = _lhb_coverage_failure_plan_markdown(
        plan=plan,
        summary=summary,
        audit=audit,
        suggestions=suggestions,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "coverage_expansion_plan": str(out / "lhb_coverage_expansion_plan_2024_2026.csv"),
        "coverage_expansion_summary": str(out / "lhb_coverage_expansion_summary.csv"),
        "next_commands": str(out / "lhb_coverage_expansion_next_commands.sh"),
        "failure_rule_audit": str(out / "failure_event_rule_refinement_audit.csv"),
        "failure_rule_suggestions": str(out / "failure_event_rule_refinement_suggestions.csv"),
        "markdown_report": str(out / "lhb_coverage_and_failure_rule_plan_report.md"),
    }
    plan.to_csv(paths["coverage_expansion_plan"], index=False)
    summary.to_csv(paths["coverage_expansion_summary"], index=False)
    Path(paths["next_commands"]).write_text(commands, encoding="utf-8")
    audit.to_csv(paths["failure_rule_audit"], index=False)
    suggestions.to_csv(paths["failure_rule_suggestions"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "coverage_expansion_plan": plan,
        "coverage_expansion_summary": summary,
        "failure_rule_audit": audit,
        "failure_rule_suggestions": suggestions,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_coverage_and_failure_rule_plan(
    *,
    coverage_gap_path: str | Path,
    case_path: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    coverage_gaps = pd.read_csv(coverage_gap_path, low_memory=False)
    curated = pd.read_csv(case_path, low_memory=False)
    snapshot = pd.read_csv(snapshot_path, low_memory=False)
    return build_lhb_coverage_and_failure_rule_plan(
        coverage_gaps=coverage_gaps,
        curated=curated,
        case_factor_snapshot=snapshot,
        output_dir=output_dir,
    )


def _build_lhb_coverage_expansion_plan(coverage_gaps: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "plan_id",
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "query_window_days_before",
        "query_window_days_after",
        "reason",
        "expected_value",
        "status",
        "notes",
    ]
    if coverage_gaps.empty:
        return pd.DataFrame(columns=columns)

    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    value_map = {
        "a_kill_failure": "补齐 A杀 龙头榜风险证据，验证负净买和机构卖出是否领先恶化",
        "failed_second_wave": "补齐失败二波分歧延续证据，验证事后关注和资金撤退",
        "failed_reversal": "校准反包失败规则，确认放量后走弱是否伴随龙虎榜抛压",
        "high_open_low_close_failure": "校准高开低走失败规则，确认日内回落和席位卖压",
        "one_day_pump": "校准一日脉冲规则，识别无持续性的短线扰动",
        "second_wave": "保留成功二波代表样本，作为低风险对照组",
    }
    rows = []
    for idx, record in enumerate(coverage_gaps.fillna("").to_dict("records"), start=1):
        case_type = str(record.get("verified_case_type") or record.get("case_type") or "")
        event_date = str(record.get("event_date") or "")
        if not event_date:
            continue
        days_after = 10 if case_type in {"a_kill_failure", "failed_second_wave"} else 5
        priority = priority_map.get(case_type, int(record.get("priority_for_lhb_backfill") or 9))
        rows.append(
            {
                "plan_id": f"lhb_expand_{idx:04d}",
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": record.get("success_or_failure"),
                "event_date": event_date,
                "priority_for_lhb_backfill": priority,
                "suggested_lhb_query_start_date": _shift_date(event_date, -5),
                "suggested_lhb_query_end_date": _shift_date(event_date, days_after),
                "query_window_days_before": 5,
                "query_window_days_after": days_after,
                "reason": record.get("missing_reason") or "coverage_gap",
                "expected_value": value_map.get(case_type, "补齐 LHB 覆盖，支持后续风险诊断复跑"),
                "status": "pending",
                "notes": record.get("notes") or "",
            }
        )
    return (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .sort_values(["priority_for_lhb_backfill", "case_year", "event_date", "case_id"])
        .reset_index(drop=True)
    )


def _build_lhb_coverage_expansion_summary(coverage_gaps: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "case_year",
        "priority_for_lhb_backfill",
        "case_count",
        "event_count",
        "avg_query_window_days",
        "expected_lhb_rows",
        "current_lhb_matched_count",
        "missing_lhb_count",
    ]
    if plan.empty:
        return pd.DataFrame(columns=columns)

    gaps = coverage_gaps.copy()
    if "has_lhb" not in gaps.columns:
        gaps["has_lhb"] = False
    gaps["has_lhb"] = gaps["has_lhb"].astype(bool)
    merged = plan.merge(
        gaps[["case_id", "event_date", "has_lhb"]].drop_duplicates(),
        on=["case_id", "event_date"],
        how="left",
    )
    merged["has_lhb"] = merged["has_lhb"].fillna(False).astype(bool)
    merged["query_window_days"] = merged["query_window_days_before"] + 1 + merged["query_window_days_after"]
    rows = []
    group_cols = ["verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill"]
    for keys, group in merged.groupby(group_cols, dropna=False):
        case_type, success, year, priority = keys
        avg_window = pd.to_numeric(group["query_window_days"], errors="coerce").mean()
        rows.append(
            {
                "verified_case_type": case_type,
                "success_or_failure": success,
                "case_year": year,
                "priority_for_lhb_backfill": priority,
                "case_count": int(group["case_id"].nunique()),
                "event_count": int(len(group)),
                "avg_query_window_days": avg_window,
                "expected_lhb_rows": int(round(len(group) * avg_window)) if pd.notna(avg_window) else 0,
                "current_lhb_matched_count": int(group["has_lhb"].sum()),
                "missing_lhb_count": int((~group["has_lhb"]).sum()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(group_cols).reset_index(drop=True)


def _lhb_coverage_expansion_commands(plan: pd.DataFrame) -> str:
    if plan.empty:
        return "#!/usr/bin/env bash\nset -euo pipefail\n\n# No LHB coverage expansion cases available.\n"

    top5 = ",".join(plan.head(5)["ts_code"].dropna().astype(str).tolist())
    mid = plan[plan["verified_case_type"].isin(["a_kill_failure", "failed_second_wave"])]
    mid_codes = ",".join(mid["ts_code"].dropna().astype(str).unique().tolist())
    high = plan[plan["priority_for_lhb_backfill"] <= 4]
    high_codes = ",".join(high["ts_code"].dropna().astype(str).unique().tolist())
    start = str(plan["suggested_lhb_query_start_date"].min())
    top_end = str(plan.head(5)["suggested_lhb_query_end_date"].max())
    mid_end = str(mid["suggested_lhb_query_end_date"].max()) if not mid.empty else top_end
    high_end = str(high["suggested_lhb_query_end_date"].max()) if not high.empty else top_end
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            "# AkShare LHB 小批量补数命令计划，只生成建议，不自动执行全量。",
            "# TODO: do not run full-market LHB backfill before reviewing sample results.",
            "# TODO: if stock-research lhb-sample-import cannot cover date range backfill, implement AkShare LHB range backfill CLI.",
            "",
            "# 1. 小样本: Top 5 priority cases, 事件日前后 ±5 日",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {top_end} --ts-codes {top5} --provider akshare --output-dir outputs/research/lhb_top5_sample",
            "",
            "# 2. 中样本: 所有 a_kill_failure / failed_second_wave, 事件日前后 ±5 到 ±10 日",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {mid_end} --ts-codes {mid_codes} --provider akshare --output-dir outputs/research/lhb_failure_mid_sample",
            "",
            "# 3. 扩展样本: 全部 high priority gap cases",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {high_end} --ts-codes {high_codes} --provider akshare --output-dir outputs/research/lhb_high_priority_sample",
            "",
        ]
    )


def _build_failure_event_rule_refinement_audit(curated: pd.DataFrame, case_factor_snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "current_verified_case_type",
        "event_date",
        "pre_3d_return",
        "pre_5d_return",
        "post_1d_return",
        "post_3d_return",
        "post_5d_return",
        "post_10d_return",
        "post_5d_max_drawdown",
        "post_10d_max_drawdown",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "close_position_in_day",
        "is_limit_up_day",
        "is_break_limit_event",
        "is_reversal_event",
        "is_second_wave_event",
        "is_a_kill_event",
        "suggested_refined_case_type",
        "refinement_reason",
        "confidence",
    ]
    if curated.empty or case_factor_snapshot.empty:
        return pd.DataFrame(columns=columns)
    targets = {
        "failed_reversal",
        "high_open_low_close_failure",
        "one_day_pump",
        "failed_second_wave",
        "a_kill_failure",
    }
    cases = curated.copy()
    cases["current_verified_case_type"] = cases.get("verified_case_type", cases.get("case_type", "")).fillna("")
    cases = cases[cases["current_verified_case_type"].isin(targets)]
    snapshot = case_factor_snapshot.copy()
    if "relative_day" in snapshot.columns:
        snapshot = snapshot[pd.to_numeric(snapshot["relative_day"], errors="coerce").fillna(0).eq(0)]
    merged = cases.merge(snapshot, on="case_id", how="left", suffixes=("", "_snapshot"))
    rows = []
    for record in merged.fillna("").to_dict("records"):
        suggested, reason, confidence = _suggest_failure_case_type(record)
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code") or record.get("ts_code_snapshot"),
                "stock_name": record.get("stock_name") or record.get("stock_name_snapshot"),
                "current_verified_case_type": record.get("current_verified_case_type"),
                "event_date": record.get("event_date") or record.get("event_date_snapshot"),
                "pre_3d_return": record.get("pre_3d_return"),
                "pre_5d_return": record.get("pre_5d_return"),
                "post_1d_return": record.get("future_1d_return"),
                "post_3d_return": record.get("future_3d_return"),
                "post_5d_return": record.get("future_5d_return"),
                "post_10d_return": record.get("future_10d_return"),
                "post_5d_max_drawdown": record.get("future_5d_max_drawdown"),
                "post_10d_max_drawdown": record.get("future_10d_max_drawdown"),
                "amount_vs_20d": record.get("amount_vs_20d"),
                "high_to_close_drawdown": record.get("high_to_close_drawdown"),
                "close_position_in_day": record.get("close_position_in_day"),
                "is_limit_up_day": bool(record.get("is_limit_up_day")),
                "is_break_limit_event": bool(record.get("is_break_limit_event")),
                "is_reversal_event": bool(record.get("is_reversal_event")),
                "is_second_wave_event": bool(record.get("is_second_wave_event")),
                "is_a_kill_event": bool(record.get("is_a_kill_event")),
                "suggested_refined_case_type": suggested,
                "refinement_reason": reason,
                "confidence": confidence,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _suggest_failure_case_type(record: dict[str, Any]) -> tuple[str, str, str]:
    current = str(record.get("current_verified_case_type") or "")
    post_10d = pd.to_numeric(pd.Series([record.get("future_10d_return")]), errors="coerce").iloc[0]
    drawdown = pd.to_numeric(pd.Series([record.get("future_10d_max_drawdown")]), errors="coerce").iloc[0]
    high_to_close = pd.to_numeric(pd.Series([record.get("high_to_close_drawdown")]), errors="coerce").iloc[0]
    amount = pd.to_numeric(pd.Series([record.get("amount_vs_20d")]), errors="coerce").iloc[0]
    pre_5d = pd.to_numeric(pd.Series([record.get("pre_5d_return")]), errors="coerce").iloc[0]
    if bool(record.get("is_a_kill_event")) or (pd.notna(post_10d) and post_10d <= -0.20):
        return "a_kill_failure", "10日后续跌幅/回撤明显，优先归入 A杀失败边界", "high"
    if bool(record.get("is_second_wave_event")) and pd.notna(post_10d) and post_10d < 0:
        return "failed_second_wave", "二波形态成立但后续收益转弱，保留失败二波标签", "high"
    if bool(record.get("is_reversal_event")) and pd.notna(pre_5d) and pre_5d > 0.10:
        return "failed_reversal", "前期已有涨幅且反包后走弱，适合反包失败规则", "medium"
    if bool(record.get("is_break_limit_event")) and pd.notna(high_to_close) and high_to_close >= 0.08:
        return "high_open_low_close_failure", "日内高点回落较深且破板/回落，适合高开低走失败", "medium"
    if bool(record.get("is_limit_up_day")) and pd.notna(amount) and amount >= 3:
        return "one_day_pump", "放量脉冲但持续性不足，适合一日脉冲规则", "medium"
    return current, "当前字段不足以稳定改判，保持原标签并补充人工复核", "low"


def _build_failure_event_rule_refinement_suggestions(curated: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_type",
        "current_sample_count",
        "suggested_rule",
        "required_fields",
        "expected_improvement",
        "risk_of_false_positive",
        "notes",
    ]
    case_types = curated.get("verified_case_type", pd.Series(dtype=str)).fillna("").astype(str)
    counts = case_types.value_counts().to_dict()
    rows = [
        {
            "case_type": "failed_reversal",
            "current_sample_count": int(counts.get("failed_reversal", 0)),
            "suggested_rule": "前5日涨幅较高，事件日反包/涨停尝试失败，后3-5日收益转负或回撤加深。",
            "required_fields": "pre_5d_return,is_reversal_event,is_limit_up_day,post_3d_return,post_5d_max_drawdown",
            "expected_improvement": "降低把普通震荡误标为反包失败的概率。",
            "risk_of_false_positive": "强趋势中的短暂换手可能被误判为失败。",
            "notes": "需要和 high_open_low_close_failure 按日内回落幅度区分。",
        },
        {
            "case_type": "high_open_low_close_failure",
            "current_sample_count": int(counts.get("high_open_low_close_failure", 0)),
            "suggested_rule": "事件日高开或冲高后收盘靠近低位，high_to_close_drawdown 明显，且破板/后续3-5日走弱。",
            "required_fields": "high_to_close_drawdown,close_position_in_day,is_break_limit_event,post_3d_return",
            "expected_improvement": "更准确识别高位分歧后的日内失败。",
            "risk_of_false_positive": "低位洗盘也可能出现高开低走。",
            "notes": "和 one_day_pump 的边界应以是否已有前置涨幅和是否破板为核心。",
        },
        {
            "case_type": "one_day_pump",
            "current_sample_count": int(counts.get("one_day_pump", 0)),
            "suggested_rule": "低前置涨幅、事件日放量脉冲或涨停，后1-5日没有持续收益。",
            "required_fields": "pre_3d_return,pre_5d_return,amount_vs_20d,is_limit_up_day,post_1d_return,post_5d_return",
            "expected_improvement": "避免把无持续性的单日脉冲混入二波或反包失败。",
            "risk_of_false_positive": "首板启动初期可能被误伤。",
            "notes": "若前5日涨幅和日内回落都高，应优先考虑 high_open_low_close_failure。",
        },
        {
            "case_type": "failed_second_wave",
            "current_sample_count": int(counts.get("failed_second_wave", 0)),
            "suggested_rule": "二波事件形态成立，但后5-10日收益转弱，且非单日 A杀式连续下挫。",
            "required_fields": "is_second_wave_event,pre_5d_return,post_5d_return,post_10d_return,post_10d_max_drawdown",
            "expected_improvement": "把失败二波从一日脉冲和 A杀中拆清。",
            "risk_of_false_positive": "样本窗口太短会把正常二波回踩误判为失败。",
            "notes": "与 a_kill_failure 的边界看跌幅速度和回撤深度。",
        },
        {
            "case_type": "a_kill_failure",
            "current_sample_count": int(counts.get("a_kill_failure", 0)),
            "suggested_rule": "高位或二波后快速转弱，后5-10日负收益和最大回撤显著。",
            "required_fields": "is_a_kill_event,pre_5d_return,post_5d_return,post_10d_return,post_10d_max_drawdown",
            "expected_improvement": "优先识别最需要 LHB 风险证据补充的失败类型。",
            "risk_of_false_positive": "系统性下跌日可能放大个股 A杀标签。",
            "notes": "应高于 failed_second_wave 的风险优先级。",
        },
    ]
    return pd.DataFrame(rows).reindex(columns=columns)


def _lhb_coverage_failure_plan_markdown(
    *,
    plan: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    warnings: list[str],
) -> str:
    high_priority = plan[plan["priority_for_lhb_backfill"] <= 3] if not plan.empty else plan
    return "\n".join(
        [
            "# LHB Coverage Expansion & Failure Rule Refinement Plan v1",
            "",
            "## 1. 背景",
            "LHB 风险诊断已经能解释 A杀、失败二波和高位分歧的部分风险，但覆盖缺口和失败事件标签仍是短板。",
            "",
            "## 2. LHB 覆盖缺口",
            f"当前覆盖扩展计划 {len(plan)} 行，高优先级案例 {len(high_priority)} 行。优先补 a_kill_failure、failed_second_wave、failed_reversal。",
            _table_preview(summary, rows=20),
            "",
            "## 3. 覆盖扩展计划",
            "默认事件日前 5 日到事件后 5 日；a_kill_failure 和 failed_second_wave 扩到事件后 10 日。",
            _table_preview(plan.head(20), rows=20),
            "",
            "## 4. AkShare 小批量补数建议",
            "先小样本 Top 5，再跑 a_kill_failure / failed_second_wave 中样本，最后扩展到全部高优先级 gap cases。",
            "",
            "## 5. 失败事件规则问题",
            "failed_reversal、high_open_low_close_failure、one_day_pump 当前边界容易混淆，需要引入前置涨幅、日内回落、放量和后续收益/回撤共同约束。",
            _table_preview(audit.head(20), rows=20),
            "",
            "## 6. 规则修正建议",
            _table_preview(suggestions, rows=20),
            "",
            "## 7. 下一步",
            "- 先补 LHB 高优先级窗口；",
            "- 再实现失败事件规则 v2；",
            "- 再重新跑 LHB risk diagnostics；",
            "- 最后再考虑 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _compact_date(value: str) -> str:
    return pd.to_datetime(value, errors="coerce").strftime("%Y%m%d")


def _code_to_ts_code(value: Any) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        return text.upper()
    if digits.startswith(("8", "4")):
        exchange = "BJ"
    elif digits.startswith(("5", "6", "9")):
        exchange = "SH"
    else:
        exchange = "SZ"
    return f"{digits}.{exchange}"


def _top_list_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.name,
            row.close,
            row.pct_change,
            row.turnover_rate,
            row.amount,
            row.l_sell,
            row.l_buy,
            row.l_amount,
            row.net_amount,
            row.net_rate,
            row.amount_rate,
            row.float_values,
            row.reason,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _top_inst_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.exalter,
            row.buy,
            row.buy_rate,
            row.sell,
            row.sell_rate,
            row.net_buy,
            row.reason,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _event_feature_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.on_lhb,
            row.lhb_reason,
            row.lhb_net_buy_amount,
            row.lhb_net_buy_ratio,
            row.lhb_buy_amount,
            row.lhb_sell_amount,
            row.institution_net_buy,
            row.top_seat_concentration,
            row.repeat_on_list_count_3d,
            row.repeat_on_list_count_5d,
            row.lhb_after_limit_up,
            row.lhb_after_break_limit,
            row.lhb_after_reversal,
            row.lhb_one_day_pump_risk,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _normalize_date_code_frame(frame: pd.DataFrame, date_col: str, code_col: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    data[code_col] = data[code_col].fillna("").astype(str).str.upper()
    return data


def _numeric_scalar(series: pd.Series, *, aggregator: str) -> float | None:
    if series.empty:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    if aggregator == "sum":
        return float(numeric.sum())
    return float(numeric.max())


def _join_unique(series: pd.Series) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for value in series.fillna("").astype(str):
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return " | ".join(values)


def _repeat_on_list_count(
    frame: pd.DataFrame,
    *,
    ts_code: str,
    source: str,
    trade_date: str,
    lookback_days: int,
) -> int:
    if frame.empty:
        return 0
    start_date = _shift_date(trade_date, -lookback_days)
    mask = (
        (frame["ts_code"] == ts_code)
        & (frame["source"] == source)
        & (frame["trade_date"] >= start_date)
        & (frame["trade_date"] <= trade_date)
    )
    return int(frame.loc[mask, "trade_date"].nunique())


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "" or pd.isna(value):
        return None
    return float(value)


def _coerce_ratio(value: Any, *, clamp: bool = True) -> float | None:
    if value is None or pd.isna(value):
        return None
    ratio = float(value)
    if abs(ratio) > 1.0:
        ratio = ratio / 100.0
    if clamp:
        ratio = max(min(ratio, 1.0), -1.0)
    return ratio


def _build_lhb_case_summary(alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_type",
        "event_type",
        "sample_count",
        "matched_count",
        "matched_rate",
        "on_event_date_count",
        "on_event_date_rate",
        "before_event_3d_count",
        "before_event_3d_rate",
        "after_event_3d_count",
        "after_event_3d_rate",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
    ]
    if alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    frame = alignment_audit.copy()
    rows: list[dict[str, Any]] = []
    for (case_type, event_type), group in frame.groupby(["case_type", "event_type"], dropna=False):
        sample_count = int(len(group))
        matched_count = int((group["lhb_alignment_status"] == "matched").sum())
        on_count = int(pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).sum())
        before_count = int(pd.to_numeric(group["lhb_before_event_3d"], errors="coerce").fillna(False).astype(bool).sum())
        after_count = int(pd.to_numeric(group["lhb_after_event_3d"], errors="coerce").fillna(False).astype(bool).sum())
        rows.append(
            {
                "case_type": case_type,
                "event_type": event_type,
                "sample_count": sample_count,
                "matched_count": matched_count,
                "matched_rate": matched_count / sample_count if sample_count else None,
                "on_event_date_count": on_count,
                "on_event_date_rate": on_count / sample_count if sample_count else None,
                "before_event_3d_count": before_count,
                "before_event_3d_rate": before_count / sample_count if sample_count else None,
                "after_event_3d_count": after_count,
                "after_event_3d_rate": after_count / sample_count if sample_count else None,
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["case_type", "event_type"]).reset_index(drop=True)


def _build_lhb_case_comparison(curated: pd.DataFrame, alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_group",
        "success_or_failure",
        "case_type",
        "sample_count",
        "matched_count",
        "on_event_date_rate",
        "before_event_3d_rate",
        "after_event_3d_rate",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    meta = curated.copy()
    meta["case_type_key"] = meta.get("verified_case_type", pd.Series(dtype="object")).fillna("").astype(str)
    empty_mask = meta["case_type_key"] == ""
    if "case_type" in meta.columns:
        meta.loc[empty_mask, "case_type_key"] = meta.loc[empty_mask, "case_type"].fillna("").astype(str)
    merged = alignment_audit.merge(
        meta[["case_id", "success_or_failure", "case_type_key"]],
        on="case_id",
        how="left",
    )
    merged["case_type_final"] = merged["case_type"].fillna("").astype(str)
    empty_mask = merged["case_type_final"] == ""
    merged.loc[empty_mask, "case_type_final"] = merged.loc[empty_mask, "case_type_key"].fillna("").astype(str)
    merged["case_group"] = merged["success_or_failure"].fillna("unknown").astype(str) + ":" + merged["case_type_final"].fillna("unknown").astype(str)
    rows: list[dict[str, Any]] = []
    for case_group, group in merged.groupby("case_group", dropna=False):
        sample_count = int(len(group))
        matched_count = int((group["lhb_alignment_status"] == "matched").sum())
        rows.append(
            {
                "case_group": case_group,
                "success_or_failure": str(group["success_or_failure"].iloc[0] or ""),
                "case_type": str(group["case_type_final"].iloc[0] or ""),
                "sample_count": sample_count,
                "matched_count": matched_count,
                "on_event_date_rate": pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).mean(),
                "before_event_3d_rate": pd.to_numeric(group["lhb_before_event_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "after_event_3d_rate": pd.to_numeric(group["lhb_after_event_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "case_type"]).reset_index(drop=True)


def _lhb_case_summary_report(*, summary: pd.DataFrame, comparison: pd.DataFrame) -> str:
    focus = comparison[comparison["case_type"].isin(["second_wave", "failed_second_wave", "a_kill_failure", "failed_reversal"])].copy() if not comparison.empty else comparison
    return "\n".join(
        [
            "# LHB Case Summary 2024-2026",
            "",
            "## 1. Scope",
            "本报告只做案例层龙虎榜事件诊断，不接策略打分，不做回测。",
            "",
            "## 2. Event Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Success vs Failure",
            _table_preview(comparison, rows=20),
            "",
            "## 4. Focus Groups",
            _table_preview(focus, rows=12),
            "",
            "## 5. Notes",
            "- on_event_date / before_event_3d / after_event_3d 用于看上榜时点分布。",
            "- institution_net_buy / repeat_on_list_count_5d / one_day_pump_risk 目前是诊断特征，不进入策略。",
        ]
    )


def _table_preview(frame: pd.DataFrame, *, rows: int = 12) -> str:
    if frame.empty:
        return "无数据。"
    return frame.head(rows).to_markdown(index=False)


def _build_lhb_case_event_detail(
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    factor_review: pd.DataFrame,
    *,
    lhb_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "case_type",
        "verified_case_type",
        "success_or_failure",
        "role",
        "event_type",
        "event_date",
        "lhb_on_event_date",
        "lhb_before_3d",
        "lhb_after_3d",
        "lhb_after_5d",
        "lhb_net_buy_amount_event",
        "lhb_net_buy_ratio_event",
        "institution_net_buy_event",
        "top_seat_concentration_event",
        "repeat_on_list_count_3d",
        "repeat_on_list_count_5d",
        "lhb_one_day_pump_risk",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
        "diagnostic_note",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    features = _normalize_date_code_frame((lhb_features if lhb_features is not None else pd.DataFrame()).copy().reindex(columns=LHB_EVENT_FEATURE_COLUMNS), "trade_date", "ts_code")
    meta = curated.copy()
    meta["case_id"] = meta["case_id"].fillna("").astype(str)
    lookup = meta.set_index("case_id", drop=False)
    future_lookup = pd.DataFrame()
    if not factor_review.empty:
        future_lookup = factor_review.copy()
        future_lookup["case_id"] = future_lookup.get("case_id", pd.Series(dtype="object")).fillna("").astype(str)
        if "case_id" not in future_lookup.columns or not future_lookup["case_id"].astype(str).str.strip().any():
            future_lookup["case_id"] = future_lookup.get("web_candidate_id", pd.Series(dtype="object")).fillna("").astype(str).map(
                lambda value: f"curated_{value.split('_')[-1]}" if value else ""
            )
    rows: list[dict[str, Any]] = []
    for record in alignment_audit.fillna("").to_dict("records"):
        case_id = str(record.get("case_id") or "")
        meta_row = lookup.loc[case_id] if case_id in lookup.index else pd.Series(dtype="object")
        if isinstance(meta_row, pd.DataFrame):
            meta_row = meta_row.iloc[0]
        future_row = pd.Series(dtype="object")
        if not future_lookup.empty and case_id:
            matched_future = future_lookup[(future_lookup["case_id"] == case_id)]
            if matched_future.empty and "ts_code" in future_lookup.columns:
                matched_future = future_lookup[(future_lookup["ts_code"].fillna("").astype(str).str.upper() == str(record.get("ts_code") or "").upper())]
            if not matched_future.empty and "event_type" in matched_future.columns:
                event_matched = matched_future[matched_future["event_type"].fillna("").astype(str) == str(record.get("event_type") or "")]
                if not event_matched.empty:
                    matched_future = event_matched
            if not matched_future.empty and "event_date" in matched_future.columns:
                date_matched = matched_future[matched_future["event_date"].fillna("").astype(str) == str(record.get("event_date") or "")]
                if not date_matched.empty:
                    matched_future = date_matched
            if not matched_future.empty:
                if "relative_day" in matched_future.columns:
                    rel0 = matched_future[pd.to_numeric(matched_future["relative_day"], errors="coerce").fillna(999).astype(int) == 0]
                    future_row = rel0.iloc[0] if not rel0.empty else matched_future.iloc[0]
                else:
                    future_row = matched_future.iloc[0]
        event_feature = pd.Series(dtype="object")
        if not features.empty:
            feature_rows = features[
                (features["ts_code"] == str(record.get("ts_code") or "").upper())
                & (features["trade_date"] == str(record.get("event_date") or ""))
            ]
            if not feature_rows.empty:
                event_feature = feature_rows.iloc[0]
        after_5d = bool(record.get("lhb_after_event_3d"))
        if not features.empty:
            event_date = str(record.get("event_date") or "")
            if event_date:
                after_5d = not features[
                    (features["ts_code"] == str(record.get("ts_code") or "").upper())
                    & (features["trade_date"] > event_date)
                    & (features["trade_date"] <= _shift_date(event_date, 5))
                ].empty
        diagnostic_note = _diagnostic_note_from_case_and_lhb(meta_row, record)
        rows.append(
            {
                "case_id": case_id,
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": meta_row.get("case_year") if not meta_row.empty else None,
                "case_type": record.get("case_type") or meta_row.get("case_type"),
                "verified_case_type": meta_row.get("verified_case_type") if not meta_row.empty else None,
                "success_or_failure": meta_row.get("success_or_failure") if not meta_row.empty else None,
                "role": meta_row.get("role") if not meta_row.empty else None,
                "event_type": record.get("event_type"),
                "event_date": record.get("event_date"),
                "lhb_on_event_date": bool(record.get("lhb_on_event_date")),
                "lhb_before_3d": bool(record.get("lhb_before_event_3d")),
                "lhb_after_3d": bool(record.get("lhb_after_event_3d")),
                "lhb_after_5d": after_5d,
                "lhb_net_buy_amount_event": _float_or_none(record.get("lhb_net_buy_amount")),
                "lhb_net_buy_ratio_event": _float_or_none(event_feature.get("lhb_net_buy_ratio")) if not event_feature.empty else None,
                "institution_net_buy_event": _float_or_none(record.get("institution_net_buy")),
                "top_seat_concentration_event": _float_or_none(record.get("top_seat_concentration")),
                "repeat_on_list_count_3d": int(record.get("repeat_on_list_count_3d") or 0),
                "repeat_on_list_count_5d": int(record.get("repeat_on_list_count_5d") or 0),
                "lhb_one_day_pump_risk": _float_or_none(record.get("lhb_one_day_pump_risk")),
                "future_3d_return": _float_or_none(future_row.get("future_3d_return")) if not future_row.empty else None,
                "future_5d_return": _float_or_none(future_row.get("future_5d_return")) if not future_row.empty else None,
                "future_10d_return": _float_or_none(future_row.get("future_10d_return")) if not future_row.empty else None,
                "future_5d_max_drawdown": _float_or_none(future_row.get("future_5d_max_drawdown")) if not future_row.empty else None,
                "future_10d_max_drawdown": _float_or_none(future_row.get("future_10d_max_drawdown")) if not future_row.empty else None,
                "diagnostic_note": diagnostic_note,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _diagnostic_note_from_case_and_lhb(meta_row: pd.Series, record: dict[str, Any]) -> str:
    case_type = str(record.get("case_type") or meta_row.get("case_type") or "")
    success = str(meta_row.get("success_or_failure") or "")
    net_buy = _float_or_none(record.get("lhb_net_buy_amount"))
    risk = _float_or_none(record.get("lhb_one_day_pump_risk"))
    if net_buy is None and not bool(record.get("lhb_on_event_date")):
        return "lhb_missing"
    if case_type == "second_wave" and success == "success" and (net_buy or 0) > 0:
        return "success_second_wave_with_positive_lhb"
    if case_type == "failed_second_wave" and bool(record.get("lhb_after_3d")):
        return "failed_second_wave_after_event_lhb_attention"
    if case_type == "a_kill_failure" and (net_buy or 0) < 0:
        return "a_kill_with_negative_lhb"
    if risk is not None and risk >= 0.7:
        return "high_pump_risk_after_event"
    if net_buy is not None and net_buy > 0:
        return "lhb_no_clear_signal"
    return "lhb_no_clear_signal"


def _build_lhb_case_type_difference_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "success_or_failure",
        "verified_case_type",
        "case_type",
        "role",
        "sample_count",
        "lhb_on_event_date_rate",
        "lhb_before_3d_rate",
        "lhb_after_3d_rate",
        "avg_lhb_net_buy_amount_on_event",
        "median_lhb_net_buy_amount_on_event",
        "avg_lhb_net_buy_ratio_on_event",
        "avg_institution_net_buy_on_event",
        "avg_top_seat_concentration_on_event",
        "avg_repeat_on_list_count_3d",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (success_or_failure, verified_case_type, case_type, role), group in detail.groupby(
        ["success_or_failure", "verified_case_type", "case_type", "role"], dropna=False
    ):
        rows.append(
            {
                "success_or_failure": success_or_failure,
                "verified_case_type": verified_case_type,
                "case_type": case_type,
                "role": role,
                "sample_count": int(len(group)),
                "lhb_on_event_date_rate": pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).mean(),
                "lhb_before_3d_rate": pd.to_numeric(group["lhb_before_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "lhb_after_3d_rate": pd.to_numeric(group["lhb_after_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "avg_lhb_net_buy_amount_on_event": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").mean(),
                "median_lhb_net_buy_amount_on_event": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").median(),
                "avg_lhb_net_buy_ratio_on_event": pd.to_numeric(group["lhb_net_buy_ratio_event"], errors="coerce").mean(),
                "avg_institution_net_buy_on_event": pd.to_numeric(group["institution_net_buy_event"], errors="coerce").mean(),
                "avg_top_seat_concentration_on_event": pd.to_numeric(group["top_seat_concentration_event"], errors="coerce").mean(),
                "avg_repeat_on_list_count_3d": pd.to_numeric(group["repeat_on_list_count_3d"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "verified_case_type", "case_type", "role"]).reset_index(drop=True)


def _window_rows(detail: pd.DataFrame, lhb_features: pd.DataFrame) -> pd.DataFrame:
    if detail.empty or lhb_features.empty:
        return pd.DataFrame()
    features = _normalize_date_code_frame(lhb_features, "trade_date", "ts_code")
    rows: list[dict[str, Any]] = []
    for record in detail.fillna("").to_dict("records"):
        event_date = str(record.get("event_date") or "")
        ts_code = str(record.get("ts_code") or "").upper()
        event_features = features[features["ts_code"] == ts_code]
        if event_features.empty:
            continue
        windows = {
            "before_3d": event_features[(event_features["trade_date"] < event_date) & (event_features["trade_date"] >= _shift_date(event_date, -3))],
            "event_day": event_features[event_features["trade_date"] == event_date],
            "after_3d": event_features[(event_features["trade_date"] > event_date) & (event_features["trade_date"] <= _shift_date(event_date, 3))],
            "after_5d": event_features[(event_features["trade_date"] > event_date) & (event_features["trade_date"] <= _shift_date(event_date, 5))],
        }
        for window, frame in windows.items():
            if frame.empty:
                rows.append(
                    {
                        **record,
                        "event_window": window,
                        "lhb_hit_rate": 0.0,
                        "avg_lhb_net_buy_amount": None,
                        "median_lhb_net_buy_amount": None,
                        "avg_lhb_net_buy_ratio": None,
                        "avg_institution_net_buy": None,
                        "avg_top_seat_concentration": None,
                        "avg_repeat_on_list_count_3d": None,
                        "avg_repeat_on_list_count_5d": None,
                        "avg_lhb_one_day_pump_risk": None,
                    }
                )
                continue
            rows.append(
                {
                    **record,
                    "event_window": window,
                    "lhb_hit_rate": 1.0,
                    "avg_lhb_net_buy_amount": pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").mean(),
                    "median_lhb_net_buy_amount": pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").median(),
                    "avg_lhb_net_buy_ratio": pd.to_numeric(frame["lhb_net_buy_ratio"], errors="coerce").mean(),
                    "avg_institution_net_buy": pd.to_numeric(frame["institution_net_buy"], errors="coerce").mean(),
                    "avg_top_seat_concentration": pd.to_numeric(frame["top_seat_concentration"], errors="coerce").mean(),
                    "avg_repeat_on_list_count_3d": pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce").mean(),
                    "avg_repeat_on_list_count_5d": pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce").mean(),
                    "avg_lhb_one_day_pump_risk": pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").mean(),
                }
            )
    return pd.DataFrame(rows)


def _build_lhb_event_window_difference(
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    lhb_features: pd.DataFrame,
    factor_review: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "success_or_failure",
        "verified_case_type",
        "event_window",
        "sample_count",
        "lhb_hit_rate",
        "avg_lhb_net_buy_amount",
        "median_lhb_net_buy_amount",
        "avg_lhb_net_buy_ratio",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_3d",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
    ]
    detail = _build_lhb_case_event_detail(curated, alignment_audit, factor_review, lhb_features=lhb_features)
    window_frame = _window_rows(detail, lhb_features)
    if window_frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (success_or_failure, verified_case_type, event_window), group in window_frame.groupby(
        ["success_or_failure", "verified_case_type", "event_window"], dropna=False
    ):
        rows.append(
            {
                "success_or_failure": success_or_failure,
                "verified_case_type": verified_case_type,
                "event_window": event_window,
                "sample_count": int(len(group)),
                "lhb_hit_rate": pd.to_numeric(group["lhb_hit_rate"], errors="coerce").mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["avg_lhb_net_buy_amount"], errors="coerce").mean(),
                "median_lhb_net_buy_amount": pd.to_numeric(group["median_lhb_net_buy_amount"], errors="coerce").median(),
                "avg_lhb_net_buy_ratio": pd.to_numeric(group["avg_lhb_net_buy_ratio"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["avg_institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["avg_top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_3d": pd.to_numeric(group["avg_repeat_on_list_count_3d"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["avg_repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["avg_lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "verified_case_type", "event_window"]).reset_index(drop=True)


def _build_lhb_signal_effectiveness(detail: pd.DataFrame, *, signal_kind: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    frame = detail.copy()
    if signal_kind == "risk":
        label_frames = {
            "lhb_negative_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") < 0],
            "lhb_strong_negative_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") <= frame["lhb_net_buy_amount_event"].quantile(0.25)],
            "lhb_high_pump_risk": frame[pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce") >= frame["lhb_one_day_pump_risk"].quantile(0.75)],
            "lhb_high_concentration": frame[pd.to_numeric(frame["top_seat_concentration_event"], errors="coerce") >= frame["top_seat_concentration_event"].quantile(0.75)],
            "lhb_repeat_attention": frame[(pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce") >= 2) | (pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce") >= 3)],
            "lhb_institution_selling": frame[pd.to_numeric(frame["institution_net_buy_event"], errors="coerce") < 0],
        }
        label_col = "risk_signal"
    else:
        label_frames = {
            "lhb_positive_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0],
            "lhb_institution_positive": frame[pd.to_numeric(frame["institution_net_buy_event"], errors="coerce") > 0],
            "lhb_repeat_with_positive_net_buy": frame[(pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce") >= 2) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
            "lhb_after_break_with_positive_net_buy": frame[(frame["lhb_after_3d"].astype(bool)) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
            "lhb_after_reversal_with_positive_net_buy": frame[(frame["diagnostic_note"].astype(str).str.contains("reversal", case=False, na=False)) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
        }
        label_col = "positive_signal"
    rows: list[dict[str, Any]] = []
    for label, group in label_frames.items():
        rows.append(
            {
                label_col: label,
                "sample_count": int(len(group)),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "win_rate_3d": (pd.to_numeric(group["future_3d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "win_rate_5d": (pd.to_numeric(group["future_5d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "win_rate_10d": (pd.to_numeric(group["future_10d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                "case_type_distribution": str(group["case_type"].value_counts().to_dict()) if "case_type" in group.columns else "{}",
                "success_failure_distribution": str(group["success_or_failure"].value_counts().to_dict()) if "success_or_failure" in group.columns else "{}",
            }
        )
    columns = [
        label_col,
        "sample_count",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "win_rate_3d",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "case_type_distribution",
        "success_failure_distribution",
    ]
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_lhb_case_coverage_summary(curated: pd.DataFrame, alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "total_cases",
        "cases_with_any_lhb",
        "cases_without_lhb",
        "total_case_events",
        "matched_case_events",
        "missing_case_events",
        "matched_rate",
        "by_case_type_matched_rate",
        "by_year_matched_rate",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame([
            {
                "total_cases": int(len(curated)),
                "cases_with_any_lhb": 0,
                "cases_without_lhb": int(len(curated)),
                "total_case_events": 0,
                "matched_case_events": 0,
                "missing_case_events": 0,
                "matched_rate": 0.0,
                "by_case_type_matched_rate": "{}",
                "by_year_matched_rate": "{}",
            }
        ], columns=columns)
    matched_cases = alignment_audit[alignment_audit["lhb_alignment_status"] == "matched"]
    cases_with_lhb = int(matched_cases["case_id"].nunique())
    total_case_events = int(len(alignment_audit))
    matched_case_events = int((alignment_audit["lhb_alignment_status"] == "matched").sum())
    by_case_type = {
        key: float((group["lhb_alignment_status"] == "matched").mean())
        for key, group in alignment_audit.groupby("case_type", dropna=False)
    }
    case_year_map = curated.set_index("case_id")["case_year"].to_dict() if "case_id" in curated.columns else {}
    year_series = alignment_audit["case_id"].map(case_year_map)
    by_year = {
        str(key): float((group["lhb_alignment_status"] == "matched").mean())
        for key, group in alignment_audit.assign(case_year=year_series).groupby("case_year", dropna=False)
    }
    return pd.DataFrame([
        {
            "total_cases": int(len(curated)),
            "cases_with_any_lhb": cases_with_lhb,
            "cases_without_lhb": int(len(curated)) - cases_with_lhb,
            "total_case_events": total_case_events,
            "matched_case_events": matched_case_events,
            "missing_case_events": total_case_events - matched_case_events,
            "matched_rate": matched_case_events / total_case_events if total_case_events else 0.0,
            "by_case_type_matched_rate": str(by_case_type),
            "by_year_matched_rate": str(by_year),
        }
    ], columns=columns)


def _merge_failure_v21_view(curated: pd.DataFrame, failure_v21_view: pd.DataFrame) -> pd.DataFrame:
    if curated.empty:
        return curated.copy()
    if failure_v21_view.empty:
        data = curated.copy()
        data["old_verified_case_type"] = data.get("verified_case_type", "")
        data["verified_case_type_v2_1"] = data.get("verified_case_type", "")
        return data
    merged = curated.merge(
        failure_v21_view[
            [
                "case_id",
                "old_verified_case_type",
                "verified_case_type_v2_1",
                "event_date",
                "event_type",
                "label_change_reason",
                "confidence",
                "source_origin",
                "web_source_available",
                "local_event_verified",
            ]
        ].drop_duplicates(subset=["case_id"]),
        on="case_id",
        how="left",
    )
    merged["old_verified_case_type"] = merged["old_verified_case_type"].fillna(merged.get("verified_case_type", ""))
    merged["verified_case_type"] = merged["verified_case_type_v2_1"].fillna(merged.get("verified_case_type", ""))
    merged["case_type"] = merged["verified_case_type"]
    return merged


def _apply_failure_v21_labels_to_alignment(alignment_audit: pd.DataFrame, curated_failure_v21: pd.DataFrame) -> pd.DataFrame:
    if alignment_audit.empty:
        return alignment_audit.copy()
    label_map = curated_failure_v21.set_index("case_id")["verified_case_type_v2_1"].to_dict() if "verified_case_type_v2_1" in curated_failure_v21.columns else {}
    data = alignment_audit.copy()
    data["case_type"] = data["case_id"].map(label_map).fillna(data.get("case_type", ""))
    return data


def _build_lhb_v2_vs_v21_comparison(
    *,
    output_dir: str | Path,
    new_detail: pd.DataFrame,
    curated: pd.DataFrame,
    failure_v21_view: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["metric", "old_value", "v2_1_value", "delta", "interpretation"]
    out = Path(output_dir)
    old_detail_path = out / "lhb_case_event_detail.csv"
    old_detail = pd.read_csv(old_detail_path, low_memory=False) if old_detail_path.exists() else pd.DataFrame()

    old_curated = curated.copy()
    old_curated["old_verified_case_type"] = old_curated.get("verified_case_type", "")

    def _metric(frame: pd.DataFrame, label: str, field: str) -> float | int | None:
        if frame.empty:
            return None
        subset = frame[frame.get("verified_case_type", pd.Series(dtype=str)).fillna("").astype(str) == label]
        if field == "count":
            return int(len(subset))
        if subset.empty:
            return None
        if field == "lhb_after_3d_rate":
            return float(pd.to_numeric(subset["lhb_after_3d"], errors="coerce").fillna(False).astype(bool).mean())
        values = pd.to_numeric(subset[field], errors="coerce")
        return float(values.mean()) if values.notna().any() else None

    def _case_count(frame: pd.DataFrame, label_col: str, label: str) -> int:
        if frame.empty or label_col not in frame.columns:
            return 0
        subset = frame[frame[label_col].fillna("").astype(str) == label]
        return int(subset["case_id"].nunique()) if "case_id" in subset.columns else int(len(subset))

    metric_defs = [
        ("a_kill_failure_count", "a_kill_failure", "count", "A杀样本数变化"),
        ("failed_second_wave_count", "failed_second_wave", "count", "失败二波样本数变化"),
        ("high_open_low_close_failure_count", "high_open_low_close_failure", "count", "高开低走失败样本数变化"),
        ("a_kill_avg_lhb_net_buy", "a_kill_failure", "lhb_net_buy_amount_event", "A杀事件日净买额是否更负"),
        ("a_kill_avg_pump_risk", "a_kill_failure", "lhb_one_day_pump_risk", "A杀 pump risk 是否更高"),
        ("a_kill_avg_future_5d_return", "a_kill_failure", "future_5d_return", "A杀 5 日收益是否更差"),
        ("a_kill_avg_future_10d_return", "a_kill_failure", "future_10d_return", "A杀 10 日收益是否更差"),
        ("a_kill_avg_future_10d_max_drawdown", "a_kill_failure", "future_10d_max_drawdown", "A杀 10 日回撤是否更深"),
        ("failed_second_wave_avg_lhb_net_buy", "failed_second_wave", "lhb_net_buy_amount_event", "失败二波净买额"),
        ("failed_second_wave_after_3d_lhb_rate", "failed_second_wave", "lhb_after_3d_rate", "失败二波事件后 LHB 关注率"),
        ("failed_second_wave_avg_future_10d_return", "failed_second_wave", "future_10d_return", "失败二波 10 日收益"),
    ]
    rows = []
    for metric, label, field, interpretation in metric_defs:
        if field == "count":
            old_value = _case_count(old_curated, "old_verified_case_type", label)
            new_value = _case_count(failure_v21_view, "verified_case_type_v2_1", label)
        else:
            old_value = _metric(old_detail, label, field)
            new_value = _metric(new_detail, label, field)
        delta = (new_value - old_value) if old_value is not None and new_value is not None else None
        rows.append(
            {
                "metric": metric,
                "old_value": old_value,
                "v2_1_value": new_value,
                "delta": delta,
                "interpretation": interpretation,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _lhb_case_difference_markdown(
    *,
    case_type_summary: pd.DataFrame,
    event_window: pd.DataFrame,
    risk: pd.DataFrame,
    positive: pd.DataFrame,
    coverage: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# LHB Case/Event Difference Report v1",
            "",
            "## 1. 研究目标",
            "本轮只做案例级资金行为诊断，不接策略、不做回测。",
            "",
            "## 2. 数据来源与样本覆盖",
            _table_preview(coverage, rows=4),
            "",
            "## 3. 成功二波 vs 失败二波",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"].isin(["second_wave", "failed_second_wave"])], rows=16),
            "",
            "## 4. A杀失败样本",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"] == "a_kill_failure"], rows=12),
            "",
            "## 5. 其他失败类型",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"].isin(["failed_reversal", "high_open_low_close_failure", "one_day_pump"])], rows=12),
            "",
            "## 6. LHB 风险信号",
            _table_preview(risk, rows=12),
            "",
            "## 7. LHB 正向确认信号",
            _table_preview(positive, rows=12),
            "",
            "## 8. 对 Dragon Strategy 的启发",
            "LHB 当前更适合作为风险过滤和案例解释，不适合直接进入策略打分。",
            "",
            "## 9. 下一步建议",
            "继续补 failed_reversal / high_open_low_close_failure / one_day_pump 样本。",
            "",
            "### Event Window",
            _table_preview(event_window, rows=20),
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _lhb_after_failure_rule_v21_markdown(
    *,
    transition_matrix: pd.DataFrame,
    case_type_summary: pd.DataFrame,
    risk_cross: pd.DataFrame,
    comparison: pd.DataFrame,
    warnings: list[str],
) -> str:
    a_kill = case_type_summary[case_type_summary["verified_case_type"] == "a_kill_failure"] if not case_type_summary.empty else case_type_summary
    failed_wave = case_type_summary[case_type_summary["verified_case_type"] == "failed_second_wave"] if not case_type_summary.empty else case_type_summary
    hocl = case_type_summary[case_type_summary["verified_case_type"] == "high_open_low_close_failure"] if not case_type_summary.empty else case_type_summary
    sample_note = []
    if hocl.empty or int(pd.to_numeric(hocl["sample_count"], errors="coerce").fillna(0).sum()) < 3:
        sample_note.append("high_open_low_close_failure 样本仍偏少。")
    if case_type_summary[case_type_summary["verified_case_type"] == "failed_reversal"].empty:
        sample_note.append("failed_reversal 样本偏少。")
    if case_type_summary[case_type_summary["verified_case_type"] == "one_day_pump"].empty:
        sample_note.append("one_day_pump 样本偏少。")
    return "\n".join(
        [
            "# LHB Risk Diagnostics after Failure Rule v2.1",
            "",
            "## 1. 背景",
            "v2.1 收紧了 A杀定义，要求绑定破位上下文，避免深跌但无破位事件的样本被直接归入 A杀。",
            "",
            "## 2. 标签迁移结果",
            _table_preview(transition_matrix, rows=20),
            "",
            "## 3. A杀样本 LHB 特征",
            _table_preview(a_kill, rows=12),
            "",
            "## 4. 失败二波样本 LHB 特征",
            _table_preview(failed_wave, rows=16),
            "",
            "## 5. high_open_low_close_failure",
            _table_preview(hocl, rows=12),
            *(sample_note or [""]),
            "",
            "## 6. 成功二波对照",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"] == "second_wave"], rows=12),
            "",
            "## 7. v2 vs v2.1 结论变化",
            _table_preview(comparison, rows=20),
            "",
            "## 8. 下一步建议",
            "保留 v2.1 的 A杀定义；继续补 failed_reversal / one_day_pump 样本，暂时仍不接策略打分。",
            "",
            "### Risk Cross",
            _table_preview(risk_cross, rows=20),
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _standardize_lhb_risk_features(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        *detail.columns.tolist(),
        "lhb_negative_net_buy",
        "lhb_strong_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "lhb_high_concentration",
        "lhb_repeat_attention",
        "lhb_after_event_attention",
        "lhb_after_break_attention",
        "lhb_after_reversal_attention",
        "lhb_risk_score",
        "lhb_risk_level",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    net_buy = pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce")
    inst = pd.to_numeric(frame["institution_net_buy_event"], errors="coerce")
    pump = pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    concentration = pd.to_numeric(frame["top_seat_concentration_event"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    repeat_3d = pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce").fillna(0.0)
    repeat_5d = pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce").fillna(0.0)
    strong_negative_cutoff = net_buy.dropna().quantile(0.25) if net_buy.notna().any() else 0.0
    high_pump_cutoff = max(0.7, pump.quantile(0.75)) if not pump.empty else 0.7
    high_concentration_cutoff = max(0.5, concentration.quantile(0.75)) if not concentration.empty else 0.5

    frame["lhb_negative_net_buy"] = net_buy < 0
    frame["lhb_strong_negative_net_buy"] = net_buy <= strong_negative_cutoff
    frame["lhb_institution_selling"] = inst < 0
    frame["lhb_high_pump_risk"] = pump >= high_pump_cutoff
    frame["lhb_high_concentration"] = concentration >= high_concentration_cutoff
    frame["lhb_repeat_attention"] = (repeat_3d >= 2) | (repeat_5d >= 3)
    frame["lhb_after_event_attention"] = frame["lhb_after_3d"].fillna(False).astype(bool)
    frame["lhb_after_break_attention"] = frame["event_type"].fillna("").astype(str).eq("break_limit") & frame["lhb_after_event_attention"]
    frame["lhb_after_reversal_attention"] = frame["event_type"].fillna("").astype(str).eq("reversal") & frame["lhb_after_event_attention"]

    negative_net_buy_score = frame["lhb_negative_net_buy"].astype(float)
    institution_selling_score = frame["lhb_institution_selling"].astype(float)
    pump_risk_score = pump
    repeat_attention_score = frame["lhb_repeat_attention"].astype(float)
    concentration_score = concentration
    after_event_attention_score = frame["lhb_after_event_attention"].astype(float)
    frame["lhb_risk_score"] = (
        0.25 * negative_net_buy_score
        + 0.20 * institution_selling_score
        + 0.20 * pump_risk_score
        + 0.15 * repeat_attention_score
        + 0.10 * concentration_score
        + 0.10 * after_event_attention_score
    ).clip(0.0, 1.0)
    frame["lhb_risk_level"] = frame["lhb_risk_score"].map(_risk_level)
    return frame.reindex(columns=columns)


def _build_lhb_risk_score_bucket_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "bucket",
        "sample_count",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "win_rate_3d",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "a_kill_failure_count",
        "failed_second_wave_count",
        "second_wave_success_count",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    scores = pd.to_numeric(frame["lhb_risk_score"], errors="coerce").fillna(0.0)
    if scores.nunique() <= 1:
        frame["bucket"] = 1
    else:
        frame["bucket"] = pd.qcut(scores.rank(method="first"), q=min(10, len(frame)), labels=False, duplicates="drop") + 1
    rows = []
    for bucket, group in frame.groupby("bucket", dropna=False):
        rows.append(
            {
                "bucket": int(bucket),
                "sample_count": int(len(group)),
                **_future_stats(group),
                "a_kill_failure_count": int((group["verified_case_type"] == "a_kill_failure").sum()),
                "failed_second_wave_count": int((group["verified_case_type"] == "failed_second_wave").sum()),
                "second_wave_success_count": int(((group["verified_case_type"] == "second_wave") & (group["success_or_failure"] == "success")).sum()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("bucket").reset_index(drop=True)


def _build_lhb_risk_failure_type_cross(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "lhb_risk_level",
        "sample_count",
        "avg_lhb_risk_score",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_lhb_one_day_pump_risk",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for (case_type, success, level), group in detail.groupby(["verified_case_type", "success_or_failure", "lhb_risk_level"], dropna=False):
        rows.append(
            {
                "verified_case_type": case_type,
                "success_or_failure": success,
                "lhb_risk_level": level,
                "sample_count": int(len(group)),
                "avg_lhb_risk_score": pd.to_numeric(group["lhb_risk_score"], errors="coerce").mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy_event"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["verified_case_type", "success_or_failure", "lhb_risk_level"]).reset_index(drop=True)


def _build_lhb_dragon_risk_cross(detail: pd.DataFrame, optional_diagnostics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = [
        "lhb_risk_level",
        "dragon_risk_level",
        "entry_window",
        "entry_window_v2",
        "verified_case_type",
        "success_or_failure",
        "sample_count",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty or not optional_diagnostics:
        return pd.DataFrame(columns=columns)
    enriched = detail.copy()
    enriched["dragon_risk_level"] = ""
    enriched["entry_window"] = ""
    enriched["entry_window_v2"] = ""
    for _, diagnostics in optional_diagnostics.items():
        if diagnostics.empty:
            continue
        diag = diagnostics.copy()
        date_col = "trade_date" if "trade_date" in diag.columns else ("event_date" if "event_date" in diag.columns else None)
        code_col = "ts_code" if "ts_code" in diag.columns else ("asset_id" if "asset_id" in diag.columns else None)
        if not date_col or not code_col:
            continue
        diag[date_col] = pd.to_datetime(diag[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        diag[code_col] = diag[code_col].fillna("").astype(str).str.upper()
        merge_cols = [code_col, date_col]
        use_cols = merge_cols + [col for col in ["dragon_risk_score", "entry_window", "entry_window_v2"] if col in diag.columns]
        merged = enriched.merge(
            diag[use_cols].drop_duplicates(subset=merge_cols),
            left_on=["ts_code", "event_date"],
            right_on=merge_cols,
            how="left",
            suffixes=("", "_diag"),
        )
        if "dragon_risk_score" in merged.columns:
            mask = enriched["dragon_risk_level"].eq("") & merged["dragon_risk_score"].notna()
            enriched.loc[mask, "dragon_risk_level"] = merged.loc[mask, "dragon_risk_score"].map(_risk_level)
        for col in ["entry_window", "entry_window_v2"]:
            diag_col = f"{col}_diag" if f"{col}_diag" in merged.columns else col
            if diag_col in merged.columns:
                mask = enriched[col].eq("") & merged[diag_col].notna()
                enriched.loc[mask, col] = merged.loc[mask, diag_col].astype(str)
    enriched = enriched[enriched["dragon_risk_level"].astype(str) != ""]
    if enriched.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for keys, group in enriched.groupby(["lhb_risk_level", "dragon_risk_level", "entry_window", "entry_window_v2", "verified_case_type", "success_or_failure"], dropna=False):
        lhb_level, dragon_level, entry_window, entry_window_v2, case_type, success = keys
        rows.append(
            {
                "lhb_risk_level": lhb_level,
                "dragon_risk_level": dragon_level,
                "entry_window": entry_window,
                "entry_window_v2": entry_window_v2,
                "verified_case_type": case_type,
                "success_or_failure": success,
                "sample_count": int(len(group)),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_lhb_coverage_gap_recommendations(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "has_lhb",
        "missing_reason",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "notes",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    rows = []
    for record in detail.fillna("").to_dict("records"):
        has_lhb = bool(record.get("lhb_on_event_date") or record.get("lhb_before_3d") or record.get("lhb_after_3d"))
        case_type = str(record.get("verified_case_type") or record.get("case_type") or "")
        event_date = str(record.get("event_date") or "")
        if not event_date:
            continue
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": record.get("success_or_failure"),
                "event_date": event_date,
                "has_lhb": has_lhb,
                "missing_reason": "" if has_lhb else "no_lhb_within_event_window",
                "priority_for_lhb_backfill": priority_map.get(case_type, 9),
                "suggested_lhb_query_start_date": _shift_date(event_date, -5),
                "suggested_lhb_query_end_date": _shift_date(event_date, 5),
                "notes": "already_covered" if has_lhb else "expand AkShare/Tushare LHB range around this event",
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["has_lhb", "priority_for_lhb_backfill", "case_year"]).reset_index(drop=True)


def _build_lhb_coverage_expansion_plan(coverage_gaps: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "plan_id",
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "query_window_days_before",
        "query_window_days_after",
        "reason",
        "expected_value",
        "status",
        "notes",
    ]
    if coverage_gaps.empty:
        return pd.DataFrame(columns=columns)
    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    frame = coverage_gaps.copy()
    if "has_lhb" in frame.columns:
        has_lhb = frame["has_lhb"].map(_coerce_bool)
        frame = frame[~has_lhb].copy()
    rows = []
    for record in frame.fillna("").to_dict("records"):
        case_type = str(record.get("verified_case_type") or "")
        success = str(record.get("success_or_failure") or "")
        if case_type == "second_wave" and success != "success":
            priority = 8
        else:
            priority = priority_map.get(case_type, 9)
        event_date = _format_date(record.get("event_date"))
        if not event_date:
            continue
        after_days = 10 if case_type in {"a_kill_failure", "failed_second_wave"} else 5
        before_days = 5
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": str(record.get("ts_code") or "").upper(),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": success,
                "event_date": event_date,
                "priority_for_lhb_backfill": priority,
                "suggested_lhb_query_start_date": _shift_date(event_date, -before_days),
                "suggested_lhb_query_end_date": _shift_date(event_date, after_days),
                "query_window_days_before": before_days,
                "query_window_days_after": after_days,
                "reason": _lhb_expansion_reason(case_type, success),
                "expected_value": _lhb_expansion_expected_value(case_type, success),
                "status": "pending",
                "notes": record.get("notes") or "LHB coverage gap; planned for small-batch AkShare/Tushare backfill",
            }
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .sort_values(["priority_for_lhb_backfill", "case_year", "event_date", "ts_code"])
        .reset_index(drop=True)
        .assign(plan_id=lambda df: [f"lhb_plan_{idx:04d}" for idx in range(1, len(df) + 1)])
        .reindex(columns=columns)
    )


def _build_lhb_coverage_expansion_summary(coverage_gaps: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "case_year",
        "priority_for_lhb_backfill",
        "case_count",
        "event_count",
        "avg_query_window_days",
        "expected_lhb_rows",
        "current_lhb_matched_count",
        "missing_lhb_count",
    ]
    if plan.empty:
        return pd.DataFrame(columns=columns)
    frame = plan.copy()
    frame["query_window_days"] = pd.to_numeric(frame["query_window_days_before"], errors="coerce").fillna(0) + pd.to_numeric(frame["query_window_days_after"], errors="coerce").fillna(0) + 1
    matched_lookup = pd.DataFrame()
    if not coverage_gaps.empty and {"verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill", "has_lhb"}.issubset(coverage_gaps.columns):
        matched_lookup = coverage_gaps.copy()
        matched_lookup["has_lhb"] = matched_lookup["has_lhb"].map(_coerce_bool)
        matched_lookup["priority_for_lhb_backfill"] = matched_lookup.apply(
            lambda row: _lhb_case_priority(row.get("verified_case_type"), row.get("success_or_failure")),
            axis=1,
        )
    rows = []
    keys = ["verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill"]
    for key_values, group in frame.groupby(keys, dropna=False):
        key_dict = dict(zip(keys, key_values))
        current_matched = 0
        if not matched_lookup.empty:
            mask = pd.Series(True, index=matched_lookup.index)
            for col, value in key_dict.items():
                mask &= matched_lookup[col].astype(str).eq(str(value))
            current_matched = int(matched_lookup.loc[mask, "has_lhb"].sum())
        rows.append(
            {
                **key_dict,
                "case_count": int(group["case_id"].nunique()),
                "event_count": int(len(group)),
                "avg_query_window_days": float(group["query_window_days"].mean()),
                "expected_lhb_rows": int(group["query_window_days"].sum()),
                "current_lhb_matched_count": current_matched,
                "missing_lhb_count": int(len(group)),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["priority_for_lhb_backfill", "case_year"]).reset_index(drop=True)


def _lhb_coverage_expansion_commands(plan: pd.DataFrame) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# LHB coverage expansion command suggestions.",
        "# Commands are intentionally commented out: review the windows before running.",
        "# TODO: do not run full-market LHB backfill from this script.",
        "",
        "# 1. Small sample: Top 5 priority cases, event window around +/-5 trading days.",
    ]
    lines.extend(_commented_lhb_import_commands(plan.head(5)))
    high = plan[plan["verified_case_type"].isin(["a_kill_failure", "failed_second_wave"])] if not plan.empty else plan
    lines.extend(["", "# 2. Medium sample: all a_kill_failure / failed_second_wave cases, event window +5 to +10 days."])
    lines.extend(_commented_lhb_import_commands(high))
    high_priority = plan[pd.to_numeric(plan["priority_for_lhb_backfill"], errors="coerce").fillna(99) <= 5] if not plan.empty else plan
    lines.extend(["", "# 3. Extended sample: all high-priority gap cases."])
    lines.extend(_commented_lhb_import_commands(high_priority))
    lines.append("")
    return "\n".join(lines)


def _commented_lhb_import_commands(plan: pd.DataFrame) -> list[str]:
    if plan.empty:
        return ["# No matching cases in this layer."]
    start = pd.to_datetime(plan["suggested_lhb_query_start_date"], errors="coerce").min()
    end = pd.to_datetime(plan["suggested_lhb_query_end_date"], errors="coerce").max()
    codes = ",".join(sorted({str(code).upper() for code in plan["ts_code"].dropna() if str(code).strip()}))
    if pd.isna(start) or pd.isna(end) or not codes:
        return ["# Missing date/code fields; inspect lhb_coverage_expansion_plan_2024_2026.csv first."]
    return [
        "# stock-research lhb-sample-import \\",
        f"#   --provider akshare --start-date {start.strftime('%Y-%m-%d')} --end-date {end.strftime('%Y-%m-%d')} \\",
        f"#   --ts-codes {codes} \\",
        "#   --output-dir outputs/research",
    ]


def _build_failure_event_rule_refinement_audit(curated: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "current_verified_case_type",
        "event_date",
        "pre_3d_return",
        "pre_5d_return",
        "post_1d_return",
        "post_3d_return",
        "post_5d_return",
        "post_10d_return",
        "post_5d_max_drawdown",
        "post_10d_max_drawdown",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "close_position_in_day",
        "is_limit_up_day",
        "is_break_limit_event",
        "is_reversal_event",
        "is_second_wave_event",
        "is_a_kill_event",
        "suggested_refined_case_type",
        "refinement_reason",
        "confidence",
    ]
    if curated.empty or snapshot.empty:
        return pd.DataFrame(columns=columns)
    focus_types = {"failed_reversal", "high_open_low_close_failure", "one_day_pump", "failed_second_wave", "a_kill_failure"}
    cases = curated.copy()
    cases["case_id"] = cases["case_id"].astype(str)
    current_type_col = "verified_case_type" if "verified_case_type" in cases.columns else "case_type"
    events = snapshot.copy()
    events["case_id"] = events["case_id"].astype(str)
    if "relative_day" in events.columns:
        day0 = events[pd.to_numeric(events["relative_day"], errors="coerce").fillna(999).eq(0)].copy()
        if not day0.empty:
            events = day0
    merged = events.merge(
        cases[["case_id", current_type_col]].rename(columns={current_type_col: "current_verified_case_type"}),
        on="case_id",
        how="left",
    )
    merged["current_verified_case_type"] = merged["current_verified_case_type"].fillna("")
    merged = merged[merged["current_verified_case_type"].isin(focus_types) | merged["is_a_kill_event"].map(_coerce_bool) | merged["is_reversal_event"].map(_coerce_bool) | merged["is_second_wave_event"].map(_coerce_bool)]
    rows = []
    for record in merged.fillna("").to_dict("records"):
        suggested, reason, confidence = _suggest_failure_case_type(record)
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": str(record.get("ts_code") or "").upper(),
                "stock_name": record.get("stock_name"),
                "current_verified_case_type": record.get("current_verified_case_type"),
                "event_date": _format_date(record.get("event_date")) or _format_date(record.get("trade_date")),
                "pre_3d_return": _num(record.get("pre_3d_return")),
                "pre_5d_return": _num(record.get("pre_5d_return")),
                "post_1d_return": _num(record.get("future_1d_return")),
                "post_3d_return": _num(record.get("future_3d_return")),
                "post_5d_return": _num(record.get("future_5d_return")),
                "post_10d_return": _num(record.get("future_10d_return")),
                "post_5d_max_drawdown": _num(record.get("future_5d_max_drawdown")),
                "post_10d_max_drawdown": _num(record.get("future_10d_max_drawdown")),
                "amount_vs_20d": _num(record.get("amount_vs_20d")),
                "high_to_close_drawdown": _num(record.get("high_to_close_drawdown")),
                "close_position_in_day": _num(record.get("close_position_in_day")),
                "is_limit_up_day": _coerce_bool(record.get("is_limit_up_day")),
                "is_break_limit_event": _coerce_bool(record.get("is_break_limit_event")),
                "is_reversal_event": _coerce_bool(record.get("is_reversal_event")),
                "is_second_wave_event": _coerce_bool(record.get("is_second_wave_event")),
                "is_a_kill_event": _coerce_bool(record.get("is_a_kill_event")),
                "suggested_refined_case_type": suggested,
                "refinement_reason": reason,
                "confidence": confidence,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_failure_event_rule_refinement_suggestions(curated: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    columns = ["case_type", "current_sample_count", "suggested_rule", "required_fields", "expected_improvement", "risk_of_false_positive", "notes"]
    current = curated["verified_case_type"].value_counts().to_dict() if "verified_case_type" in curated.columns else {}
    suggestions = [
        {
            "case_type": "failed_reversal",
            "suggested_rule": "断板后 1-5 日出现反包/强修复，但 1-3 日内无法延续，跌破反包日低点或 post_3d/post_5d 转负。",
            "required_fields": "is_reversal_event, post_3d_return, post_5d_return, high_to_close_drawdown, close_position_in_day",
            "expected_improvement": "把成功反包与假反包拆开，补足 failed_reversal 样本。",
            "risk_of_false_positive": "强趋势里的正常分歧可能被误判为失败反包。",
            "notes": "需要结合后续是否再创新高做二次校验。",
        },
        {
            "case_type": "high_open_low_close_failure",
            "suggested_rule": "事件日冲高回落明显，close_position_in_day 偏低且 high_to_close_drawdown 较高，后续 3/5 日继续走弱。",
            "required_fields": "high_to_close_drawdown, close_position_in_day, post_3d_return, post_5d_return, amount_vs_20d",
            "expected_improvement": "识别高位爆量分歧、准天地板和大面样本。",
            "risk_of_false_positive": "低位洗盘或指数拖累的长上影可能被误判。",
            "notes": "与 one_day_pump 的边界在于前期是否已有高度/人气确认。",
        },
        {
            "case_type": "one_day_pump",
            "suggested_rule": "单日大涨或涨停伴随 amount_vs_20d 放大，但无连板/反包/二波，次日或 3 日内明显回落。",
            "required_fields": "is_limit_up_day, limit_up_count_before_event, amount_vs_20d, post_1d_return, post_3d_return",
            "expected_improvement": "把低持续性脉冲从弱转强/跟风里拆出来。",
            "risk_of_false_positive": "首板试错后再次走强的样本可能被提前归为一日游。",
            "notes": "需要排除后续二波或连续趋势延续。",
        },
        {
            "case_type": "failed_second_wave_vs_a_kill_failure",
            "suggested_rule": "failed_second_wave 需要先有二波尝试/突破失败；a_kill_failure 更强调高人气确认后破位且无有效反包。",
            "required_fields": "is_second_wave_event, is_a_kill_event, post_5d_return, post_10d_return, post_10d_max_drawdown",
            "expected_improvement": "减少二波失败与纯 A 杀互相污染。",
            "risk_of_false_positive": "先失败后二次修复的 mixed 案例需要人工备注。",
            "notes": "若后续再突破前高，应改为 mixed 或 failed_then_recovered。",
        },
        {
            "case_type": "high_open_low_close_failure_vs_one_day_pump",
            "suggested_rule": "HOCL 侧重已有高度后的高位冲高回落；one_day_pump 侧重低持续性的单日脉冲。",
            "required_fields": "pre_5d_return, limit_up_count_before_event, high_to_close_drawdown, post_3d_return",
            "expected_improvement": "让失败类型更贴近市场语言。",
            "risk_of_false_positive": "缺少分钟线时无法确认早盘高开/冲高路径。",
            "notes": "后续 5min 承接特征可显著提高边界质量。",
        },
    ]
    for item in suggestions:
        item["current_sample_count"] = int(current.get(item["case_type"], 0))
    return pd.DataFrame(suggestions).reindex(columns=columns)


def _suggest_failure_case_type(record: dict[str, Any]) -> tuple[str, str, float]:
    current = str(record.get("current_verified_case_type") or "")
    post_3d = _num(record.get("future_3d_return")) or 0.0
    post_5d = _num(record.get("future_5d_return")) or 0.0
    post_10d = _num(record.get("future_10d_return")) or 0.0
    dd_10d = _num(record.get("future_10d_max_drawdown")) or 0.0
    high_to_close = _num(record.get("high_to_close_drawdown")) or 0.0
    close_pos = _num(record.get("close_position_in_day"))
    limit_count = _num(record.get("limit_up_count_before_event")) or 0.0
    if _coerce_bool(record.get("is_a_kill_event")) or post_10d <= -0.15 or dd_10d <= -0.18:
        return "a_kill_failure", "破位后 10 日收益/回撤显示 A 杀风险，且无有效修复确认。", 0.85
    if _coerce_bool(record.get("is_reversal_event")) and (post_3d < 0 or post_5d <= -0.05):
        return "failed_reversal", "反包尝试后 3-5 日无法延续，符合失败反包。", 0.80
    if _coerce_bool(record.get("is_second_wave_event")) and (post_5d <= -0.08 or dd_10d <= -0.12):
        return "failed_second_wave", "二波尝试后收益转弱且回撤扩大。", 0.78
    if high_to_close >= 0.08 and (close_pos is None or close_pos <= 0.35) and post_3d < 0:
        return "high_open_low_close_failure", "事件日冲高回落且收盘位置偏低，后续走弱。", 0.76
    if _coerce_bool(record.get("is_limit_up_day")) and limit_count <= 1 and post_3d <= -0.06:
        return "one_day_pump", "单日涨停/大涨后 3 日回落且缺少连板延续。", 0.72
    return current or "unknown", "现有日线字段不足以重分类，保留原标签。", 0.50


def _lhb_coverage_failure_plan_markdown(
    *,
    plan: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    warnings: list[str],
) -> str:
    high_priority = int((pd.to_numeric(plan.get("priority_for_lhb_backfill", pd.Series(dtype=float)), errors="coerce") <= 3).sum()) if not plan.empty else 0
    return "\n".join(
        [
            "# LHB Coverage Expansion & Failure Rule Refinement Plan v1",
            "",
            "## 1. 背景",
            "LHB 风险诊断已能解释部分 A杀、失败二波和高位分歧，但覆盖和失败事件标签仍是短板。本轮只生成补数计划和规则审计，不接策略打分、不做组合回测、不接实盘。",
            "",
            "## 2. LHB 覆盖缺口",
            f"覆盖扩展计划共 {len(plan)} 条，其中高优先级（priority <= 3）{high_priority} 条。",
            _table_preview(summary, rows=20),
            "",
            "## 3. 覆盖扩展计划",
            "优先级为 a_kill_failure、failed_second_wave、failed_reversal、high_open_low_close_failure、one_day_pump、success second_wave 代表案例。a_kill_failure / failed_second_wave 的事件后窗口扩到 10 日。",
            _table_preview(plan, rows=20),
            "",
            "## 4. AkShare 小批量补数建议",
            "先跑 Top 5 小样本，再跑 a_kill_failure / failed_second_wave 中样本，最后扩展到全部高优先级缺口。脚本只输出注释命令，不自动执行全量补数。",
            "",
            "## 5. 失败事件规则问题",
            "failed_reversal、high_open_low_close_failure、one_day_pump 样本仍偏少，且仅靠日线会混淆假反包、高位冲高回落和单日脉冲。",
            _table_preview(audit, rows=20),
            "",
            "## 6. 规则修正建议",
            _table_preview(suggestions, rows=10),
            "",
            "## 7. 下一步",
            "建议先做 AkShare LHB 高优先级窗口小批量补数，再实现失败事件规则 v2，随后重跑 LHB risk diagnostics；最后再考虑 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _lhb_case_priority(case_type: Any, success: Any) -> int:
    text = str(case_type or "")
    if text == "a_kill_failure":
        return 1
    if text == "failed_second_wave":
        return 2
    if text == "failed_reversal":
        return 3
    if text == "high_open_low_close_failure":
        return 4
    if text == "one_day_pump":
        return 5
    if text == "second_wave" and str(success or "") == "success":
        return 6
    return 9


def _lhb_expansion_reason(case_type: str, success: str) -> str:
    if case_type == "a_kill_failure":
        return "A杀风险样本需要验证负净买、重复上榜和 pump risk。"
    if case_type == "failed_second_wave":
        return "失败二波需要观察事件后分歧关注和资金撤退。"
    if case_type == "failed_reversal":
        return "失败反包样本稀缺，优先补 LHB 证据。"
    if case_type == "high_open_low_close_failure":
        return "高开低走/冲高回落需要资金分歧证据。"
    if case_type == "one_day_pump":
        return "一日游需要验证事件后资金承接缺失。"
    if case_type == "second_wave" and success == "success":
        return "成功二波作为对照组补充覆盖。"
    return "低覆盖案例补充 LHB 对齐。"


def _lhb_expansion_expected_value(case_type: str, success: str) -> str:
    if case_type in {"a_kill_failure", "failed_second_wave", "failed_reversal"}:
        return "high: improve failure-risk diagnostics"
    if case_type in {"high_open_low_close_failure", "one_day_pump"}:
        return "medium_high: refine sparse failure labels"
    if case_type == "second_wave" and success == "success":
        return "medium: success contrast sample"
    return "low: coverage completeness"


def _future_stats(group: pd.DataFrame) -> dict[str, Any]:
    future_3d = pd.to_numeric(group["future_3d_return"], errors="coerce")
    future_5d = pd.to_numeric(group["future_5d_return"], errors="coerce")
    future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce")
    return {
        "avg_future_3d_return": future_3d.mean(),
        "avg_future_5d_return": future_5d.mean(),
        "avg_future_10d_return": future_10d.mean(),
        "win_rate_3d": (future_3d > 0).mean() if future_3d.notna().any() else None,
        "win_rate_5d": (future_5d > 0).mean() if future_5d.notna().any() else None,
        "win_rate_10d": (future_10d > 0).mean() if future_10d.notna().any() else None,
        "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
        "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
    }


def _risk_level(value: Any) -> str:
    score = float(value) if value is not None and not pd.isna(value) else 0.0
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "mid"
    return "low"


def _lhb_risk_feature_markdown(
    *,
    risk_detail: pd.DataFrame,
    bucket: pd.DataFrame,
    cross: pd.DataFrame,
    dragon_cross: pd.DataFrame,
    gaps: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# LHB Risk Feature Diagnostics v1",
            "",
            "## 1. 研究目标",
            "本轮只做 LHB 风险特征标准化和案例诊断，不接策略打分。",
            "",
            "## 2. LHB 风险特征定义",
            "lhb_risk_score = 25% negative_net_buy + 20% institution_selling + 20% pump_risk + 15% repeat_attention + 10% concentration + 10% after_event_attention。future return 不参与分数。",
            "",
            "## 3. risk_score 分桶结果",
            _table_preview(bucket, rows=12),
            "",
            "## 4. 失败类型交叉分析",
            _table_preview(cross, rows=20),
            "",
            "## 5. 与 Dragon 风险标签交叉",
            _table_preview(dragon_cross, rows=20),
            "",
            "## 6. 覆盖缺口",
            _table_preview(gaps, rows=20),
            "",
            "## 7. 当前结论",
            f"标准化明细 {len(risk_detail)} 行。LHB 当前更适合作为风险因子候选，不适合作为买点确认。",
            "",
            "## 8. 下一步建议",
            "继续扩大 LHB 覆盖，修 failed_reversal / high_open_low_close_failure / one_day_pump 事件识别规则，后续再设计 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _shift_date(value: str, days: int) -> str:
    return (pd.Timestamp(value) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def _format_date(value: Any) -> str:
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return ""
    return date.strftime("%Y-%m-%d")


def _num(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def _coerce_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}
