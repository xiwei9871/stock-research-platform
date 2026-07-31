from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import uuid
from datetime import date, datetime
from pathlib import Path, PurePath
from typing import Any

import numpy as np
import pandas as pd

from .contracts import UNIFIED_OUTPUT_FILENAMES, validate_trade_date
from .evidence import OUTPUT_COLUMNS as EVIDENCE_OUTPUT_COLUMNS
from .evidence import _valid_source_url


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

_FRAME_KEYS = (
    "evidence",
    "scores",
    "exclusions",
    "top20",
    "reserve",
    "preaudit",
    "comparison",
)
_PAYLOAD_KEYS = ("trade_date", *_FRAME_KEYS, "coverage")
_COVERAGE_KEYS = (
    "funnel",
    "data_date_maxima",
    "missing_field_counts",
    "warnings",
    "valuation_history_coverage",
    "finance_history_coverage",
    "unified_funnel",
    "publication_status",
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
    "eligible": True,
    "elasticity_coverage": True,
}
_UNIFIED_FUNNEL_KEYS = (
    "full",
    "automatic",
    "preaudit",
    "evidence_reviewed",
    "evidence_complete",
    "elasticity_complete",
    "final",
    "reserve",
)
_PUBLICATION_STATUSES = {"ready", "coverage_insufficient", "preaudit_only"}
_STAGING_PREFIX = ".consumer-oversold-staging-"
_TEMP_LINK_PREFIX = ".consumer-oversold-current-tmp-"
_RELEASE_PREFIX = "consumer-oversold-"


def _missing_keys(mapping: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if key not in mapping]


def _ordered_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if result.empty and "asset_id" not in result.columns:
        result = result.reindex(columns=["asset_id", *result.columns])
    preferred = [column for column in REPORT_COLUMNS if column in result.columns]
    extras = sorted(column for column in result.columns if column not in preferred)
    return result.loc[:, [*preferred, *extras]]


def _ordered_evidence_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    missing = [column for column in EVIDENCE_OUTPUT_COLUMNS if column not in result.columns]
    if missing:
        raise ValueError(f"evidence missing validated columns: {', '.join(missing)}")
    preferred = [column for column in EVIDENCE_OUTPUT_COLUMNS if column in result.columns]
    extras = sorted(column for column in result.columns if column not in preferred)
    return result.loc[:, [*preferred, *extras]]


def _validate_assets(frame: pd.DataFrame, name: str) -> tuple[list[str], set[str]]:
    if frame.empty:
        return [], set()
    if "asset_id" not in frame.columns:
        raise ValueError(f"{name} missing required columns: asset_id")
    missing = frame["asset_id"].isna()
    normalized = frame["asset_id"].astype(str).str.strip()
    if (missing | normalized.eq("")).any():
        raise ValueError(f"{name} asset_id must be non-empty")
    if normalized.duplicated().any():
        raise ValueError(f"{name} asset_id must be unique")
    return normalized.tolist(), set(normalized)


def _validate_selected(
    frame: pd.DataFrame,
    name: str,
    expected_ranks: range,
) -> set[str]:
    if frame.empty:
        return set()
    required_columns = ("asset_id", "final_rank", *_SELECTED_GATES)
    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"{name} missing required columns: {', '.join(missing_columns)}")
    _, assets = _validate_assets(frame, name)
    ranks: list[int] = []
    for value in frame["final_rank"]:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} field final_rank must contain strict integers")
        ranks.append(int(value))
    if ranks != list(expected_ranks):
        raise ValueError(f"{name} final_rank must equal {list(expected_ranks)}")
    for field, required in _SELECTED_GATES.items():
        valid = frame[field].map(
            lambda value: isinstance(value, (bool, np.bool_)) and bool(value) is required
        )
        if not valid.all():
            raise ValueError(f"{name} field {field} must be {str(required).lower()}")
    return assets


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


def _positive_size(coverage: dict[str, Any], key: str, default: int) -> int:
    value = coverage.get(key, default)
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"coverage {key} must be an integer")
    if int(value) < 1:
        raise ValueError(f"coverage {key} must be positive")
    return int(value)


