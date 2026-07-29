from __future__ import annotations

import copy
import json
import math
import os
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from .contracts import OUTPUT_FILENAMES, validate_trade_date


REPORT_COLUMNS = (
    "asset_id",
    "stock_code",
    "stock_name",
    "consumer_subindustry",
    "repair_bucket",
    "bucket_rank",
    "return_6m",
    "max_drawdown_12m",
    "relative_return_6m",
    "valuation_method",
    "valuation_percentile",
    "pessimistic_upside",
    "base_upside",
    "optimistic_upside",
    "repair_thesis",
    "unrepaired_metrics",
    "leading_indicator",
    "expected_validation_date",
    "source_title",
    "source_url",
    "source_publish_date",
    "main_risks",
    "invalidation_conditions",
    "operating_gap_score",
    "repair_potential_score",
    "valuation_repair_score",
    "oversold_score",
    "balance_sheet_score",
    "catalyst_verifiability_score",
    "priced_in_penalty",
    "composite_score",
    "exclusion_reasons",
)

_FRAME_KEYS = ("expected", "early", "scores", "exclusions")
_PAYLOAD_KEYS = ("trade_date", *_FRAME_KEYS, "coverage")
_COVERAGE_KEYS = (
    "funnel",
    "data_date_maxima",
    "missing_field_counts",
    "warnings",
    "valuation_history_coverage",
    "finance_history_coverage",
)
_FUNNEL_KEYS = (
    "raw_assets",
    "consumer_universe",
    "market_eligible",
    "oversold_eligible",
    "hard_risk_clear",
    "evidence_complete",
    "valuation_eligible",
    "selected_expected",
    "selected_early",
)
_SELECTED_GATES = {
    "evidence_complete": True,
    "hard_risk_triggered": False,
    "hard_risk_review_unknown": False,
}


def _missing_keys(mapping: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if key not in mapping]


def _ordered_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if result.empty and "asset_id" not in result.columns:
        result = result.reindex(columns=["asset_id", *result.columns])
    preferred = [column for column in REPORT_COLUMNS if column in result.columns]
    extras = sorted(column for column in result.columns if column not in preferred)
    return result.loc[:, [*preferred, *extras]]


def _validate_selected(frame: pd.DataFrame, name: str) -> set[str]:
    if len(frame) > 20:
        raise ValueError(f"{name} must contain at most 20 rows")
    if frame.empty:
        return set()
    if "asset_id" not in frame.columns:
        raise ValueError(f"{name} missing required column: asset_id")
    missing = frame["asset_id"].isna()
    normalized = frame["asset_id"].astype(str).str.strip()
    if (missing | normalized.eq("")).any():
        raise ValueError(f"{name} asset_id must be non-empty")
    if normalized.duplicated().any():
        raise ValueError(f"{name} asset_id must be unique")
    for field, required in _SELECTED_GATES.items():
        if field not in frame.columns:
            continue
        valid = frame[field].map(
            lambda value: isinstance(value, (bool, np.bool_)) and bool(value) is required
        )
        if not valid.all():
            raise ValueError(f"{name} field {field} must be {str(required).lower()}")
    return set(normalized)


