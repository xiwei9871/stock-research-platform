from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.quality import latest_trade_date

RETURN_HORIZONS = [1, 3, 5, 10, 20]
SUMMARY_RETURN_COLUMNS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
]
SUMMARY_DRAWDOWN_COLUMNS = [
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
    "future_20d_max_drawdown",
]
SUMMARY_GROUP_METRICS = [
    "sample_count",
    "win_rate_5d",
    "win_rate_10d",
]
SUMMARY_COLUMNS = SUMMARY_GROUP_METRICS + [
    f"avg_{column}" for column in SUMMARY_RETURN_COLUMNS + SUMMARY_DRAWDOWN_COLUMNS
]
BUCKET_FEATURES = [
    "notice_count_3d",
    "notice_count_10d",
    "research_report_count_20d",
    "rating_action_count_20d",
    "risk_notice_count_20d",
]


def load_review_inputs(*, base_dir: str | Path) -> dict[str, pd.DataFrame]:
    base = Path(base_dir)
    return {
        "candidates": pd.read_csv(base / "historical_top10_candidates.csv", low_memory=False),
        "features": pd.read_csv(base / "historical_news_feature_daily.csv", low_memory=False),
        "enrichment": pd.read_csv(
            base / "historical_top10_news_enrichment.csv",
            low_memory=False,
        ),
    }


def build_future_label_frame(*, bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        columns = [
            "asset_id",
            "trade_date",
            "close",
            "low",
            *SUMMARY_RETURN_COLUMNS,
            "future_1d_max_drawdown",
            "future_3d_max_drawdown",
            *SUMMARY_DRAWDOWN_COLUMNS,
        ]
        return pd.DataFrame(columns=columns)

    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
    frame = frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)

    for horizon in RETURN_HORIZONS:
        frame[f"future_{horizon}d_return"] = frame.groupby("asset_id")["close"].shift(-horizon) / frame["close"] - 1.0
        frame[f"future_{horizon}d_max_drawdown"] = _forward_max_drawdown(frame, horizon)

    frame["trade_date"] = frame["trade_date"].dt.strftime("%Y-%m-%d")
    return frame


def bucket_0_1_2plus(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0]
    try:
        integer_value = int(number)
    except (TypeError, ValueError, OverflowError):
        integer_value = 0
    if integer_value <= 0:
        return "0"
    if integer_value == 1:
        return "1"
    return "2+"


def build_count_bucket_summary(frame: pd.DataFrame, *, feature_name: str) -> pd.DataFrame:
    columns = ["feature_name", "bucket", *SUMMARY_COLUMNS]
    if frame.empty or feature_name not in frame.columns:
        return pd.DataFrame(columns=columns)

    data = frame.copy()
    data["bucket"] = data[feature_name].map(bucket_0_1_2plus)
    summary = build_group_summary(data, group_col="bucket")
    summary.insert(0, "feature_name", feature_name)
    return summary.reindex(columns=columns)