def _normalize_coverage(
    coverage: dict[str, Any],
    trade_date: str,
    *,
    top20_count: int,
    reserve_count: int,
    preaudit_count: int,
) -> dict[str, Any]:
    missing = _missing_keys(coverage, _COVERAGE_KEYS)
    if missing:
        raise ValueError(f"coverage missing required keys: {', '.join(missing)}")
    if not isinstance(coverage["funnel"], dict):
        raise TypeError("coverage funnel must be a dict")
    missing_funnel = _missing_keys(coverage["funnel"], _FUNNEL_KEYS)
    if missing_funnel:
        raise ValueError(f"coverage funnel missing required keys: {', '.join(missing_funnel)}")
    for key in _FUNNEL_KEYS:
        value = coverage["funnel"][key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise TypeError(f"coverage funnel {key} must be an integer")
        if int(value) < 0:
            raise ValueError(f"coverage funnel {key} must be non-negative")
    ordered = [int(coverage["funnel"][key]) for key in _FUNNEL_KEYS[:7]]
    if any(left < right for left, right in zip(ordered, ordered[1:])):
        raise ValueError("coverage funnel counts must be non-increasing")
    selected_expected = int(coverage["funnel"]["selected_expected"])
    selected_early = int(coverage["funnel"]["selected_early"])
    if ordered[-1] < selected_expected + selected_early:
        raise ValueError(
            "coverage valuation_eligible must be at least selected_expected + selected_early"
        )
    if not isinstance(coverage["unified_funnel"], dict):
        raise TypeError("coverage unified_funnel must be a dict")
    missing_unified = _missing_keys(coverage["unified_funnel"], _UNIFIED_FUNNEL_KEYS)
    if missing_unified:
        raise ValueError(
            f"coverage unified_funnel missing required keys: {', '.join(missing_unified)}"
        )
    for key in _UNIFIED_FUNNEL_KEYS:
        value = coverage["unified_funnel"][key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise TypeError(f"coverage unified_funnel {key} must be an integer")
        if int(value) < 0:
            raise ValueError(f"coverage unified_funnel {key} must be non-negative")
    unified = {
        key: int(coverage["unified_funnel"][key]) for key in _UNIFIED_FUNNEL_KEYS
    }
    if not unified["full"] >= unified["automatic"] >= unified["preaudit"]:
        raise ValueError(
            "coverage unified_funnel must satisfy full >= automatic >= preaudit"
        )
    if not (
        unified["preaudit"]
        >= unified["evidence_reviewed"]
        >= unified["evidence_complete"]
    ):
        raise ValueError(
            "coverage unified_funnel must satisfy "
            "preaudit >= evidence_reviewed >= evidence_complete"
        )
    if unified["preaudit"] < unified["elasticity_complete"]:
        raise ValueError(
            "coverage unified_funnel preaudit must be at least elasticity_complete"
        )
    if unified["evidence_complete"] < unified["elasticity_complete"]:
        raise ValueError(
            "coverage unified_funnel evidence_complete must be at least "
            "elasticity_complete"
        )
    status = coverage["publication_status"]
    if status not in _PUBLICATION_STATUSES:
        raise ValueError(
            "coverage publication_status must be ready, coverage_insufficient, "
            "or preaudit_only"
        )
    final_top_n = _positive_size(coverage, "final_top_n", 20)
    reserve_top_n = _positive_size(coverage, "reserve_top_n", 20)
    preaudit_size = _positive_size(coverage, "preaudit_size", 60)
    minimum_evidence_complete = _positive_size(
        coverage, "minimum_evidence_complete", final_top_n + reserve_top_n
    )
    if preaudit_size < final_top_n + reserve_top_n:
        raise ValueError("coverage preaudit_size must cover final_top_n plus reserve_top_n")
    if minimum_evidence_complete < final_top_n + reserve_top_n:
        raise ValueError(
            "coverage minimum_evidence_complete must cover final_top_n plus reserve_top_n"
        )
    if minimum_evidence_complete > preaudit_size:
        raise ValueError(
            "coverage minimum_evidence_complete must not exceed preaudit_size"
        )
    if preaudit_count > preaudit_size:
        raise ValueError("preaudit frame length must not exceed coverage preaudit_size")
    if status == "ready":
        if top20_count != final_top_n:
            raise ValueError("ready publication top20 length must equal final_top_n")
        if reserve_count != reserve_top_n:
            raise ValueError("ready publication reserve length must equal reserve_top_n")
        selected_count = top20_count + reserve_count
        if unified["evidence_complete"] < minimum_evidence_complete:
            raise ValueError(
                "ready publication evidence_complete must meet minimum_evidence_complete"
            )
        if unified["evidence_complete"] < selected_count:
            raise ValueError(
                "ready publication evidence_complete must cover final plus reserve"
            )
        if unified["elasticity_complete"] < selected_count:
            raise ValueError(
                "ready publication elasticity_complete must cover final plus reserve"
            )
    elif top20_count or reserve_count:
        raise ValueError("coverage_insufficient publication must not publish ranked selections")
    if unified["preaudit"] != preaudit_count:
        raise ValueError("coverage unified_funnel preaudit must equal preaudit frame length")
    if unified["final"] != top20_count:
        raise ValueError("coverage unified_funnel final must equal top20 frame length")
    if unified["reserve"] != reserve_count:
        raise ValueError("coverage unified_funnel reserve must equal reserve frame length")
    normalized = _json_safe(copy.deepcopy(coverage))
    normalized["trade_date"] = trade_date
    normalized.update(
        final_top_n=final_top_n,
        reserve_top_n=reserve_top_n,
        preaudit_size=preaudit_size,
        minimum_evidence_complete=minimum_evidence_complete,
    )
    warning = (
        "publication_thresholds: "
        f"final_top_n={final_top_n}, reserve_top_n={reserve_top_n}, "
        f"preaudit_size={preaudit_size}, "
        f"minimum_evidence_complete={minimum_evidence_complete}"
    )
    warnings = normalized["warnings"]
    if not isinstance(warnings, list):
        raise TypeError("coverage warnings must be a list")
    normalized["warnings"] = [*warnings, warning] if warning not in warnings else warnings
    return normalized


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    safe = frame.copy(deep=True)
    for column in safe.columns:
        safe[column] = safe[column].map(_escape_csv_formula)
    safe.to_csv(path, index=False, encoding="utf-8")
    _fsync_file(path)


def _write_text(text: str, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _dir_fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _escape_csv_formula(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


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


def _escape_markdown_text(value: Any) -> str:
    text = _display(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("\\", "\\\\")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in "[]()!*_`#":
        text = text.replace(character, f"\\{character}")
    return text.replace("|", "\\|")


def _escape_table(value: Any) -> str:
    return _escape_markdown_text(value)


def _escape_link_label(value: Any) -> str:
    return _escape_markdown_text(value)


def _percent_text(value: Any) -> str:
    return _escape_markdown_text(_display(value, percent=True))


def _score_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number):
            return f"{number:.1f}"
    return _escape_markdown_text(value)


def _market_cap_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number):
            return f"{number / 100_000_000:.2f} 亿元"
    return "数据缺失"


def _count_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number) and number.is_integer():
            return str(int(number))
    return _escape_markdown_text(value)


def _enrich_rows(primary: pd.DataFrame, supplemental: pd.DataFrame | None) -> pd.DataFrame:
    result = primary.copy(deep=True)
    if (
        result.empty
        or supplemental is None
        or supplemental.empty
        or "asset_id" not in result.columns
        or "asset_id" not in supplemental.columns
    ):
        return result
    lookup = supplemental.drop_duplicates("asset_id", keep="first").set_index("asset_id")
    missing_columns = [column for column in lookup.columns if column not in result.columns]
    if missing_columns:
        additions = lookup.reindex(result["asset_id"])[missing_columns].reset_index(drop=True)
        additions.index = result.index
        result = pd.concat([result, additions], axis=1)
    for column in (column for column in lookup.columns if column in primary.columns):
        mapped = result["asset_id"].map(lookup[column])
        result[column] = result[column].where(result[column].notna(), mapped)
    return result


def _valid_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value
    if (
        not url
        or url != url.strip()
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)
        or "<" in url
        or ">" in url
    ):
        return None
    if not _valid_source_url(url):
        return None
    return url


def _source_link(row: pd.Series) -> str:
    title = _escape_link_label(row.get("source_title"))
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
    unified_labels = {
        "full": "完整评分池",
        "automatic": "自动门槛通过",
        "preaudit": "审计前候选",
        "evidence_reviewed": "证据已审阅",
        "evidence_complete": "证据完整（审计前）",
        "elasticity_complete": (
            "启动数据完整"
            if coverage.get("ranking_version") == "v2"
            else "弹性数据完整"
        ),
        "final": "最终榜单",
        "reserve": "储备榜单",
    }
    lines.extend(
        f"| {unified_labels[key]} | {_escape_table(coverage['unified_funnel'][key])} |"
        for key in _UNIFIED_FUNNEL_KEYS
    )
    for label, key in (
        ("估值历史覆盖", "valuation_history_coverage"),
        ("财务历史覆盖", "finance_history_coverage"),
    ):
        lines.append(f"| {label} | {_escape_table(json.dumps(coverage[key], ensure_ascii=False, sort_keys=True))} |")
    return lines


def _candidate_section(
    title: str,
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    for _, row in frame.iterrows():
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        score_detail = (
            (
                "- 启动评分：技术启动 "
                f"{_score_text(row.get('technical_readiness_score'))}；历史延续 "
                f"{_score_text(row.get('continuation_character_score'))}；剩余空间 "
                f"{_score_text(row.get('residual_price_space_score'))}；资金效率 "
                f"{_score_text(row.get('capital_efficiency_score'))}；催化时间 "
                f"{_score_text(row.get('catalyst_timing_score'))}；3—5日启动 "
                f"{_score_text(row.get('activation_score'))}"
            )
            if ranking_version == "v2"
            else (
                "- 弹性评分：残差偏离 "
                f"{_score_text(row.get('residual_deviation_score'))}；股票特性 "
                f"{_score_text(row.get('stock_character_score'))}；市场容量 "
                f"{_score_text(row.get('market_capacity_score'))}；催化流动性 "
                f"{_score_text(row.get('catalyst_liquidity_score'))}；反弹弹性 "
                f"{_score_text(row.get('elasticity_score'))}"
            )
        )
        lines.extend(
            [
                f"### {_escape_table(name)}（{_escape_table(code)}）",
                "",
                f"- 行业分类：{_escape_table(row.get('consumer_subindustry'))}",
                (
                    "- 跌幅：6个月 "
                    f"{_percent_text(row.get('return_6m'))}；12个月最大回撤 "
                    f"{_percent_text(row.get('max_drawdown_12m'))}；相对收益 "
                    f"{_percent_text(row.get('relative_return_6m'))}"
                ),
                (
                    f"- 估值：{_escape_table(row.get('valuation_method'))}；分位 "
                    f"{_percent_text(row.get('valuation_percentile'))}；三情景 "
                    f"{_percent_text(row.get('pessimistic_upside'))} / "
                    f"{_percent_text(row.get('base_upside'))} / "
                    f"{_percent_text(row.get('optimistic_upside'))}"
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
                (
                    "- 真实市值：总市值 "
                    f"{_market_cap_text(row.get('current_total_market_cap'))}；流通市值 "
                    f"{_market_cap_text(row.get('current_float_market_cap'))}；来源 "
                    f"{_escape_table(row.get('market_cap_source'))}"
                ),
                (
                    "- 大涨特征：涨停 "
                    f"{_count_text(row.get('limit_up_count_2y'))} 次；上涨超过7% "
                    f"{_count_text(row.get('up_7pct_count_2y'))} 次；上涨超过5% "
                    f"{_count_text(row.get('up_5pct_count_2y'))} 次；大涨后正收益率 "
                    f"1日 {_percent_text(row.get('positive_after_big_up_1d_rate'))}；"
                    f"3日 {_percent_text(row.get('positive_after_big_up_3d_rate'))}；"
                    f"5日 {_percent_text(row.get('positive_after_big_up_5d_rate'))}"
                ),
                (
                    "- 位置与反弹：1年回撤 "
                    f"{_percent_text(row.get('drawdown_from_high_1y'))}；2年回撤 "
                    f"{_percent_text(row.get('drawdown_from_high_2y'))}；1年位置 "
                    f"{_percent_text(row.get('price_position_1y'))}；2年位置 "
                    f"{_percent_text(row.get('price_position_2y'))}；MA120 "
                    f"{_percent_text(row.get('distance_hfq_ma120'))}；MA250 "
                    f"{_percent_text(row.get('distance_hfq_ma250'))}；60日反弹 "
                    f"{_percent_text(row.get('rebound_from_low_60d'))}；120日反弹 "
                    f"{_percent_text(row.get('rebound_from_low_120d'))}"
                ),
                score_detail,
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


def _ranking_table(
    title: str,
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    score_label = "启动分位" if ranking_version == "v2" else "弹性分位"
    score_field = (
        "activation_rank_percentile"
        if ranking_version == "v2"
        else "elasticity_rank_percentile"
    )
    final_field = (
        "final_rank_score_v2" if ranking_version == "v2" else "final_rank_score"
    )
    lines.extend(
        [
            f"| 排名 | 股票 | 修复分位 | {score_label} | 最终排名分 |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for _, row in frame.iterrows():
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        lines.append(
            f"| {_escape_table(row.get('final_rank'))} | "
            f"{_escape_table(name)}（{_escape_table(code)}） | "
            f"{_score_text(row.get('repair_rank_percentile'))} | "
            f"{_score_text(row.get(score_field))} | "
            f"{_score_text(row.get(final_field))} |"
        )
    return [*lines, ""]


def _preaudit_table(frame: pd.DataFrame) -> list[str]:
    lines = ["## 审计前 Top 60", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    lines.extend(
        [
            "| 预审排名 | 股票 | 预审分 | 修复潜力 | 自动弹性分 | 证据状态 |",
            "|---:|---|---:|---:|---:|---|",
        ]
    )
    for preaudit_rank, (_, row) in enumerate(frame.iterrows(), start=1):
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        evidence_complete = row.get("evidence_complete")
        evidence_status = (
            "证据完整"
            if isinstance(evidence_complete, (bool, np.bool_))
            and bool(evidence_complete)
            else "证据不完整"
        )
        lines.append(
            f"| {preaudit_rank} | {_escape_table(name)}（{_escape_table(code)}） | "
            f"{_score_text(row.get('preaudit_score'))} | "
            f"{_score_text(row.get('repair_potential_score'))} | "
            f"{_score_text(row.get('automatic_elasticity_score'))} | "
            f"{evidence_status} |"
        )
    return [*lines, ""]


def _comparison_table(frame: pd.DataFrame) -> list[str]:
    lines = ["## 新旧排名对照", ""]
    if frame.empty:
        return [*lines, "暂无对照记录。", ""]
    lines.extend(["| 股票 | 旧排名 | 新排名 | 变化 |", "|---|---:|---:|---:|"])
    for _, row in frame.iterrows():
        old_rank = row.get(
            "old_combined_rank", row.get("old_rank", row.get("v1_rank"))
        )
        lines.append(
            f"| {_escape_table(row.get('stock_name', row.get('asset_id')))} | "
            f"{_escape_table(old_rank)} | "
            f"{_escape_table(row.get('new_rank', row.get('v2_rank')))} | "
            f"{_escape_table(row.get('rank_change'))} |"
        )
    return [*lines, ""]


_FIXED_SPECIAL_STOCKS = (
    ("600418", "江淮汽车"),
    ("600702", "舍得酒业"),
    ("601127", "赛力斯"),
)


def _meaningful(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return not isinstance(value, str) or bool(value.strip())


def _find_special_stock(frame: pd.DataFrame, code: str, name: str) -> pd.Series | None:
    if frame.empty:
        return None
    matched = pd.Series(False, index=frame.index)
    if "stock_code" in frame.columns:
        matched |= frame["stock_code"].astype(str).str.split(".").str[0].eq(code)
    if "asset_id" in frame.columns:
        matched |= frame["asset_id"].astype(str).str.split(".").str[0].eq(code)
    if "stock_name" in frame.columns:
        matched |= frame["stock_name"].astype(str).str.strip().eq(name)
    if not matched.any():
        return None
    return frame.loc[matched].iloc[0]


def _special_stock_comparison(
    comparison: pd.DataFrame,
    scores: pd.DataFrame | None,
    top20: pd.DataFrame,
    reserve: pd.DataFrame,
    preaudit: pd.DataFrame,
) -> list[str]:
    lines = ["## 江淮汽车、舍得酒业、赛力斯对照", ""]
    sources = (comparison, scores, top20, reserve, preaudit)
    for code, name in _FIXED_SPECIAL_STOCKS:
        combined: dict[str, Any] = {}
        found = False
        in_preaudit = _find_special_stock(preaudit, code, name) is not None
        for source in sources:
            if source is None:
                continue
            row = _find_special_stock(source, code, name)
            if row is None:
                continue
            found = True
            for field, value in row.items():
                if field not in combined and _meaningful(value):
                    combined[field] = value
        lines.extend([f"### {name}（{code}）", ""])
        lines.append(
            "- 审计状态：已进入本期终端消费审计。"
            if in_preaudit
            else "- 审计状态：未进入本期终端消费审计。"
        )
        if not found:
            lines.extend(["- 无可用排名。", ""])
            continue
        old_rank = combined.get(
            "old_combined_rank", combined.get("old_rank", combined.get("v1_rank"))
        )
        new_rank = combined.get(
            "new_rank", combined.get("v2_rank", combined.get("final_rank"))
        )
        rank_change = combined.get("rank_change")
        rank_parts = []
        if _meaningful(old_rank):
            rank_parts.append(f"旧排名 {_count_text(old_rank)}")
        if _meaningful(new_rank):
            rank_parts.append(f"新排名 {_count_text(new_rank)}")
        if _meaningful(rank_change):
            rank_parts.append(f"排名变化 {_count_text(rank_change)}")
        lines.append(f"- {'；'.join(rank_parts)}" if rank_parts else "- 无可用排名。")
        reasons = combined.get(
            "exclusion_reasons", combined.get("automatic_exclusion_reasons")
        )
        if _meaningful(reasons):
            lines.append(f"- 状态/剔除原因：{_escape_table(reasons)}")
        else:
            lines.append("- 状态/剔除原因：无明确剔除原因。")
        lines.append("")
    return lines


def _render_report(
    trade_date: str,
    top20: pd.DataFrame,
    reserve: pd.DataFrame,
    preaudit: pd.DataFrame,
    comparison: pd.DataFrame,
    exclusions: pd.DataFrame,
    coverage: dict[str, Any],
    scores: pd.DataFrame | None = None,
) -> str:
    ranking_version = str(coverage.get("ranking_version", "v1"))
    candidate_details = _enrich_rows(
        pd.concat([top20, reserve], ignore_index=True), scores
    )
    methodology_lines = (
        [
            "> 单一排名公式：修复潜力 55% + 3—5日启动 45%。",
            "",
            (
                "> 3—5日启动分：技术启动 30% + 历史延续 25% + "
                "剩余价格空间 20% + 资金推动效率 15% + 催化时间 10%。"
            ),
        ]
        if ranking_version == "v2"
        else ["> 单一排名公式：修复潜力 70% + 反弹弹性 30%。"]
    )
    lines = [
        f"# 消费超跌修复候选周报（{trade_date}）",
        "",
        "> 方法声明：本报告仅提供研究候选，不是交易指令。",
        "",
        "> CSV 为审阅安全转义：疑似公式的文本单元格已加单引号前缀。",
        "",
        *methodology_lines,
        "",
        f"> 发布状态：{_escape_table(coverage['publication_status'])}",
        "",
        *(
            ["> **仅预审，不是正式Top20。**", ""]
            if coverage["publication_status"] == "preaudit_only"
            else []
        ),
        "## 数据覆盖",
        "",
        *_coverage_table(coverage),
        "",
        "### 数据日期上限与缺失字段",
        "",
        f"- 数据日期上限：{_escape_table(json.dumps(coverage['data_date_maxima'], ensure_ascii=False, sort_keys=True))}",
        f"- 缺失字段计数：{_escape_table(json.dumps(coverage['missing_field_counts'], ensure_ascii=False, sort_keys=True))}",
        "",
        *_ranking_table(
            "最终统一榜单 Top 20", top20, ranking_version=ranking_version
        ),
        *_ranking_table(
            "储备榜单 21-40", reserve, ranking_version=ranking_version
        ),
        *_preaudit_table(preaudit),
        *_comparison_table(comparison),
        *_candidate_section(
            "候选详情", candidate_details, ranking_version=ranking_version
        ),
        *_special_stock_comparison(comparison, scores, top20, reserve, preaudit),
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


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        path.chmod(0o755)
        shutil.rmtree(path)


def _cleanup_stale(output_dir: Path, releases_dir: Path) -> None:
    for path in releases_dir.glob(f"{_STAGING_PREFIX}*"):
        _remove_path(path)
    for path in output_dir.glob(f"{_TEMP_LINK_PREFIX}*"):
        _remove_path(path)


def _restore_current(output_dir: Path, old_target: str | None) -> None:
    current = output_dir / "current"
    if old_target is None:
        current.unlink(missing_ok=True)
        return
    recovery = output_dir / f"{_TEMP_LINK_PREFIX}recovery-{uuid.uuid4().hex}"
    try:
        os.symlink(old_target, recovery)
        os.replace(recovery, current)
    finally:
        recovery.unlink(missing_ok=True)


def _open_directory_no_follow(path: Path, name: str) -> int:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o755)
        except FileExistsError:
            pass
        metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{name} must be a real directory, not a symlink")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{name} must be a real directory, not a symlink") from exc
    opened = os.fstat(descriptor)
    current = os.lstat(path)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        os.close(descriptor)
        raise ValueError(f"{name} changed during validation")
    return descriptor


def _verify_directory_identity(path: Path, descriptor: int, name: str) -> None:
    opened = os.fstat(descriptor)
    current = os.lstat(path)
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise ValueError(f"{name} changed during publication")


def _validated_current_target(
    current: Path, output_dir: Path, releases_dir: Path
) -> str | None:
    if not current.is_symlink():
        if current.exists():
            raise ValueError("output_dir/current must be a symlink managed by this publisher")
        return None
    target = os.readlink(current)
    pure_target = PurePath(target)
    parts = pure_target.parts
    if (
        pure_target.is_absolute()
        or len(parts) != 2
        or parts[0] != ".releases"
        or not parts[1].startswith(_RELEASE_PREFIX)
        or parts[1] == _RELEASE_PREFIX
        or ".." in parts
    ):
        raise ValueError("output_dir/current target is not a managed relative release")
    release = output_dir.joinpath(*parts)
    try:
        metadata = os.lstat(release)
        resolved_release = release.resolve(strict=True)
        resolved_releases = releases_dir.resolve(strict=True)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise ValueError("output_dir/current target must be an existing managed release") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved_release.parent != resolved_releases
    ):
        raise ValueError("output_dir/current target must be a real managed release directory")
    return target


def _open_publish_lock(path: Path):
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError("output_dir/.publish.lock must be a regular file, not a symlink") from exc
    try:
        opened = os.fstat(descriptor)
        current = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError("output_dir/.publish.lock must be a regular file, not a symlink")
        return os.fdopen(descriptor, "a+b")
    except BaseException:
        os.close(descriptor)
        raise


def _artifact_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_and_verify_manifest(release: Path) -> Path:
    manifest = release / ".manifest.sha256"
    lines = [
        f"{_artifact_digest(release / filename)}  {filename}"
        for filename in sorted(UNIFIED_OUTPUT_FILENAMES.values())
    ]
    _write_text("\n".join(lines) + "\n", manifest)
    parsed: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", 1)
        parsed[filename] = digest
    expected_names = sorted(UNIFIED_OUTPUT_FILENAMES.values())
    if list(parsed) != expected_names or any(
        parsed[filename] != _artifact_digest(release / filename) for filename in expected_names
    ):
        raise ValueError("release manifest verification failed")
    return manifest


def _seal_release(release: Path, manifest: Path) -> None:
    for filename in (*UNIFIED_OUTPUT_FILENAMES.values(), manifest.name):
        artifact = release / filename
        artifact.chmod(0o444)
        _fsync_file(artifact)
    release.chmod(0o555)
    _dir_fsync(release)


def _publish_release(
    output_dir: Path,
    frames: dict[str, pd.DataFrame],
    coverage: dict[str, Any],
    report: str,
) -> None:
    releases_dir = output_dir / ".releases"
    releases_descriptor = _open_directory_no_follow(
        releases_dir, "output_dir/.releases"
    )
    try:
        _verify_directory_identity(
            releases_dir, releases_descriptor, "output_dir/.releases"
        )
        current = output_dir / "current"
        old_target = _validated_current_target(current, output_dir, releases_dir)
        _cleanup_stale(output_dir, releases_dir)
        identifier = uuid.uuid4().hex
        staging = releases_dir / f"{_STAGING_PREFIX}{identifier}"
        release = releases_dir / f"{_RELEASE_PREFIX}{identifier}"
        temp_link = output_dir / f"{_TEMP_LINK_PREFIX}{identifier}"
        switched = False
        preserve_release = False
        staging.mkdir()
        try:
            for key in _FRAME_KEYS:
                _write_csv(frames[key], staging / UNIFIED_OUTPUT_FILENAMES[key])
            _write_text(
                json.dumps(
                    coverage, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
                )
                + "\n",
                staging / UNIFIED_OUTPUT_FILENAMES["coverage"],
            )
            _write_text(report, staging / UNIFIED_OUTPUT_FILENAMES["report"])
            manifest = _write_and_verify_manifest(staging)
            _seal_release(staging, manifest)
            _verify_directory_identity(
                releases_dir, releases_descriptor, "output_dir/.releases"
            )
            os.replace(staging, release)
            _dir_fsync(releases_dir)
            relative_target = str(Path(".releases") / release.name)
            os.symlink(relative_target, temp_link)
            _dir_fsync(output_dir)
            os.replace(temp_link, current)
            switched = True
            try:
                _dir_fsync(output_dir)
            except OSError as publication_error:
                try:
                    _restore_current(output_dir, old_target)
                    _dir_fsync(output_dir)
                except BaseException as rollback_error:
                    preserve_release = True
                    failure = RuntimeError(
                        f"artifact publication failed and rollback incomplete: {rollback_error}"
                    )
                    raise failure from publication_error
                switched = False
                raise
        finally:
            _remove_path(staging)
            temp_link.unlink(missing_ok=True)
            if not switched and not preserve_release:
                _remove_path(release)
    finally:
        os.close(releases_descriptor)


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
        frames[key] = _ordered_evidence_frame(frame) if key == "evidence" else _ordered_frame(frame)
    _, preaudit_assets = _validate_assets(frames["preaudit"], "preaudit")
    _validate_assets(frames["comparison"], "comparison")
    if not isinstance(payload["coverage"], dict):
        raise TypeError("coverage must be a dict")
    coverage = _normalize_coverage(
        payload["coverage"],
        trade_date,
        top20_count=len(frames["top20"]),
        reserve_count=len(frames["reserve"]),
        preaudit_count=len(frames["preaudit"]),
    )
    final_top_n = coverage["final_top_n"]
    reserve_top_n = coverage["reserve_top_n"]
    top20_assets = _validate_selected(
        frames["top20"], "top20", range(1, len(frames["top20"]) + 1)
    )
    reserve_assets = _validate_selected(
        frames["reserve"],
        "reserve",
        range(final_top_n + 1, final_top_n + len(frames["reserve"]) + 1),
    )
    if top20_assets & reserve_assets:
        raise ValueError("top20 and reserve asset sets must be mutually exclusive")
    if not (top20_assets | reserve_assets).issubset(preaudit_assets):
        raise ValueError("top20 and reserve assets must be present in preaudit")
    report = _render_report(
        trade_date,
        frames["top20"],
        frames["reserve"],
        frames["preaudit"],
        frames["comparison"],
        frames["exclusions"],
        coverage,
        frames["scores"],
    )

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    lock_path = destination / ".publish.lock"
    lock_handle = _open_publish_lock(lock_path)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        _publish_release(destination, frames, coverage, report)
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()

    paths = {
        key: str(destination / "current" / filename)
        for key, filename in UNIFIED_OUTPUT_FILENAMES.items()
    }
    return {
        "paths": paths,
        "evidence": frames["evidence"],
        "scores": frames["scores"],
        "exclusions": frames["exclusions"],
        "coverage": coverage,
        "report": report,
        "top20": frames["top20"],
        "reserve": frames["reserve"],
        "preaudit": frames["preaudit"],
        "comparison": frames["comparison"],
    }
