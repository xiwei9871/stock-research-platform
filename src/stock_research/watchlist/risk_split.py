from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


FAILURE_STRUCTURES = {
    "a_kill_failure",
    "failed_second_wave",
    "high_open_low_close_failure",
    "one_day_pump",
    "failed_reversal",
}

PERFORMANCE_COLUMNS = [
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
    "future_40d_return",
    "future_60d_return",
    "future_20d_max_drawdown",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]


def run_risk_watch_split_review(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    return build_risk_watch_split_from_frame(detail, output_dir=output_dir)


def build_risk_watch_split_from_frame(
    detail: pd.DataFrame,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    risk_detail = detail[detail.get("watch_group", pd.Series(dtype=object)).fillna("").eq("risk_watch")].copy()
    if risk_detail.empty:
        risk_detail = pd.DataFrame(columns=list(detail.columns) + ["risk_split_group", "split_reason"])
    else:
        classifications = risk_detail.apply(classify_risk_watch_row, axis=1, result_type="expand")
        risk_detail = pd.concat([risk_detail.reset_index(drop=True), classifications.reset_index(drop=True)], axis=1)

    summary = _build_split_summary(risk_detail)
    reason_summary = _build_reason_summary(risk_detail)
    report = _render_report(summary, reason_summary, risk_detail)

    result: dict[str, Any] = {
        "detail": risk_detail,
        "summary": summary,
        "reason_summary": reason_summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "risk_watch_split_detail.csv",
            "summary": output / "risk_watch_split_summary.csv",
            "reason_summary": output / "risk_watch_split_reason_summary.csv",
            "report": output / "risk_watch_split_report.md",
        }
        risk_detail.to_csv(paths["detail"], index=False)
        summary.to_csv(paths["summary"], index=False)
        reason_summary.to_csv(paths["reason_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def classify_risk_watch_row(row: pd.Series) -> dict[str, str]:
    reasons = _risk_reasons(row)
    hard_reasons = [reason for reason in reasons if reason in _hard_reason_set()]
    elasticity_reasons = [reason for reason in reasons if reason in _elasticity_reason_set()]

    if hard_reasons:
        group = "hard_risk"
    elif _is_high_elasticity_shadow(row, elasticity_reasons):
        group = "high_elasticity_risk_shadow"
    else:
        group = "ambiguous_risk"

    return {
        "risk_split_group": group,
        "split_reason": ",".join(reasons) if reasons else "risk_watch_unspecified",
    }


def _risk_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    structure = _text(row.get("event_structure"))
    if structure in FAILURE_STRUCTURES or _bool(row.get("failure_flag")):
        reasons.append("failure_event")
    if _bool(row.get("lhb_negative_net_buy")):
        reasons.append("lhb_negative_net_buy")
    if _bool(row.get("lhb_institution_selling")):
        reasons.append("lhb_institution_selling")
    if _bool(row.get("lhb_high_pump_risk")):
        reasons.append("lhb_high_pump_risk")
    if _float(row.get("dragon_risk_score")) >= 0.7 and _float(row.get("lhb_risk_score")) >= 0.7:
        reasons.append("dragon_lhb_risk_confluence")
    if _float(row.get("dragon_risk_score")) >= 0.7:
        reasons.append("dragon_risk_high")
    if _float(row.get("lhb_risk_score")) >= 0.7:
        reasons.append("lhb_risk_high")
    if _bool(row.get("overheat_avoid")):
        reasons.append("overheat_avoid")
    if _bool(row.get("crowded_late_entry")):
        reasons.append("crowded_late_entry")
    if _float(row.get("amount_vs_20d")) >= 4.0:
        reasons.append("extreme_amount")
    if _float(row.get("high_to_close_drawdown")) >= 0.08:
        reasons.append("intraday_fade")
    if _float(row.get("volatility_5d")) >= 0.05:
        reasons.append("high_volatility")
    return reasons


def _is_high_elasticity_shadow(row: pd.Series, elasticity_reasons: list[str]) -> bool:
    score_rank = _float(row.get("score_rank"))
    if not (0 < score_rank <= 50):
        return False
    if not elasticity_reasons:
        return False
    if _float(row.get("amount_vs_20d")) >= 1.5:
        return True
    if _float(row.get("volatility_5d")) >= 0.04:
        return True
    return _bool(row.get("overheat_avoid")) and _float(row.get("dragon_risk_score")) < 0.7


def _hard_reason_set() -> set[str]:
    return {
        "failure_event",
        "lhb_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "dragon_lhb_risk_confluence",
        "dragon_risk_high",
        "lhb_risk_high",
    }


def _elasticity_reason_set() -> set[str]:
    return {
        "intraday_fade",
        "extreme_amount",
        "high_volatility",
        "overheat_avoid",
        "crowded_late_entry",
    }


def _build_split_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "risk_split_group",
        "sample_count",
        "avg_score_rank",
        "avg_amount_vs_20d",
        "avg_high_to_close_drawdown",
        "avg_volatility_5d",
        "avg_future_5d_return",
        "avg_future_20d_return",
        "avg_future_60d_return",
        "avg_future_20d_max_drawdown",
        "avg_future_60d_max_drawdown",
        "avg_max_return_within_60d",
        "hit_double_within_60d_rate",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    for column in [
        "score_rank",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "volatility_5d",
        *PERFORMANCE_COLUMNS,
    ]:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    grouped = frame.groupby("risk_split_group", dropna=False)
    summary = grouped.agg(
        sample_count=("asset_id", "size"),
        avg_score_rank=("score_rank", "mean"),
        avg_amount_vs_20d=("amount_vs_20d", "mean"),
        avg_high_to_close_drawdown=("high_to_close_drawdown", "mean"),
        avg_volatility_5d=("volatility_5d", "mean"),
        avg_future_5d_return=("future_5d_return", "mean"),
        avg_future_20d_return=("future_20d_return", "mean"),
        avg_future_60d_return=("future_60d_return", "mean"),
        avg_future_20d_max_drawdown=("future_20d_max_drawdown", "mean"),
        avg_future_60d_max_drawdown=("future_60d_max_drawdown", "mean"),
        avg_max_return_within_60d=("max_return_within_60d", "mean"),
        hit_double_within_60d_rate=("hit_double_within_60d", "mean"),
    ).reset_index()
    return summary.loc[:, columns].sort_values("risk_split_group").reset_index(drop=True)


def _build_reason_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "split_reason",
        "sample_count",
        "risk_split_group_distribution",
        "avg_future_20d_return",
        "avg_future_60d_return",
        "avg_future_60d_max_drawdown",
        "hit_double_within_60d_rate",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for _, row in detail.iterrows():
        reasons = [reason for reason in str(row.get("split_reason") or "").split(",") if reason]
        for reason in reasons or ["risk_watch_unspecified"]:
            record = row.to_dict()
            record["split_reason"] = reason
            rows.append(record)
    exploded = pd.DataFrame(rows)
    for column in PERFORMANCE_COLUMNS:
        if column not in exploded.columns:
            exploded[column] = pd.NA
        exploded[column] = pd.to_numeric(exploded[column], errors="coerce")
    grouped = exploded.groupby("split_reason", dropna=False)
    summary = grouped.agg(
        sample_count=("asset_id", "size"),
        avg_future_20d_return=("future_20d_return", "mean"),
        avg_future_60d_return=("future_60d_return", "mean"),
        avg_future_60d_max_drawdown=("future_60d_max_drawdown", "mean"),
        hit_double_within_60d_rate=("hit_double_within_60d", "mean"),
    ).reset_index()
    distribution = grouped["risk_split_group"].apply(lambda values: _distribution(values)).reset_index(
        name="risk_split_group_distribution"
    )
    return (
        summary.merge(distribution, on="split_reason", how="left")
        .loc[:, columns]
        .sort_values(["sample_count", "split_reason"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _distribution(values: pd.Series) -> str:
    counts = values.value_counts(dropna=False)
    total = int(counts.sum())
    return ";".join(f"{key}:{count}/{total}" for key, count in counts.items())


def _render_report(summary: pd.DataFrame, reason_summary: pd.DataFrame, detail: pd.DataFrame) -> str:
    lines = [
        "# Risk Watch Split Review",
        "",
        "## 1. 研究目标",
        "本报告只拆分 risk_watch 的来源：区分硬风险和高弹性风险观察，不改变正式 watchlist 规则。",
        "",
        "## 2. 拆分定义",
        "- hard_risk: 失败事件、LHB 负面、Dragon/LHB 风险共振或明确高风险分。",
        "- high_elasticity_risk_shadow: 没有硬风险，但因为冲高回落、放量、波动或过热被放入 risk_watch 的强排名样本。",
        "- ambiguous_risk: 信息不足或不满足高弹性条件的 risk_watch 样本。",
        "",
        "## 3. 拆分结果",
    ]
    if summary.empty:
        lines.append("- 无 risk_watch 样本。")
    else:
        lines.append(summary.to_markdown(index=False))
    lines.extend(["", "## 4. 原因有效性"])
    if reason_summary.empty:
        lines.append("- 无原因统计。")
    else:
        lines.append(reason_summary.to_markdown(index=False))
    if not detail.empty:
        if "max_return_within_60d" not in detail.columns:
            detail = detail.copy()
            detail["max_return_within_60d"] = pd.NA
        top = detail.sort_values("max_return_within_60d", ascending=False).head(10)
        lines.extend(["", "## 5. 高弹性样本线索"])
        for row in top.to_dict("records"):
            lines.append(
                f"- {row.get('trade_date')} {row.get('ts_code')} rank={row.get('score_rank')} "
                f"group={row.get('risk_split_group')} reason={row.get('split_reason')} "
                f"max60={_float(row.get('max_return_within_60d')):.2%} "
                f"dd60={_float(row.get('future_60d_max_drawdown')):.2%}"
            )
    lines.extend(
        [
            "",
            "## 6. 初步结论",
            "如果 high_elasticity_risk_shadow 的强票命中高但回撤可控，应从 risk_watch 中拆出为单独观察层；hard_risk 继续作为排雷层。",
        ]
    )
    return "\n".join(lines) + "\n"


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "n", "off", "none", "null", "nan"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
    return bool(value)
