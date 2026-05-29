from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.daily_job_run_store import (
    apply_daily_job_run_schema,
    record_daily_job_run,
)
from stock_research.db import connect, fetch_all
from stock_research.p2.review_read_model import import_p2_aggregate_review
from stock_research.p3.operator_export import export_operator_review
from stock_research.simulation.virtual_portfolio_read_model import (
    import_virtual_portfolio_review,
)


def run_daily_orchestration(
    *,
    trade_date: str,
    aggregate_review_path: str | Path,
    virtual_portfolio_path: str | Path,
    output_dir: str | Path,
    portfolio_id: str | None = None,
    apply_daily_run_schema: bool = False,
    record_run: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    aggregate_path = Path(aggregate_review_path)
    virtual_path = Path(virtual_portfolio_path)
    output_path = Path(output_dir)
    if apply_daily_run_schema:
        apply_daily_job_run_schema(service=service)
    missing = [
        str(path)
        for path in (aggregate_path, virtual_path)
        if not path.exists()
    ]
    if missing:
        result = {
            "trade_date": trade_date,
            "status": "blocked",
            "blocker_count": len(missing),
            "missing_artifacts": missing,
            "p2_review_import": None,
            "virtual_portfolio_import": None,
            "operator_export": None,
        }
        if record_run:
            result["daily_job_run_id"] = _record_orchestration_result(
                result,
                service=service,
                error_message="missing artifacts: " + ",".join(missing),
            )
        return result

    try:
        p2_result = import_p2_aggregate_review(aggregate_path, service=service)
        virtual_result = import_virtual_portfolio_review(virtual_path, service=service)
        export_result = export_operator_review(
            start_date=trade_date,
            end_date=trade_date,
            output_dir=output_path,
            portfolio_id=portfolio_id,
            service=service,
        )
    except Exception as exc:
        if record_run:
            _record_orchestration_result(
                {
                    "trade_date": trade_date,
                    "status": "failed",
                    "blocker_count": 1,
                    "missing_artifacts": [],
                    "p2_review_import": None,
                    "virtual_portfolio_import": None,
                    "operator_export": None,
                    "aggregate_review_path": str(aggregate_path),
                    "virtual_portfolio_path": str(virtual_path),
                    "output_dir": str(output_path),
                    "portfolio_id": portfolio_id,
                    "error_type": type(exc).__name__,
                },
                service=service,
                error_message=str(exc),
            )
        raise

    result = {
        "trade_date": trade_date,
        "status": "ok",
        "blocker_count": 0,
        "missing_artifacts": [],
        "p2_review_import": p2_result,
        "virtual_portfolio_import": virtual_result,
        "operator_export": export_result,
    }
    if record_run:
        result["daily_job_run_id"] = _record_orchestration_result(
            result,
            service=service,
        )
    return result


def format_daily_orchestration_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        "p4_daily_orchestration|"
        f"status|{result['status']}|trade_date|{result['trade_date']}|"
        f"blockers|{int(result['blocker_count'])}"
    ]
    for path in result.get("missing_artifacts") or []:
        lines.append(f"p4_daily_orchestration|missing_artifact|{path}")
    if result.get("daily_job_run_id"):
        lines.append(
            f"p4_daily_orchestration|daily_job_run_id|{result['daily_job_run_id']}"
        )
    p2_result = result.get("p2_review_import")
    if p2_result:
        lines.append(
            "p4_daily_orchestration|p2_review_import|"
            f"imported|{int(p2_result['imported_count'])}"
        )
    virtual_result = result.get("virtual_portfolio_import")
    if virtual_result:
        lines.append(
            "p4_daily_orchestration|virtual_portfolio_import|"
            f"imported|{int(virtual_result['imported_count'])}|"
            f"states|{int(virtual_result['state_count'])}|"
            f"positions|{int(virtual_result['position_count'])}"
        )
    export_result = result.get("operator_export")
    if export_result:
        lines.append(
            "p4_daily_orchestration|operator_export|"
            f"manifest|{export_result['manifest_path']}"
        )
        for dataset_name, rows in sorted(export_result.get("row_counts", {}).items()):
            lines.append(
                f"p4_daily_orchestration_dataset|{dataset_name}|rows|{int(rows)}"
            )
    return lines


def _record_orchestration_result(
    result: dict[str, Any],
    *,
    service: str,
    error_message: str | None = None,
) -> str:
    return record_daily_job_run(
        trade_date=result["trade_date"],
        step="p4_daily_orchestration",
        status=_daily_job_status(result["status"]),
        metadata=_orchestration_metadata(result),
        error_message=error_message,
        service=service,
    )


def _daily_job_status(status: str) -> str:
    if status == "ok":
        return "success"
    return status


