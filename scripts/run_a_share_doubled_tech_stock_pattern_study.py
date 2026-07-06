#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "a_share_doubled_tech_stock_pattern_study_v1"
INPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1"
INPUT_DOUBLED_TECH = INPUT_DIR / "doubled_tech_stocks.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_pattern_study_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
REQUIRED_CASES = [
    "胜宏科技",
    "中际旭创",
    "新易盛",
    "天孚通信",
    "寒武纪",
    "源杰科技",
    "北方华创",
    "中微公司",
    "华海清科",
    "安集科技",
    "长川科技",
    "中科飞测",
]


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_stock_code(value: Any) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _render_pdf(markdown_text: str, path: Path) -> tuple[str, str]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        path.write_text(f"PDF renderer unavailable: {exc}\n", encoding="utf-8")
        return "failed", str(exc)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        x = 40
        y = height - 42
        pdf.setFont("Helvetica", 8)
        for raw_line in markdown_text.splitlines():
            line = raw_line.encode("latin-1", "replace").decode("latin-1")
            while len(line) > 118:
                pdf.drawString(x, y, line[:118])
                line = line[118:]
                y -= 10
                if y < 38:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 8)
                    y = height - 42
            pdf.drawString(x, y, line)
            y -= 10
            if y < 38:
                pdf.showPage()
                pdf.setFont("Helvetica", 8)
                y = height - 42
        pdf.save()
        return "generated", ""
    except Exception as exc:  # pragma: no cover
        return "failed", str(exc)


def _load_input() -> pd.DataFrame:
    frame = pd.read_csv(INPUT_DOUBLED_TECH, dtype={"stock_code": str})
    frame["stock_code"] = frame["stock_code"].map(_normalize_stock_code)
    if len(frame) != 596:
        raise ValueError(f"Expected 596 doubled tech input rows, found {len(frame)}. Re-run a_share_doubled_tech_stocks_since_20250101_v1 first.")
    return frame


def _stock_code_to_asset_ids(codes: list[str], service: str) -> dict[str, str]:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT symbol AS stock_code, asset_id
            FROM core.asset_master
            WHERE symbol = ANY(%s)
            """,
            [codes],
        )
    return {_normalize_stock_code(row["stock_code"]): row["asset_id"] for row in rows}


def _load_bars(asset_ids: list[str], service: str) -> pd.DataFrame:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id, trade_date, open::float, high::float, low::float, close::float,
                   volume::float, amount::float, turnover_rate::float, pct_chg::float
            FROM market_daily_bar
            WHERE adjust_type = 'qfq'
              AND trade_date >= DATE '2025-01-01'
              AND asset_id = ANY(%s)
            ORDER BY asset_id, trade_date
            """,
            [asset_ids],
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "trade_date", "close"])
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for column in ["open", "high", "low", "close", "volume", "amount", "turnover_rate", "pct_chg"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _load_finance(asset_ids: list[str], service: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with connect(service) as conn:
        income = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, report_period, report_type, announcement_date,
                       revenue::float, net_profit::float, np_parent::float
                FROM finance.income_statement
                WHERE asset_id = ANY(%s)
                  AND report_period >= DATE '2023-01-01'
                ORDER BY asset_id, report_period
                """,
                [asset_ids],
            )
        )
        cash = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, report_period, announcement_date,
                       net_operate_cash_flow::float, capex::float, free_cash_flow::float
                FROM finance.cash_flow
                WHERE asset_id = ANY(%s)
                  AND report_period >= DATE '2023-01-01'
                ORDER BY asset_id, report_period
                """,
                [asset_ids],
            )
        )
        balance = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, report_period, announcement_date,
                       total_assets::float, total_liabilities::float, total_equity::float
                FROM finance.balance_sheet
                WHERE asset_id = ANY(%s)
                  AND report_period >= DATE '2023-01-01'
                ORDER BY asset_id, report_period
                """,
                [asset_ids],
            )
        )
    for frame in [income, cash, balance]:
        if not frame.empty:
            frame["report_period"] = pd.to_datetime(frame["report_period"])
            frame["announcement_date"] = pd.to_datetime(frame["announcement_date"], errors="coerce")
    return income, cash, balance


def _load_events(asset_ids: list[str], service: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with connect(service) as conn:
        news = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT m.asset_id, m.ts_code, m.stock_name, m.theme_name, m.trade_date,
                       s.source_event_id, s.source_name, s.source_channel, s.title, s.url, s.published_at
                FROM research.news_event_mention m
                JOIN research.news_event_source s ON s.source_event_id = m.source_event_id
                WHERE m.asset_id = ANY(%s)
                  AND m.trade_date >= DATE '2024-10-01'
                ORDER BY m.asset_id, m.trade_date
                """,
                [asset_ids],
            )
        )
        reports = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, ts_code, stock_name, industry_name, report_id, report_date,
                       rating, rating_change, company_view, industry_view, risk_summary
                FROM research.stock_report_event
                WHERE asset_id = ANY(%s)
                  AND report_date >= DATE '2024-10-01'
                ORDER BY asset_id, report_date
                """,
                [asset_ids],
            )
        )
        report_features = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT trade_date, asset_id, report_count_30d, report_count_90d,
                       positive_rating_count, rating_upgrade_count, broker_coverage_count,
                       research_support_score
                FROM research.stock_report_feature_daily
                WHERE asset_id = ANY(%s)
                  AND trade_date >= DATE '2025-01-01'
                ORDER BY asset_id, trade_date
                """,
                [asset_ids],
            )
        )
    for frame, date_cols in [
        (news, ["trade_date", "published_at"]),
        (reports, ["report_date"]),
        (report_features, ["trade_date"]),
    ]:
        for col in date_cols:
            if not frame.empty and col in frame:
                frame[col] = pd.to_datetime(frame[col], errors="coerce")
    return news, reports, report_features


