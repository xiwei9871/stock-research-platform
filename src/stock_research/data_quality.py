from __future__ import annotations

from datetime import datetime
from typing import Any

from stock_research.data_audit import run_data_audit
from stock_research.factor_config import candidate_factor_names
from stock_research.finance_audit import summarize_finance_coverage
from stock_research.research_preflight import (
    check_factor_label_coverage,
    check_industry_membership_coverage,
    find_latest_common_label_date,
)


def run_data_quality(
    *,
    expected_start_date: str = "1990-12-01",
    start_date: str,
    end_date: str,
    horizons: list[int],
    factor_names: list[str] | None = None,
    calc_version: str = "v1",
    min_label_dates: int = 20,
    require_industry_membership: bool = False,
) -> dict[str, Any]:
    selected_factor_names = candidate_factor_names() if factor_names is None else factor_names
    checks = [
        *_build_data_audit_checks(expected_start_date=expected_start_date),
        *_build_finance_audit_checks(),
        *_build_research_preflight_checks(
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            factor_names=selected_factor_names,
            calc_version=calc_version,
            min_label_dates=min_label_dates,
            require_industry_membership=require_industry_membership,
        ),
    ]
    blocked_checks = [check["check_name"] for check in checks if check["status"] == "blocked"]
    warning_checks = [check["check_name"] for check in checks if check["status"] == "warning"]
    overall_status = "blocked" if blocked_checks else "warning" if warning_checks else "ok"
    return {
        "overall_status": overall_status,
        "generated_at": datetime.now().astimezone().isoformat(),
        "checks": checks,
        "blocked_checks": blocked_checks,
        "warning_checks": warning_checks,
    }


def format_data_quality_summary_line(report: dict[str, Any]) -> str:
    return (
        "data_quality|summary|"
        f"{report['overall_status']}|checks|{len(report['checks'])}|"
        f"blocked|{len(report['blocked_checks'])}|warning|{len(report['warning_checks'])}"
    )


def format_data_quality_check_line(check: dict[str, Any]) -> str:
    parts = [
        "data_quality",
        str(check["check_name"]),
        str(check["status"]),
        "kind",
        str(check["kind"]),
    ]
    for key, value in check.get("metrics", {}).items():
        if _is_scalar_metric(value):
            parts.extend([str(key), _format_metric_value(value)])
    return "|".join(parts)


def iter_data_quality_lines(report: dict[str, Any]):
    yield format_data_quality_summary_line(report)
    for check in report["checks"]:
        yield format_data_quality_check_line(check)


def _build_data_audit_checks(*, expected_start_date: str) -> list[dict[str, Any]]:
    return [
        _normalize_data_audit_check(row)
        for row in run_data_audit(expected_start_date=expected_start_date)
    ]


def _build_finance_audit_checks() -> list[dict[str, Any]]:
    return [_normalize_finance_audit_check(row) for row in summarize_finance_coverage()]


def _build_research_preflight_checks(
    *,
    start_date: str,
    end_date: str,
    horizons: list[int],
    factor_names: list[str],
    calc_version: str,
    min_label_dates: int,
    require_industry_membership: bool,
) -> list[dict[str, Any]]:
    latest = find_latest_common_label_date(start_date=start_date, horizons=horizons)
    coverage = check_factor_label_coverage(
        factor_names=factor_names,
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        calc_version=calc_version,
        min_label_dates=min_label_dates,
    )
    checks = [
        _normalize_latest_common_label_date_check(latest),
        _normalize_factor_label_coverage_check(coverage),
    ]
    if require_industry_membership:
        industry = check_industry_membership_coverage(
            start_date=start_date,
            end_date=end_date,
        )
        checks.append(_normalize_industry_membership_coverage_check(industry))
    return checks


def _normalize_data_audit_check(row: dict[str, Any]) -> dict[str, Any]:
    return _normalize_check(
        check_name=str(row["dataset"]),
        status=_normalize_data_audit_status(str(row["status"])),
        kind="data_audit",
        source="data_audit",
        metrics={
            "rows": int(row.get("rows") or 0),
            "date_count": int(row.get("date_count") or 0),
            "min_date": _normalize_optional_date(row.get("min_date")),
            "max_date": _normalize_optional_date(row.get("max_date")),
        },
        details={"raw_status": row.get("status")},
    )


def _normalize_finance_audit_check(row: dict[str, Any]) -> dict[str, Any]:
    return _normalize_check(
        check_name=str(row["check"]),
        status=str(row["status"]),
        kind="finance_audit",
        source="finance_audit",
        metrics={"rows": int(row.get("rows") or 0)},
        details={},
    )


def _normalize_latest_common_label_date_check(row: dict[str, Any]) -> dict[str, Any]:
    latest_common_date = _normalize_optional_date(row.get("latest_common_date"))
    date_count = int(row.get("date_count") or 0)
    status = "ok" if latest_common_date is not None and date_count > 0 else "blocked"
    return _normalize_check(
        check_name="latest_common_label_date",
        status=status,
        kind="research_preflight",
        source="research_preflight",
        metrics={
            "latest_common_date": latest_common_date,
            "date_count": date_count,
        },
        details={"horizons": list(row.get("horizons") or [])},
    )


def _normalize_factor_label_coverage_check(row: dict[str, Any]) -> dict[str, Any]:
    return _normalize_check(
        check_name="factor_label_coverage",
        status=_normalize_research_preflight_status(str(row["status"])),
        kind="research_preflight",
        source="research_preflight",
        metrics={
            "factor_date_count": int(row.get("factor_date_count") or 0),
            "factor_complete_date_count": int(row.get("factor_complete_date_count") or 0),
        },
        details={
            "missing_horizons": list(row.get("missing_horizons") or []),
            "short_label_horizons": list(row.get("short_label_horizons") or []),
            "required_factor_names": list(row.get("required_factor_names") or []),
            "unavailable_factor_names": list(row.get("unavailable_factor_names") or []),
            "reasons": list(row.get("reasons") or []),
        },
    )


def _normalize_industry_membership_coverage_check(row: dict[str, Any]) -> dict[str, Any]:
    return _normalize_check(
        check_name="industry_membership_coverage",
        status=_normalize_research_preflight_status(str(row["status"])),
        kind="research_preflight",
        source="research_preflight",
        metrics={
            "market_rows": int(row.get("market_rows") or 0),
            "covered_rows": int(row.get("covered_rows") or 0),
            "missing_rows": int(row.get("missing_rows") or 0),
            "date_count": int(row.get("date_count") or 0),
        },
        details={},
    )


def _normalize_check(
    *,
    check_name: str,
    status: str,
    kind: str,
    source: str,
    metrics: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "status": status,
        "kind": kind,
        "source": source,
        "metrics": metrics,
        "details": details,
    }


def _normalize_data_audit_status(status: str) -> str:
    return {
        "ok": "ok",
        "short_history": "warning",
        "empty": "blocked",
    }[status]


def _normalize_research_preflight_status(status: str) -> str:
    return {
        "ok": "ok",
        "blocked": "blocked",
    }[status]


def _normalize_optional_date(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)[:10]


def _is_scalar_metric(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _format_metric_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