def _orchestration_metadata(result: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "trade_date",
        "status",
        "blocker_count",
        "missing_artifacts",
        "p2_review_import",
        "virtual_portfolio_import",
        "operator_export",
        "aggregate_review_path",
        "virtual_portfolio_path",
        "output_dir",
        "portfolio_id",
        "error_type",
    ]
    return {
        key: result[key]
        for key in keys
        if key in result and result[key] is not None
    }


def check_read_model_freshness(
    *,
    trade_date: str,
    operator_manifest_path: str | Path,
    portfolio_id: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    manifest_path = Path(operator_manifest_path)
    with connect(service) as conn:
        latest_review = _latest_p2_review_run(conn, trade_date)
        latest_portfolio = _latest_virtual_portfolio_state(
            conn,
            trade_date,
            portfolio_id=portfolio_id,
        )

    checks = {
        "p2_review_run": _freshness_check(latest_review, trade_date),
        "virtual_portfolio_state": _freshness_check(latest_portfolio, trade_date),
        "operator_export_files": _operator_export_files_check(manifest_path),
        "operator_export_row_counts": _operator_export_row_counts_check(manifest_path),
    }
    blocker_count = sum(1 for check in checks.values() if check["status"] == "blocked")
    warning_count = sum(1 for check in checks.values() if check["status"] == "warning")
    return {
        "trade_date": trade_date,
        "status": "blocked" if blocker_count else "warning" if warning_count else "pass",
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "checks": checks,
    }


def format_read_model_freshness_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        "p4_read_model_smoke|"
        f"status|{result['status']}|trade_date|{result['trade_date']}|"
        f"blockers|{int(result['blocker_count'])}|"
        f"warnings|{int(result['warning_count'])}"
    ]
    for name, check in sorted(result.get("checks", {}).items()):
        detail = _format_check_detail(check)
        suffix = f"|{detail}" if detail else ""
        lines.append(f"p4_read_model_smoke_check|{name}|{check['status']}{suffix}")
    return lines


def _latest_p2_review_run(conn: Any, trade_date: str) -> dict[str, Any] | None:
    sql = """
        SELECT trade_date, run_id, status
        FROM ops.p2_review_run
        WHERE trade_date <= %s
        ORDER BY trade_date DESC, updated_at DESC, run_id
        LIMIT 1
    """
    rows = fetch_all(conn, sql, [trade_date])
    return rows[0] if rows else None


def _latest_virtual_portfolio_state(
    conn: Any,
    trade_date: str,
    *,
    portfolio_id: str | None,
) -> dict[str, Any] | None:
    where = ["trade_date <= %s"]
    params: list[Any] = [trade_date]
    if portfolio_id:
        where.append("portfolio_id = %s")
        params.append(portfolio_id)
    sql = f"""
        SELECT trade_date, portfolio_id, strategy_id, review_status
        FROM simulation.virtual_portfolio_state_daily
        WHERE {" AND ".join(where)}
        ORDER BY trade_date DESC, portfolio_id, strategy_id
        LIMIT 1
    """
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def _freshness_check(row: dict[str, Any] | None, trade_date: str) -> dict[str, Any]:
    if not row:
        return {"status": "blocked", "latest_trade_date": ""}
    latest_trade_date = str(row.get("trade_date") or "")
    if latest_trade_date != trade_date:
        return {"status": "blocked", "latest_trade_date": latest_trade_date}
    return {"status": "pass", "latest_trade_date": latest_trade_date}


def _operator_export_files_check(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return {
            "status": "blocked",
            "missing_files": [str(manifest_path)],
        }
    paths = list((manifest.get("files") or {}).values())
    paths.extend((manifest.get("json_files") or {}).values())
    missing = [str(path) for path in paths if not Path(path).exists()]
    return {
        "status": "blocked" if missing else "pass",
        "missing_files": missing,
    }


def _operator_export_row_counts_check(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return {
            "status": "blocked",
            "zero_count_datasets": [],
        }
    zero_count = [
        str(name)
        for name, count in (manifest.get("row_counts") or {}).items()
        if int(count or 0) == 0
    ]
    return {
        "status": "warning" if zero_count else "pass",
        "zero_count_datasets": sorted(zero_count),
    }


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"operator manifest must be a JSON object: {path}")
    return data


def _format_check_detail(check: dict[str, Any]) -> str:
    if "missing_files" in check and check["missing_files"]:
        return "missing_files|" + ",".join(str(path) for path in check["missing_files"])
    if "zero_count_datasets" in check and check["zero_count_datasets"]:
        return "zero_count_datasets|" + ",".join(
            str(name) for name in check["zero_count_datasets"]
        )
    if "latest_trade_date" in check:
        return f"latest_trade_date|{check['latest_trade_date']}"
    return ""