def _strict_theme(row: pd.Series) -> str:
    text = " ".join(
        [
            _clean(row.get("stock_name")),
            _clean(row.get("industry")),
            _clean(row.get("concept_tags")),
            _clean(row.get("tech_theme")),
            _clean(row.get("hard_tech_relevance")),
        ]
    )
    if any(k in text for k in ["中际旭创", "新易盛", "天孚通信", "源杰科技", "联特科技", "光通信", "光模块", "光芯片", "CPO"]):
        return "optical module / CPO / optical communication"
    if any(k in text for k in ["胜宏科技", "沪电股份", "生益电子", "生益科技", "PCB", "印制电路", "高频", "高速"]):
        return "AI PCB / high-speed board / AI server component"
    if any(k in text for k in ["寒武纪", "AI芯片", "国产算力", "GPU", "算力"]):
        return "AI chip / 国产算力"
    if any(k in text for k in ["江波龙", "佰维存储", "德明利", "存储", "memory"]):
        return "memory / storage"
    if any(k in text for k in ["北方华创", "中微公司", "华海清科", "长川科技", "中科飞测", "精测电子", "半导体设备", "检测", "量测", "专用设备"]):
        if any(k in text for k in ["长川科技", "中科飞测", "精测电子", "检测", "量测"]):
            return "semiconductor testing / advanced packaging"
        return "semiconductor equipment"
    if any(k in text for k in ["安集科技", "光刻胶", "CMP", "电子特气", "靶材", "半导体材料", "电子专用材料"]):
        return "semiconductor materials"
    if any(k in text for k in ["机器人", "伺服", "减速器", "传感器"]):
        return "robotics / humanoid robot chain"
    if any(k in text for k in ["EDA", "工业软件", "仿真", "软件"]):
        return "industrial software / EDA / simulation"
    if any(k in text for k in ["电网", "电力设备", "电力电子", "电气"]):
        return "power electronics / grid equipment"
    if any(k in text for k in ["低空", "卫星", "军工", "航空", "航天"]):
        return "low-altitude economy / satellite / defense electronics"
    if any(k in text for k in ["消费电子", "端侧", "AI眼镜"]):
        return "consumer electronics / edge AI"
    if any(k in text for k in ["仪器", "装备", "新材料", "高端"]):
        return "high-end equipment / instrumentation"
    if any(k in text for k in ["electronic_component", "其他战略性关键环节", "电子设备"]):
        return "broad tech application"
    return "concept-only or weak-tech"


def _pct_return(series: pd.Series, days: int) -> float | None:
    if len(series) < days + 1:
        return None
    first = series.iloc[-days - 1]
    last = series.iloc[-1]
    if not first or pd.isna(first) or pd.isna(last):
        return None
    return float(last / first - 1.0)


def _slope(series: pd.Series) -> float | None:
    clean = series.dropna()
    if len(clean) < 3:
        return None
    return float((clean.iloc[-1] / clean.iloc[0] - 1.0) / max(len(clean) - 1, 1))


def _max_drawdown(close: pd.Series) -> float | None:
    if close.empty:
        return None
    running_max = close.cummax()
    drawdown = close / running_max - 1.0
    return float(drawdown.min())