def load_daily_bars_for_review(*, asset_ids: list[str], end_date: str, adjust_type: str) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "trade_date", "close", "low"])

    sql = """
        SELECT asset_id, trade_date, close, low
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND asset_id = ANY(%s)
          AND trade_date <= %s
        ORDER BY asset_id, trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, asset_ids, end_date])
    return pd.DataFrame(rows)


def build_review_base_frame(
    *,
    candidates: pd.DataFrame,
    features: pd.DataFrame,
    enrichment: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    frame = candidates.copy()
    for payload in (features, enrichment, labels):
        payload = _dedupe_review_join_payload(payload)
        frame = frame.merge(payload, on=["trade_date", "asset_id"], how="left")
    frame["coverage_group"] = frame.apply(_coverage_group, axis=1)
    frame["source_type_group"] = frame.apply(_source_type_group, axis=1)
    return frame


def build_group_summary(frame: pd.DataFrame, *, group_col: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group_value, group in frame.groupby(group_col, dropna=False, sort=False):
        row: dict[str, object] = {
            group_col: group_value,
            "sample_count": int(len(group)),
        }
        future_5d = _numeric_group_series(group, "future_5d_return")
        future_10d = _numeric_group_series(group, "future_10d_return")
        row["win_rate_5d"] = _win_rate(future_5d)
        row["win_rate_10d"] = _win_rate(future_10d)
        for column in SUMMARY_RETURN_COLUMNS + SUMMARY_DRAWDOWN_COLUMNS:
            row[f"avg_{column}"] = float("nan")
            if column in group.columns:
                values = pd.to_numeric(group[column], errors="coerce")
                row[f"avg_{column}"] = float(values.mean())
        rows.append(row)
    return pd.DataFrame(rows, columns=[group_col, *SUMMARY_COLUMNS])


def _forward_max_drawdown(frame: pd.DataFrame, horizon: int) -> pd.Series:
    result = pd.Series(float("nan"), index=frame.index)
    for _, group in frame.groupby("asset_id", sort=False):
        lows = group["low"].tolist()
        closes = group["close"].tolist()
        values: list[float] = []
        for index, close in enumerate(closes):
            window = [
                value
                for value in lows[index + 1 : index + horizon + 1]
                if not pd.isna(value)
            ]
            if not window or pd.isna(close) or close == 0:
                values.append(float("nan"))
                continue
            values.append(min(window) / close - 1.0)
        result.loc[group.index] = values
    return result


def _dedupe_review_join_payload(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.drop_duplicates(subset=["trade_date", "asset_id"], keep="last").copy()


def _numeric_group_series(group: pd.DataFrame, column: str) -> pd.Series:
    if column not in group.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(group[column], errors="coerce")


def _win_rate(values: pd.Series) -> float:
    valid = values.dropna()
    if valid.empty:
        return float("nan")
    return float((valid > 0).mean())


def _coverage_group(row: pd.Series) -> str:
    summary = row.get("historical_event_summary")
    if pd.notna(summary) and str(summary).strip():
        return "historical_summary_present"
    attention = row.get("news_attention_level")
    if pd.notna(attention) and str(attention).strip().lower() != "unknown":
        return "news_feature_only"
    return "no_news_feature"


def _source_type_group(row: pd.Series) -> str:
    notice_count = pd.to_numeric(row.get("notice_count_10d"), errors="coerce")
    report_count = pd.to_numeric(row.get("research_report_count_20d"), errors="coerce")
    has_notice = bool(pd.notna(notice_count) and notice_count > 0)
    has_report = bool(pd.notna(report_count) and report_count > 0)
    if has_notice and has_report:
        return "notice_and_report"
    if has_notice:
        return "notice_only"
    if has_report:
        return "report_only"
    return "no_historical_event"


def _trade_date_end(frame: pd.DataFrame) -> str:
    if frame.empty or "trade_date" not in frame.columns:
        return pd.Timestamp.today().date().isoformat()
    trade_dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if trade_dates.empty:
        return pd.Timestamp.today().date().isoformat()
    return trade_dates.max().date().isoformat()


def _render_summary_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    return frame.to_markdown(index=False)


def _render_review_report(
    *,
    base_frame: pd.DataFrame,
    coverage_summary: pd.DataFrame,
    source_type_summary: pd.DataFrame,
    feature_bucket_summary: pd.DataFrame,
) -> str:
    sections = [
        "# Top10 Historical News Effectiveness Review",
        "",
        "## Base Sample",
        f"- rows: {len(base_frame)}",
        f"- columns: {len(base_frame.columns)}",
        "",
        "## Coverage Summary",
        _render_summary_table(coverage_summary),
        "",
        "## Source Type Summary",
        _render_summary_table(source_type_summary),
        "",
        "## Feature Bucket Summary",
        _render_summary_table(feature_bucket_summary),
        "",
    ]
    return "\n".join(sections)


def run_top10_historical_news_effectiveness_review(
    *,
    base_dir: str | Path,
    adjust_type: str,
    output_dir: str | Path,
) -> dict[str, object]:
    base = Path(base_dir)
    payload = load_review_inputs(base_dir=base)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    candidates = payload["candidates"].copy()
    features = payload["features"].copy()
    enrichment = payload["enrichment"].copy()
    asset_ids = [str(value) for value in candidates.get("asset_id", pd.Series(dtype="object")).dropna().astype(str).unique()]
    end_date = latest_trade_date(adjust_type=adjust_type) or _trade_date_end(candidates)
    bars = load_daily_bars_for_review(asset_ids=asset_ids, end_date=end_date, adjust_type=adjust_type)
    labels = build_future_label_frame(bars=bars)
    base_frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )
    coverage_summary = build_group_summary(base_frame, group_col="coverage_group")
    source_type_summary = build_group_summary(base_frame, group_col="source_type_group")
    bucket_frames = [
        build_count_bucket_summary(base_frame, feature_name=feature_name)
        for feature_name in BUCKET_FEATURES
        if feature_name in base_frame.columns
    ]
    feature_bucket_summary = (
        pd.concat(bucket_frames, ignore_index=True)
        if bucket_frames
        else pd.DataFrame(columns=["feature_name", "bucket", *SUMMARY_COLUMNS])
    )

    base_path = output_path / "top10_historical_news_effectiveness_base.csv"
    coverage_summary_path = output_path / "top10_historical_news_effectiveness_coverage_summary.csv"
    source_type_summary_path = output_path / "top10_historical_news_effectiveness_source_type_summary.csv"
    feature_bucket_summary_path = output_path / "top10_historical_news_effectiveness_feature_bucket_summary.csv"
    report_path = output_path / "top10_historical_news_effectiveness_report.md"

    base_frame.to_csv(base_path, index=False)
    coverage_summary.to_csv(coverage_summary_path, index=False)
    source_type_summary.to_csv(source_type_summary_path, index=False)
    feature_bucket_summary.to_csv(feature_bucket_summary_path, index=False)
    report_path.write_text(
        _render_review_report(
            base_frame=base_frame,
            coverage_summary=coverage_summary,
            source_type_summary=source_type_summary,
            feature_bucket_summary=feature_bucket_summary,
        ),
        encoding="utf-8",
    )

    return {
        "adjust_type": adjust_type,
        "paths": {
            "base_dir": str(base),
            "candidates": str(base / "historical_top10_candidates.csv"),
            "features": str(base / "historical_news_feature_daily.csv"),
            "enrichment": str(base / "historical_top10_news_enrichment.csv"),
            "output_dir": str(output_path),
            "base": str(base_path),
            "coverage_summary": str(coverage_summary_path),
            "source_type_summary": str(source_type_summary_path),
            "feature_bucket_summary": str(feature_bucket_summary_path),
            "report": str(report_path),
        },
        "input_rows": {
            "candidates": len(payload["candidates"]),
            "features": len(payload["features"]),
            "enrichment": len(payload["enrichment"]),
        },
    }
