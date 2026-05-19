from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any


def build_run_card_payload(
    *,
    run_type: str,
    run_id: str,
    title: str,
    config: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    artifact_paths: dict[str, Any] | None = None,
    status: str = "completed",
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    config_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "run_type": str(run_type),
        "run_id": str(run_id),
        "title": str(title),
        "status": str(status),
        "config_hash": str(config_hash or ""),
        "config": _jsonable(config or {}),
        "metrics": _jsonable(metrics or {}),
        "artifact_paths": _jsonable(artifact_paths or {}),
        "warnings": _jsonable(warnings or []),
        "metadata": _jsonable(metadata or {}),
    }


def render_run_card_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('title', 'Run Card')}",
        "",
        f"- run_type: {payload.get('run_type', '')}",
        f"- run_id: {payload.get('run_id', '')}",
        f"- status: {payload.get('status', '')}",
        f"- config_hash: {payload.get('config_hash', '')}",
        "",
        "## Config",
        "",
        "```json",
        json.dumps(payload.get("config", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(payload.get("metrics", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Artifacts",
        "",
        "```json",
        json.dumps(payload.get("artifact_paths", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Metadata",
        "",
        "```json",
        json.dumps(payload.get("metadata", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    warnings = payload.get("warnings") or []
    if warnings:
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                *[f"- {warning}" for warning in warnings],
            ]
        )
    return "\n".join(lines) + "\n"


def write_run_card(
    *,
    output_dir: str | Path,
    run_type: str,
    run_id: str,
    title: str,
    config: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    artifact_paths: dict[str, Any] | None = None,
    status: str = "completed",
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    data_coverage: dict[str, Any] | None = None,
) -> dict[str, str]:
    config_hash = _config_hash(config or {})
    out = build_run_card_output_dir(
        output_dir=output_dir,
        run_type=run_type,
        run_id=run_id,
        config=config or {},
    )
    out.mkdir(parents=True, exist_ok=True)
    evidence_dir = out / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    normalized_coverage = normalize_data_coverage(data_coverage or {})

    payload = build_run_card_payload(
        run_type=run_type,
        run_id=run_id,
        title=title,
        config=config,
        metrics=metrics,
        artifact_paths=artifact_paths,
        status=status,
        warnings=warnings,
        metadata=metadata,
        config_hash=config_hash,
    )

    json_path = out / "run_card.json"
    markdown_path = out / "run_card.md"
    manifest_path = evidence_dir / "manifest.json"
    metrics_json_path = out / "metrics.json"
    config_snapshot_path = out / "config_snapshot.json"
    warnings_md_path = out / "warnings.md"
    data_coverage_json_path = out / "data_coverage.json"

    artifact_manifest = {
        **(payload.get("artifact_paths") or {}),
        "run_card_json_path": str(json_path),
        "run_card_md_path": str(markdown_path),
        "metrics_json_path": str(metrics_json_path),
        "config_snapshot_path": str(config_snapshot_path),
        "warnings_md_path": str(warnings_md_path),
        "data_coverage_json_path": str(data_coverage_json_path),
    }
    payload["artifact_paths"] = artifact_manifest

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_run_card_markdown(payload), encoding="utf-8")
    metrics_json_path.write_text(
        json.dumps(_jsonable(metrics or {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config_snapshot = {
        **_jsonable(config or {}),
        "__run_type": str(run_type),
        "__run_id": str(run_id),
        "__title": str(title),
        "__status": str(status),
        "__config_hash": config_hash,
        "__metadata": _jsonable(metadata or {}),
    }
    config_snapshot_path.write_text(
        json.dumps(
            config_snapshot,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    warnings_md_path.write_text(
        _render_warnings_markdown(warnings or []),
        encoding="utf-8",
    )
    data_coverage_json_path.write_text(
        json.dumps(
            normalized_coverage,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "run_type": payload["run_type"],
                "run_id": payload["run_id"],
                "artifacts": payload["artifact_paths"],
                "warnings": payload["warnings"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "run_card_dir": str(out),
        "run_id": str(run_id),
        "config_hash": config_hash,
        "run_card_json_path": str(json_path),
        "run_card_md_path": str(markdown_path),
        "metrics_json_path": str(metrics_json_path),
        "config_snapshot_path": str(config_snapshot_path),
        "warnings_md_path": str(warnings_md_path),
        "data_coverage_json_path": str(data_coverage_json_path),
        "run_card_json": str(json_path),
        "run_card_markdown": str(markdown_path),
        "evidence_manifest": str(manifest_path),
    }


def normalize_data_coverage(data_coverage: dict[str, Any] | None) -> dict[str, Any]:
    coverage = _jsonable(data_coverage or {})
    if not isinstance(coverage, dict):
        return {}

    actual_dates = coverage.get("actual_dates")
    if actual_dates is not None:
        actual_dates = _normalize_string_list(actual_dates)
    expected_dates = coverage.get("expected_dates")
    if expected_dates is not None:
        expected_dates = _normalize_string_list(expected_dates)
    expected_assets = coverage.get("expected_assets")
    if expected_assets is not None:
        expected_assets = _normalize_string_list(expected_assets)

    coverage["actual_dates"] = actual_dates
    coverage["expected_dates"] = expected_dates
    coverage["expected_assets"] = expected_assets

    if coverage.get("row_count") is not None:
        coverage["row_count"] = _coerce_int(coverage.get("row_count"))
    if coverage.get("asset_count") is not None:
        coverage["asset_count"] = _coerce_int(coverage.get("asset_count"))

    coverage["missing_dates"] = None
    coverage["missing_assets"] = None
    coverage["coverage_ratio"] = None

    if expected_dates is not None and actual_dates is not None:
        missing_dates = [item for item in expected_dates if item not in actual_dates]
        coverage["missing_dates"] = missing_dates
        expected_count = len(expected_dates)
        if expected_count >= 0:
            coverage["coverage_ratio"] = (
                (expected_count - len(missing_dates)) / expected_count
                if expected_count > 0
                else None
            )

    if expected_assets is not None:
        actual_assets = _normalize_string_list(coverage.get("actual_assets")) if coverage.get("actual_assets") is not None else None
        coverage["actual_assets"] = actual_assets
        missing_assets = [item for item in expected_assets if actual_assets is not None and item not in actual_assets]
        coverage["missing_assets"] = missing_assets if actual_assets is not None else None
        if actual_assets is not None and coverage["coverage_ratio"] is None:
            expected_count = len(expected_assets)
            coverage["coverage_ratio"] = (
                (expected_count - len(missing_assets)) / expected_count
                if expected_count > 0
                else None
            )

    if expected_dates is None:
        coverage["missing_dates"] = None
        if coverage.get("coverage_ratio") is not None and actual_dates is None:
            coverage["coverage_ratio"] = None
    if expected_assets is None:
        coverage["missing_assets"] = None

    return coverage


def build_run_card_stem(
    *,
    run_type: str,
    run_id: str,
    config: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> str:
    stamp = timestamp or _timestamp_text()
    config_hash = _config_hash(config or {})
    type_part = _slugify(run_type)
    id_part = _slugify(run_id or run_type)
    return f"{type_part}_{id_part}_{stamp}_{config_hash}"


def build_run_card_output_dir(
    *,
    output_dir: str | Path,
    run_type: str,
    run_id: str,
    config: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> Path:
    base_dir = Path(output_dir)
    stem = build_run_card_stem(
        run_type=run_type,
        run_id=run_id,
        config=config,
        timestamp=timestamp,
    )
    candidate = base_dir / stem
    index = 2
    while candidate.exists():
        candidate = base_dir / f"{stem}_{index:02d}"
        index += 1
    return candidate


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(_jsonable(config), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def _timestamp_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").lower()
    return normalized[:80] or "run_card"


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _render_warnings_markdown(warnings: list[str]) -> str:
    lines = ["# Warnings", ""]
    if warnings:
        lines.extend([f"- {warning}" for warning in warnings])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