def _first_crossing(frame: pd.DataFrame, start_close: float, threshold: float) -> tuple[str, int] | tuple[None, None]:
    hit = frame[frame["close"] / start_close - 1.0 >= threshold]
    if hit.empty:
        return None, None
    index = int(hit.index[0])
    return hit.iloc[0]["trade_date"].strftime("%Y-%m-%d"), index + 1


def _breakout_type(pre: pd.DataFrame, volume_ratio: float | None, distance_to_high: float | None, limit_up_days: int) -> str:
    if limit_up_days >= 2:
        return "limit_up_cluster"
    if distance_to_high is not None and distance_to_high >= -0.02:
        return "new_high_breakout"
    ret120 = _pct_return(pre["close"], min(120, max(len(pre) - 1, 1)))
    if ret120 is not None and ret120 < 0.2 and volume_ratio is not None and volume_ratio >= 1.5:
        return "low_base_breakout"
    if volume_ratio is not None and volume_ratio >= 2.0:
        return "gap_up_catalyst"
    if ret120 is not None and ret120 >= 0.5:
        return "trend_continuation"
    return "unknown"


def _pattern_archetype(row: pd.Series) -> str:
    if bool(row.get("is_ipo_after_20250101")):
        return "IPO_or_new_stock_repricing"
    theme = _clean(row.get("strict_theme"))
    breakout = _clean(row.get("breakout_type"))
    if theme in {"optical module / CPO / optical communication", "AI PCB / high-speed board / AI server component", "AI chip / 国产算力"}:
        return "AI_theme_revaluation"
    if theme in {"semiconductor equipment", "semiconductor materials", "semiconductor testing / advanced packaging", "memory / storage"}:
        return "domestic_substitution_revaluation"
    if row.get("number_of_limit_up_days", 0) >= 5:
        return "limit_up_sentiment_wave"
    if breakout == "low_base_breakout":
        return "bottom_reversal_with_volume"
    if breakout == "new_high_breakout":
        return "new_high_trend_acceleration"
    if row.get("return_since_20250101", 0) >= 4 and theme == "broad tech application":
        return "small_cap_concept_squeeze"
    return "unclear_or_mixed"


def _event_type_from_text(text: str) -> str:
    lowered = text.lower()
    if any(k in text for k in ["业绩", "利润", "营收", "增长", "预告"]):
        return "earnings"
    if any(k in text for k in ["订单", "合同", "中标", "客户"]):
        return "order"
    if any(k in text for k in ["DeepSeek", "AI", "算力", "CPO", "光模块"]):
        return "AI theme"
    if any(k in text for k in ["政策", "国产替代", "自主可控", "信创"]):
        return "policy"
    if any(k in text for k in ["产品", "发布", "认证", "验证"]):
        return "product launch"
    if any(k in text for k in ["涨价", "价格"]):
        return "price increase"
    if "overseas" in lowered or "英伟达" in text or "海外" in text:
        return "overseas supply chain"
    return "unknown"