def _json_safe(value: Any, path: str = "coverage") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{path} must contain only finite JSON values")
        return number
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} object keys must be strings")
            result[key] = _json_safe(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains a value that is not JSON-safe: {type(value).__name__}")


def _normalize_coverage(coverage: dict[str, Any], trade_date: str) -> dict[str, Any]:
    missing = _missing_keys(coverage, _COVERAGE_KEYS)
    if missing:
        raise ValueError(f"coverage missing required keys: {', '.join(missing)}")
    if not isinstance(coverage["funnel"], dict):
        raise TypeError("coverage funnel must be a dict")
    missing_funnel = _missing_keys(coverage["funnel"], _FUNNEL_KEYS)
    if missing_funnel:
        raise ValueError(f"coverage funnel missing required keys: {', '.join(missing_funnel)}")
    normalized = _json_safe(copy.deepcopy(coverage))
    normalized["trade_date"] = trade_date
    return normalized


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8")
    _fsync_file(path)


def _write_text(text: str, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass


def _fsync_file(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


def _display(value: Any, *, percent: bool = False) -> str:
    if value is None or value is pd.NA:
        return "数据缺失"
    try:
        if pd.isna(value):
            return "数据缺失"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return "数据缺失"
    if percent and isinstance(value, (int, float, np.integer, np.floating)):
        return f"{float(value):.1%}"
    text = str(value).strip()
    return text if text else "数据缺失"


def _escape_table(value: Any) -> str:
    return _display(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _valid_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(char in url for char in "\r\n"):
        return None
    return url


def _source_link(row: pd.Series) -> str:
    title = _escape_table(row.get("source_title"))
    url = _valid_url(row.get("source_url"))
    if url is None:
        return title
    return f"[{title}](<{url}>)"


def _coverage_table(coverage: dict[str, Any]) -> list[str]:
    labels = {
        "raw_assets": "原始资产",
        "consumer_universe": "消费候选池",
        "market_eligible": "市场条件合格",
        "oversold_eligible": "超跌条件合格",
        "hard_risk_clear": "硬风险通过",
        "evidence_complete": "证据完整",
        "valuation_eligible": "估值条件合格",
        "selected_expected": "纯预期修复入选",
        "selected_early": "初步验证入选",
    }
    lines = ["| 漏斗阶段 | 数量 |", "|---|---:|"]
    lines.extend(
        f"| {labels[key]} | {_escape_table(coverage['funnel'][key])} |" for key in _FUNNEL_KEYS
    )
    for label, key in (
        ("估值历史覆盖", "valuation_history_coverage"),
        ("财务历史覆盖", "finance_history_coverage"),
    ):
        lines.append(f"| {label} | {_escape_table(json.dumps(coverage[key], ensure_ascii=False, sort_keys=True))} |")
    return lines


def _candidate_section(title: str, frame: pd.DataFrame) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    for _, row in frame.iterrows():
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        lines.extend(
            [
                f"### {_escape_table(name)}（{_escape_table(code)}）",
                "",
                f"- 行业分类：{_escape_table(row.get('consumer_subindustry'))}",
                (
                    "- 跌幅：6个月 "
                    f"{_display(row.get('return_6m'), percent=True)}；12个月最大回撤 "
                    f"{_display(row.get('max_drawdown_12m'), percent=True)}；相对收益 "
                    f"{_display(row.get('relative_return_6m'), percent=True)}"
                ),
                (
                    f"- 估值：{_escape_table(row.get('valuation_method'))}；分位 "
                    f"{_display(row.get('valuation_percentile'), percent=True)}；三情景 "
                    f"{_display(row.get('pessimistic_upside'), percent=True)} / "
                    f"{_display(row.get('base_upside'), percent=True)} / "
                    f"{_display(row.get('optimistic_upside'), percent=True)}"
                ),
                f"- 修复逻辑：{_escape_table(row.get('repair_thesis'))}",
                f"- 未修复指标：{_escape_table(row.get('unrepaired_metrics'))}",
                f"- 领先指标：{_escape_table(row.get('leading_indicator'))}",
                f"- 下一验证日：{_escape_table(row.get('expected_validation_date'))}",
                f"- 来源：{_source_link(row)}（{_escape_table(row.get('source_publish_date'))}）",
                f"- 主要风险：{_escape_table(row.get('main_risks'))}",
                f"- 失效条件：{_escape_table(row.get('invalidation_conditions'))}",
                (
                    "- 评分：经营缺口 "
                    f"{_escape_table(row.get('operating_gap_score'))}；修复潜力 "
                    f"{_escape_table(row.get('repair_potential_score'))}；估值修复 "
                    f"{_escape_table(row.get('valuation_repair_score'))}；超跌 "
                    f"{_escape_table(row.get('oversold_score'))}；资产负债表 "
                    f"{_escape_table(row.get('balance_sheet_score'))}；催化可验证性 "
                    f"{_escape_table(row.get('catalyst_verifiability_score'))}；已定价扣分 "
                    f"{_escape_table(row.get('priced_in_penalty'))}；综合分 "
                    f"{_escape_table(row.get('composite_score'))}"
                ),
                "",
            ]
        )
    return lines


def _exclusion_summary(frame: pd.DataFrame) -> list[str]:
    lines = ["## 剔除原因摘要", ""]
    if frame.empty or "exclusion_reasons" not in frame.columns:
        return [*lines, "暂无剔除记录。", ""]
    reasons: list[str] = []
    for value in frame["exclusion_reasons"].dropna():
        reasons.extend(part.strip() for part in str(value).split("|") if part.strip())
    if not reasons:
        return [*lines, "暂无可统计的剔除原因。", ""]
    counts = pd.Series(reasons).value_counts(sort=False).sort_index()
    lines.extend(["| 原因 | 数量 |", "|---|---:|"])
    lines.extend(f"| {_escape_table(reason)} | {count} |" for reason, count in counts.items())
    return [*lines, ""]


def _render_report(
    trade_date: str,
    expected: pd.DataFrame,
    early: pd.DataFrame,
    exclusions: pd.DataFrame,
    coverage: dict[str, Any],
) -> str:
    lines = [
        f"# 消费超跌修复候选周报（{trade_date}）",
        "",
        "> 方法声明：本报告仅提供研究候选，不是交易指令。",
        "",
        "## 数据覆盖",
        "",
        *_coverage_table(coverage),
        "",
        "### 数据日期上限与缺失字段",
        "",
        f"- 数据日期上限：{_escape_table(json.dumps(coverage['data_date_maxima'], ensure_ascii=False, sort_keys=True))}",
        f"- 缺失字段计数：{_escape_table(json.dumps(coverage['missing_field_counts'], ensure_ascii=False, sort_keys=True))}",
        "",
        *_candidate_section("纯预期修复", expected),
        *_candidate_section("初步验证但尚未充分定价", early),
        *_exclusion_summary(exclusions),
        "## 警告",
        "",
    ]
    warnings = coverage["warnings"]
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {_escape_table(warning)}" for warning in warnings)
    else:
        lines.append("- 无")
    return "\n".join(lines).rstrip() + "\n"


def _publish_set(staged: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    backup = staged.parent / "backup"
    backup.mkdir()
    targets = {key: output_dir / filename for key, filename in OUTPUT_FILENAMES.items()}
    backed_up: list[str] = []
    promoted: list[str] = []
    try:
        for key, target in targets.items():
            if target.exists():
                os.replace(target, backup / target.name)
                backed_up.append(key)
        for key, target in targets.items():
            os.replace(staged / target.name, target)
            promoted.append(key)
    except BaseException:
        rollback_errors: list[OSError] = []
        for key in promoted:
            try:
                targets[key].unlink(missing_ok=True)
            except OSError as error:
                rollback_errors.append(error)
        for key in backed_up:
            try:
                os.replace(backup / targets[key].name, targets[key])
            except OSError as error:
                rollback_errors.append(error)
        if rollback_errors:
            raise RuntimeError("artifact publication failed and rollback was incomplete") from rollback_errors[0]
        raise


def write_consumer_oversold_artifacts(
    payload: dict[str, Any], *, output_dir: str | Path
) -> dict[str, Any]:
    """Validate, render, and atomically publish consumer oversold research artifacts."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    missing = _missing_keys(payload, _PAYLOAD_KEYS)
    if missing:
        raise ValueError(f"payload missing required keys: {', '.join(missing)}")
    trade_date = validate_trade_date(payload["trade_date"])
    frames: dict[str, pd.DataFrame] = {}
    for key in _FRAME_KEYS:
        frame = payload[key]
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{key} must be a pandas DataFrame")
        frames[key] = _ordered_frame(frame)
    expected_assets = _validate_selected(frames["expected"], "expected")
    early_assets = _validate_selected(frames["early"], "early")
    if expected_assets & early_assets:
        raise ValueError("expected and early asset sets must be mutually exclusive")
    if not isinstance(payload["coverage"], dict):
        raise TypeError("coverage must be a dict")
    coverage = _normalize_coverage(payload["coverage"], trade_date)
    report = _render_report(
        trade_date,
        frames["expected"],
        frames["early"],
        frames["exclusions"],
        coverage,
    )

    destination = Path(output_dir).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    staged = staging_root / "new"
    staged.mkdir()
    try:
        for key in _FRAME_KEYS:
            _write_csv(frames[key], staged / OUTPUT_FILENAMES[key])
        _write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
            staged / OUTPUT_FILENAMES["coverage"],
        )
        _write_text(report, staged / OUTPUT_FILENAMES["report"])
        _publish_set(staged, destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    paths = {key: str(destination / filename) for key, filename in OUTPUT_FILENAMES.items()}
    return {
        "paths": paths,
        "expected": frames["expected"],
        "early": frames["early"],
        "scores": frames["scores"],
        "exclusions": frames["exclusions"],
        "coverage": coverage,
        "report": report,
    }
