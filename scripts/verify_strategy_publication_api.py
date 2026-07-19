#!/usr/bin/env python3
"""Verify the official strategy publication API response."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.strategy_publication_artifacts import ARTIFACT_VERSION
from stock_research.strategy_publication_contracts import (
    OFFICIAL_STRATEGY_IDS,
    build_publication_identity,
    get_publication_contract,
)


def _runnable_official_strategy_ids() -> list[str]:
    return sorted(
        str(item.get("strategy_id") or "")
        for item in list_strategy_catalog()
        if item.get("status") == "runnable"
        and str(item.get("strategy_id") or "") in OFFICIAL_STRATEGY_IDS
    )


def _valid_date(value: Any) -> bool:
    text = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def _valid_manifest_path(value: Any, strategy_id: str) -> bool:
    text = str(value or "")
    if not text.startswith("/") or "\\" in text or "?" in text or "#" in text:
        return False
    parts = text.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if parts.count("strategy_runs") != 1:
        return False
    index = parts.index("strategy_runs")
    if len(parts) != index + 4:
        return False
    publish_id = parts[index + 2]
    return bool(
        parts[index + 1] == strategy_id
        and re.fullmatch(r"[A-Za-z0-9._-]+", publish_id)
        and publish_id not in {".", ".."}
        and parts[index + 3] == "publication_manifest.json"
    )


def _item_valid(item: Mapping[str, Any], strategy_id: str) -> bool:
    if item.get("status") != "runnable":
        return False
    metrics = item.get("latest_metrics")
    if not isinstance(metrics, Mapping) or metrics.get("contract_status") != "success":
        return False
    expected = build_publication_identity(
        get_publication_contract(strategy_id, profile="balanced")
    )
    projected_identity = {
        field: metrics.get(field)
        for field in (
            "identity_schema_version",
            "contract_id",
            "config_fingerprint",
            "publication_policy",
        )
    }
    expected_projection = {
        field: expected[field]
        for field in projected_identity
    }
    if projected_identity != expected_projection:
        return False
    if metrics.get("artifact_version") != ARTIFACT_VERSION:
        return False
    if not _valid_date(metrics.get("performance_as_of_date")):
        return False
    return _valid_manifest_path(metrics.get("publication_manifest_path"), strategy_id)


def verify_payload(payload: Any) -> dict[str, Any]:
    strategy_ids = _runnable_official_strategy_ids()
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, list):
        items = []
    grouped: dict[str, list[Mapping[str, Any]]] = {strategy_id: [] for strategy_id in strategy_ids}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        strategy_id = str(item.get("strategy_id") or "")
        if strategy_id in grouped:
            grouped[strategy_id].append(item)

    failures = [
        f"{strategy_id}: contract_mismatch"
        for strategy_id in strategy_ids
        if len(grouped[strategy_id]) != 1
        or not _item_valid(grouped[strategy_id][0], strategy_id)
    ]
    return {
        "status": "failed" if failures else "success",
        "checked": strategy_ids,
        "failures": failures,
    }


def _fetch_payload(base_url: str) -> Mapping[str, Any]:
    url = f"{base_url.rstrip('/')}/api/backtests/strategies"
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:  # nosec - operator-supplied local API URL.
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise ValueError("strategy API response must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5174")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        report = verify_payload(_fetch_payload(args.base_url))
    except Exception as exc:
        report = {"status": "failed", "checked": [], "failures": [f"api: {exc}"]}
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