def _nearest_events(asset_id: str, stock_name: str, milestone_dates: list[str], news: pd.DataFrame, reports: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, milestone in milestone_dates:
        if not milestone:
            continue
        center = pd.Timestamp(milestone)
        window_start = center - pd.Timedelta(days=30)
        window_end = center + pd.Timedelta(days=10)
        stock_news = news[
            (news["asset_id"] == asset_id)
            & (news["trade_date"] >= window_start)
            & (news["trade_date"] <= window_end)
        ].head(2)
        stock_reports = reports[
            (reports["asset_id"] == asset_id)
            & (reports["report_date"] >= window_start)
            & (reports["report_date"] <= window_end)
        ].head(2)
        for _, item in stock_news.iterrows():
            title = _clean(item.get("title"), "news title missing")
            rows.append(
                {
                    "stock_code": "",
                    "stock_name": stock_name,
                    "milestone": label,
                    "event_date": item["trade_date"].strftime("%Y-%m-%d") if pd.notna(item["trade_date"]) else "",
                    "event_type": _event_type_from_text(title),
                    "source_type": "news",
                    "source_title": title,
                    "source_reference": _clean(item.get("url"), _clean(item.get("source_event_id"), "local_news_event")),
                    "evidence_strength": "source_available",
                }
            )
        for _, item in stock_reports.iterrows():
            title = " / ".join(part for part in [_clean(item.get("company_view")), _clean(item.get("industry_view"))] if part)[:160]
            title = title or f"research report {item.get('report_id')}"
            rows.append(
                {
                    "stock_code": "",
                    "stock_name": stock_name,
                    "milestone": label,
                    "event_date": item["report_date"].strftime("%Y-%m-%d") if pd.notna(item["report_date"]) else "",
                    "event_type": _event_type_from_text(title),
                    "source_type": "broker_research_report",
                    "source_title": title,
                    "source_reference": _clean(item.get("report_id"), "local_stock_report_event"),
                    "evidence_strength": "source_available",
                }
            )
        if stock_news.empty and stock_reports.empty:
            rows.append(
                {
                    "stock_code": "",
                    "stock_name": stock_name,
                    "milestone": label,
                    "event_date": center.strftime("%Y-%m-%d"),
                    "event_type": "unknown",
                    "source_type": "evidence_required",
                    "source_title": "evidence_required",
                    "source_reference": "local catalyst source unavailable for milestone window",
                    "evidence_strength": "missing",
                }
            )
    return rows


def _finance_feature(asset_id: str, cutoff: str, income: pd.DataFrame, cash: pd.DataFrame, balance: pd.DataFrame) -> dict[str, Any]:
    cutoff_ts = pd.Timestamp(cutoff)
    stock_income = income[(income["asset_id"] == asset_id) & (income["announcement_date"].fillna(income["report_period"]) <= cutoff_ts)].copy()
    stock_cash = cash[(cash["asset_id"] == asset_id) & (cash["announcement_date"].fillna(cash["report_period"]) <= cutoff_ts)].copy()
    stock_balance = balance[(balance["asset_id"] == asset_id) & (balance["announcement_date"].fillna(balance["report_period"]) <= cutoff_ts)].copy()
    result = {
        "revenue_growth_ttm": None,
        "net_profit_growth_ttm": None,
        "quarterly_revenue_acceleration": None,
        "quarterly_profit_acceleration": None,
        "gross_margin": None,
        "rd_expense": None,
        "rd_expense_ratio": None,
        "operating_cash_flow": None,
        "market_cap_at_start": None,
        "market_cap_at_100pct": None,
        "pe_pb_ps_at_start": "evidence_required",
        "earnings_surprise_or_forecast_revision": "evidence_required",
        "order_or_capacity_expansion_evidence": "evidence_required",
        "fundamental_data_status": "missing",
    }
    if not stock_income.empty:
        latest = stock_income.sort_values("report_period").iloc[-1]
        previous_period = latest["report_period"] - pd.DateOffset(years=1)
        previous = stock_income[stock_income["report_period"] == previous_period]
        if not previous.empty:
            prev = previous.iloc[-1]
            if prev.get("revenue") and not pd.isna(prev.get("revenue")):
                result["revenue_growth_ttm"] = float(latest.get("revenue") / prev.get("revenue") - 1.0)
            if prev.get("net_profit") and not pd.isna(prev.get("net_profit")):
                result["net_profit_growth_ttm"] = float(latest.get("net_profit") / prev.get("net_profit") - 1.0)
        result["fundamental_data_status"] = "partial_source_available"
    if not stock_cash.empty:
        result["operating_cash_flow"] = float(stock_cash.sort_values("report_period").iloc[-1].get("net_operate_cash_flow") or 0)
        result["fundamental_data_status"] = "partial_source_available"
    return result


def generate(output_dir: Path = OUTPUT_DIR, service: str = SETTINGS.research_service) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doubled = _load_input()
    codes = doubled["stock_code"].tolist()
    asset_map = _stock_code_to_asset_ids(codes, service)
    doubled["asset_id"] = doubled["stock_code"].map(asset_map)
    asset_ids = [asset for asset in doubled["asset_id"].dropna().unique().tolist()]
    bars = _load_bars(asset_ids, service)
    income, cash, balance = _load_finance(asset_ids, service)
    news, reports, report_features = _load_events(asset_ids, service)

    path_rows: list[dict[str, Any]] = []
    tech_rows: list[dict[str, Any]] = []
    fundamental_rows: list[dict[str, Any]] = []
    catalyst_rows: list[dict[str, Any]] = []
    sentiment_rows: list[dict[str, Any]] = []
    archetype_rows: list[dict[str, Any]] = []
    master_rows: list[dict[str, Any]] = []

    for _, row in doubled.iterrows():
        stock_code = row["stock_code"]
        stock_name = row["stock_name"]
        asset_id = row["asset_id"]
        stock_bars = bars[bars["asset_id"] == asset_id].sort_values("trade_date").reset_index(drop=True)
        stock_bars.index = range(len(stock_bars))
        start_close = float(row["start_close_qfq"])
        date30, days30 = _first_crossing(stock_bars, start_close, 0.3)
        date50, days50 = _first_crossing(stock_bars, start_close, 0.5)
        date100, days100 = _first_crossing(stock_bars, start_close, 1.0)
        if date100 is None:
            date100 = row["latest_date"]
            days100 = len(stock_bars)
        idx100 = max(int(days100 or len(stock_bars)) - 1, 0)
        pre = stock_bars.iloc[: idx100 + 1].copy()
        post = stock_bars.iloc[idx100:].copy()
        before_window = stock_bars.iloc[max(0, idx100 - 120) : idx100].copy()
        limit_mask = stock_bars["pct_chg"].fillna(0).ge(9.8)
        number_of_limit_up_days = int(limit_mask.sum())
        new_high_days = int(stock_bars["close"].eq(stock_bars["close"].cummax()).sum())
        vol20 = before_window["volume"].tail(20).mean()
        vol120 = before_window["volume"].tail(120).mean()
        amt20 = before_window["amount"].tail(20).mean()
        amt120 = before_window["amount"].tail(120).mean()
        volume_ratio = float(vol20 / vol120) if vol120 and not pd.isna(vol120) else None
        amount_ratio = float(amt20 / amt120) if amt120 and not pd.isna(amt120) else None
        volatility_20d = float(before_window["close"].pct_change().tail(20).std()) if len(before_window) >= 2 else None
        ma20 = before_window["close"].rolling(20).mean().dropna().tail(20)
        ma60 = before_window["close"].rolling(60).mean().dropna().tail(60)
        last_pre_close = before_window["close"].iloc[-1] if not before_window.empty else None
        high120 = before_window["close"].tail(120).max() if not before_window.empty else None
        distance_high = float(last_pre_close / high120 - 1.0) if high120 and last_pre_close else None
        limit_pre20 = int(before_window["pct_chg"].fillna(0).tail(20).ge(9.8).sum()) if not before_window.empty else 0
        breakout = _breakout_type(before_window, volume_ratio, distance_high, limit_pre20)
        strict_theme = _strict_theme(row)
        path = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "start_date_used": row["start_date_used"],
            "start_close_qfq": row["start_close_qfq"],
            "latest_date": row["latest_date"],
            "latest_close_qfq": row["latest_close_qfq"],
            "return_since_20250101": row["return_since_20250101"],
            "max_return_since_20250101": row["max_return_since_20250101"],
            "date_return_30pct": date30,
            "date_return_50pct": date50,
            "date_return_100pct": date100,
            "trading_days_to_30pct": days30,
            "trading_days_to_50pct": days50,
            "trading_days_to_100pct": days100,
            "max_drawdown_before_100pct": _max_drawdown(pre["close"]),
            "max_drawdown_after_100pct": _max_drawdown(post["close"]),
            "number_of_limit_up_days": number_of_limit_up_days,
            "number_of_new_high_days": new_high_days,
            "main_uptrend_duration_days": (int(days100 or 0) - int(days30 or 0)) if days30 and days100 else None,
        }
        technical = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "return_20d_before_breakout": _pct_return(before_window["close"], min(20, max(len(before_window) - 1, 1))),
            "return_60d_before_breakout": _pct_return(before_window["close"], min(60, max(len(before_window) - 1, 1))),
            "return_120d_before_breakout": _pct_return(before_window["close"], min(120, max(len(before_window) - 1, 1))),
            "volume_ratio_20d_vs_120d": volume_ratio,
            "amount_ratio_20d_vs_120d": amount_ratio,
            "volatility_20d": volatility_20d,
            "ma20_slope": _slope(ma20),
            "ma60_slope": _slope(ma60),
            "distance_to_120d_high_before_breakout": distance_high,
            "base_consolidation_days": int((before_window["close"].tail(120) / before_window["close"].tail(120).max()).ge(0.8).sum()) if not before_window.empty else None,
            "breakout_type": breakout,
        }
        path_rows.append(path)
        tech_rows.append(technical | {"strict_theme": strict_theme})
        fund = _finance_feature(asset_id, date100, income, cash, balance)
        fundamental_rows.append({"stock_code": stock_code, "stock_name": stock_name} | fund)
        event_rows = _nearest_events(
            asset_id,
            stock_name,
            [("+30%", date30), ("+50%", date50), ("+100%", date100)],
            news,
            reports,
        )
        for event in event_rows:
            event["stock_code"] = stock_code
        catalyst_rows.extend(event_rows)
        event_types = [event["event_type"] for event in event_rows if event["event_type"] != "unknown"]
        event_type = event_types[0] if event_types else ("AI theme" if "AI" in strict_theme or "optical" in strict_theme else "unknown")
        breakout_ts = pd.Timestamp(date100)
        news_count = int(
            len(
                news[
                    (news["asset_id"] == asset_id)
                    & (news["trade_date"] >= breakout_ts - pd.Timedelta(days=30))
                    & (news["trade_date"] < breakout_ts)
                ]
            )
        ) if not news.empty else 0
        report_count = int(
            len(
                reports[
                    (reports["asset_id"] == asset_id)
                    & (reports["report_date"] >= breakout_ts - pd.Timedelta(days=60))
                    & (reports["report_date"] < breakout_ts)
                ]
            )
        ) if not reports.empty else 0
        sentiment_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "strict_theme": strict_theme,
                "sentiment_event_type": event_type,
                "news_count_30d_before_breakout": news_count,
                "research_report_count_60d_before_breakout": report_count,
                "theme_news_burst": news_count >= 3,
                "research_attention_burst": report_count >= 2,
            }
        )
        archetype_input = pd.Series(row.to_dict() | path | technical | {"strict_theme": strict_theme, "number_of_limit_up_days": number_of_limit_up_days})
        archetype = _pattern_archetype(archetype_input)
        archetype_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "strict_theme": strict_theme,
                "pattern_archetype": archetype,
                "primary_pattern_reason": f"{strict_theme}; breakout_type={breakout}; limit_up_days={number_of_limit_up_days}",
            }
        )
        master_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "strict_theme": strict_theme,
                "original_tech_theme": row["tech_theme"],
                "hard_tech_relevance": row["hard_tech_relevance"],
                "return_since_20250101": row["return_since_20250101"],
                "date_return_100pct": date100,
                "trading_days_to_100pct": days100,
                "breakout_type": breakout,
                "sentiment_event_type": event_type,
                "pattern_archetype": archetype,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )

    path_df = pd.DataFrame(path_rows)
    technical_df = pd.DataFrame(tech_rows)
    fundamental_df = pd.DataFrame(fundamental_rows)
    catalyst_df = pd.DataFrame(catalyst_rows)
    sentiment_df = pd.DataFrame(sentiment_rows)
    archetype_df = pd.DataFrame(archetype_rows)
    master_df = pd.DataFrame(master_rows)

    theme_summary = (
        master_df.groupby("strict_theme")
        .agg(
            stock_count=("stock_code", "count"),
            median_return=("return_since_20250101", "median"),
            mean_return=("return_since_20250101", "mean"),
            representative_stocks=("stock_name", lambda values: "、".join(list(values.head(8)))),
        )
        .reset_index()
        .sort_values(["stock_count", "median_return"], ascending=[False, False])
    )
    early = master_df[
        [
            "stock_code",
            "stock_name",
            "strict_theme",
            "pattern_archetype",
            "breakout_type",
            "trading_days_to_100pct",
        ]
    ].merge(
        technical_df.drop(columns=["strict_theme", "breakout_type"], errors="ignore"),
        on=["stock_code", "stock_name"],
        how="left",
    )
    early = early[
        [
            "stock_code",
            "stock_name",
            "strict_theme",
            "pattern_archetype",
            "breakout_type",
            "return_20d_before_breakout",
            "return_60d_before_breakout",
            "return_120d_before_breakout",
            "volume_ratio_20d_vs_120d",
            "amount_ratio_20d_vs_120d",
            "distance_to_120d_high_before_breakout",
            "trading_days_to_100pct",
        ]
    ]
    risk = master_df.merge(path_df[["stock_code", "stock_name", "max_drawdown_after_100pct", "number_of_limit_up_days"]], on=["stock_code", "stock_name"])
    risk["risk_pattern"] = risk.apply(
        lambda row: "high_post_double_drawdown"
        if pd.notna(row["max_drawdown_after_100pct"]) and row["max_drawdown_after_100pct"] <= -0.3
        else "sentiment_cluster_risk"
        if row["number_of_limit_up_days"] >= 5
        else "late_after_double_risk",
        axis=1,
    )
    risk = risk[["stock_code", "stock_name", "strict_theme", "pattern_archetype", "max_drawdown_after_100pct", "number_of_limit_up_days", "risk_pattern"]]

    master_df.to_csv(output_dir / "doubled_tech_stock_pattern_master.csv", index=False)
    theme_summary.to_csv(output_dir / "doubled_tech_theme_summary.csv", index=False)
    path_df.to_csv(output_dir / "doubling_path_features.csv", index=False)
    technical_df.to_csv(output_dir / "pre_breakout_technical_features.csv", index=False)
    fundamental_df.to_csv(output_dir / "fundamental_features.csv", index=False)
    catalyst_df.to_csv(output_dir / "catalyst_event_timeline.csv", index=False)
    sentiment_df.to_csv(output_dir / "sentiment_and_theme_features.csv", index=False)
    archetype_df.to_csv(output_dir / "pattern_archetype_classification.csv", index=False)
    early.to_csv(output_dir / "early_signal_candidate_features.csv", index=False)
    risk.to_csv(output_dir / "false_positive_and_risk_patterns.csv", index=False)

    case_text = _case_studies(master_df, path_df, technical_df, fundamental_df, catalyst_df, sentiment_df)
    (output_dir / "representative_case_studies.md").write_text(case_text, encoding="utf-8")
    _render_pdf(case_text, output_dir / "representative_case_studies.pdf")
    methodology = _methodology_notes()
    (output_dir / "pattern_methodology_notes.md").write_text(methodology, encoding="utf-8")

    strategy_diff = _git_diff_formal_strategy_files()
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "input_doubled_tech_count": int(len(doubled)),
        "master_rows": int(len(master_df)),
        "theme_count": int(theme_summary["strict_theme"].nunique()),
        "top_theme_by_count": _clean(theme_summary.iloc[0]["strict_theme"]) if not theme_summary.empty else "",
        "top_theme_by_median_return": _clean(theme_summary.sort_values("median_return", ascending=False).iloc[0]["strict_theme"]) if not theme_summary.empty else "",
        "case_study_count": int(master_df["stock_name"].isin(REQUIRED_CASES).sum()),
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "acceptance_decision": "a_share_doubled_tech_stock_pattern_study_ready" if strategy_diff == "" else "blocked_due_to_strategy_diff",
    }
    _write_json(output_dir / "pattern_study_summary.json", summary)
    report = _report(summary, theme_summary, master_df, technical_df, fundamental_df, sentiment_df, risk)
    (output_dir / "a_share_doubled_tech_stock_pattern_study_v1_report.md").write_text(report, encoding="utf-8")
    return summary


def _case_studies(master: pd.DataFrame, path: pd.DataFrame, technical: pd.DataFrame, fundamental: pd.DataFrame, catalyst: pd.DataFrame, sentiment: pd.DataFrame) -> str:
    sections = ["# Representative doubled tech stock case studies", "", "Research-only case review. No signal or admission output.", ""]
    for name in REQUIRED_CASES:
        m = master[master["stock_name"] == name]
        if m.empty:
            sections.append(f"## {name}\n\ncase_missing: input row not found.\n")
            continue
        row = m.iloc[0]
        p = path[path["stock_code"] == row["stock_code"]].iloc[0]
        t = technical[technical["stock_code"] == row["stock_code"]].iloc[0]
        f = fundamental[fundamental["stock_code"] == row["stock_code"]].iloc[0]
        s = sentiment[sentiment["stock_code"] == row["stock_code"]].iloc[0]
        events = catalyst[catalyst["stock_code"] == row["stock_code"]].head(6)
        event_lines = "\n".join(
            f"- {event.event_date} [{event.milestone}] {event.event_type}: {event.source_title} ({event.source_reference})"
            for event in events.itertuples(index=False)
        )
        sections.append(
            f"""## {row['stock_code']} {name}

- theme: {row['strict_theme']}
- pattern_archetype: {row['pattern_archetype']}
- return_since_20250101: {float(row['return_since_20250101']):.2f}
- date_return_100pct: {p['date_return_100pct']}
- trading_days_to_100pct: {p['trading_days_to_100pct']}
- breakout_type: {t['breakout_type']}
- price/volume path: +30% on {p['date_return_30pct']}, +50% on {p['date_return_50pct']}, +100% on {p['date_return_100pct']}; volume_ratio_20d_vs_120d={_fmt(t['volume_ratio_20d_vs_120d'])}; amount_ratio_20d_vs_120d={_fmt(t['amount_ratio_20d_vs_120d'])}.
- key catalysts: {s['sentiment_event_type']}; local source rows are listed below when available.
- fundamental evidence: {f['fundamental_data_status']}; revenue_growth_ttm={_fmt(f['revenue_growth_ttm'])}; net_profit_growth_ttm={_fmt(f['net_profit_growth_ttm'])}; operating_cash_flow={_fmt(f['operating_cash_flow'])}.
- why it doubled: classification combines theme exposure, path features, and available local event/fundamental evidence. Missing source rows remain `evidence_required`.
- early signs: breakout_type={t['breakout_type']}; return_60d_before_breakout={_fmt(t['return_60d_before_breakout'])}; distance_to_120d_high_before_breakout={_fmt(t['distance_to_120d_high_before_breakout'])}.
- hard-to-detect ex ante: catalyst source gaps, future theme diffusion, and later valuation expansion are not inferable from price alone.
- risk after doubling: max_drawdown_after_100pct={_fmt(p['max_drawdown_after_100pct'])}; post-double risk requires separate review.

### Timeline / source rows

{event_lines or '- evidence_required'}
"""
        )
    return "\n".join(sections)


def _fmt(value: Any) -> str:
    if value is None:
        return "evidence_required"
    try:
        if pd.isna(value):
            return "evidence_required"
        if isinstance(value, (int, float)):
            return f"{float(value):.4f}"
    except Exception:
        pass
    return _clean(value, "evidence_required")


def _methodology_notes() -> str:
    return """# Pattern methodology notes

This module studies stocks that already doubled. It does not add stocks to any pool and does not produce signals.

## Data layers

1. Input scope: doubled tech/hard-tech rows from `a_share_doubled_tech_stocks_since_20250101_v1`.
2. Price path: local `market_daily_bar` qfq close, volume, amount, turnover, pct_chg.
3. Fundamental layer: local finance statements when available; missing fields are explicit `evidence_required`.
4. Catalyst layer: local news and stock report tables when available; unavailable windows are explicit `evidence_required`.

## Interpretation limits

The study separates observed price/volume facts from inferred catalysts. Theme and pattern labels are research categories, not production scoring logic.
"""


def _report(summary: dict[str, Any], theme_summary: pd.DataFrame, master: pd.DataFrame, technical: pd.DataFrame, fundamental: pd.DataFrame, sentiment: pd.DataFrame, risk: pd.DataFrame) -> str:
    common_breakouts = technical["breakout_type"].value_counts().rename_axis("breakout_type").reset_index(name="count")
    fundamentals_available = int(fundamental["fundamental_data_status"].eq("partial_source_available").sum())
    sentiment_types = sentiment["sentiment_event_type"].value_counts().rename_axis("sentiment_event_type").reset_index(name="count")
    archetypes = master["pattern_archetype"].value_counts().rename_axis("pattern_archetype").reset_index(name="count")
    return f"""# A-share doubled tech stock pattern study v1

Research-only pattern study. No signal, no admission logic, no production candidate change.

## Scope

- input doubled tech count: {summary['input_doubled_tech_count']}
- theme count: {summary['theme_count']}
- case study count: {summary['case_study_count']}
- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}

## Which hard-tech themes produced the most doublers?

{theme_summary[['strict_theme', 'stock_count', 'median_return', 'representative_stocks']].to_markdown(index=False)}

## Which themes had the highest median return?

{theme_summary.sort_values('median_return', ascending=False)[['strict_theme', 'stock_count', 'median_return', 'representative_stocks']].head(10).to_markdown(index=False)}

## What were the most common pre-breakout technical traits?

{common_breakouts.to_markdown(index=False)}

## How often did fundamentals improve before price doubled?

Local finance rows were available for {fundamentals_available} of {len(fundamental)} stocks. Missing finance rows are marked evidence_required; no fundamental claim is inferred from price alone.

## How often was the move mainly theme/sentiment driven?

{sentiment_types.to_markdown(index=False)}

## What catalyst types were most common?

Catalyst event types are derived from local news/report titles when available and otherwise marked unknown/evidence_required.

## Did small-cap stocks dominate, or did large-cap fundamental leaders also double?

Market-cap-at-start is not fully available in local source tables for this run, so this question is left as evidence_required in `fundamental_features.csv`.

## What early signals could have identified some winners?

Reusable early features are exported in `early_signal_candidate_features.csv`: breakout type, 20/60/120 day pre-breakout returns, volume and amount expansion, moving-average slopes, and distance to 120-day high.

## What signals were unreliable or late?

Late/risky rows are exported in `false_positive_and_risk_patterns.csv`. High post-double drawdown, sentiment clusters, and weak source evidence are not reliable standalone predictors.

## Which doubled stocks are too late/high-risk after the move?

{risk['risk_pattern'].value_counts().rename_axis('risk_pattern').reset_index(name='count').to_markdown(index=False)}

## What lessons can improve future hard-tech candidate selection?

- Separate theme exposure from bottleneck role.
- Track source-backed catalyst density before the move, not only after.
- Combine low-base or new-high breakout features with hard-tech relevance.
- Treat weak-source and concept-only rows as risk patterns, not automatic candidates.
- Use doubled stocks to improve research workflow, not to backfill production admission.

## Pattern archetypes

{archetypes.to_markdown(index=False)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir, service=args.service)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
