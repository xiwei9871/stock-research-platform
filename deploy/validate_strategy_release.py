#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


OFFICIAL_STRATEGIES = {
    "lhb_shortline": "strategy_lhb_shortline_review.csv",
    "mid_trend": "strategy_mid_trend_review.csv",
    "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
}
REQUIRED_MODULES = {
    "strategy_lhb_shortline",
    "strategy_mid_trend",
    "strategy_tech_bottleneck",
    "review_queue_strategy_manifest",
}


def _read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required release file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON release file: {path}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required release file: {path}") from exc


def _validate_rows(rows: list[dict[str, str]], *, trade_date: str, label: str) -> None:
    if len(rows) != 5:
        raise ValueError(f"{label} must contain exactly 5 rows, got {len(rows)}")
    dates = {str(row.get("trade_date") or "") for row in rows}
    if dates != {trade_date}:
        raise ValueError(f"{label} trade_date mismatch: {sorted(dates)}")
    ranks = sorted(int(str(row.get("rank") or "0")) for row in rows)
    if ranks != [1, 2, 3, 4, 5]:
        raise ValueError(f"{label} ranks must be 1..5, got {ranks}")
    if any(str(row.get("review_tier") or "") != "top5_focus" for row in rows):
        raise ValueError(f"{label} contains non-top5 review rows")
    assets = [_asset_id(row) for row in rows]
    if any(not asset_id for asset_id in assets):
        raise ValueError(f"{label} contains an empty asset identifier")
    if len(set(assets)) != len(assets):
        raise ValueError(f"{label} contains a duplicate asset identifier")


def _asset_id(row: dict[str, str]) -> str:
    for key in ("asset_id", "stock_code", "ts_code", "code"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _row_keys(rows: list[dict[str, str]]) -> set[tuple[str, int, str]]:
    return {
        (
            str(row.get("strategy_id") or "").strip(),
            int(str(row.get("rank") or "0")),
            _asset_id(row),
        )
        for row in rows
    }


def _validate_artifact_paths(rows: list[dict[str, str]], *, output_dir: Path) -> None:
    release_root = output_dir.resolve()
    for row in rows:
        raw_path = str(row.get("artifact_path") or "").strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        resolved = (release_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            resolved.relative_to(release_root)
        except ValueError as exc:
            raise ValueError(f"manifest artifact_path escapes release directory: {raw_path}") from exc


def validate_strategy_release(*, output_dir: str | Path, trade_date: str) -> None:
    root = Path(output_dir)
    summary = _read_json(root / "strategy_eod_publish_summary.json")
    if str(summary.get("trade_date") or "") != trade_date:
        raise ValueError("strategy publish summary trade_date mismatch")
    if "publishable" in summary and summary.get("publishable") is not True:
        raise ValueError("strategy publish summary is not publishable")
    if int(summary.get("review_rows") or 0) != 15:
        raise ValueError("strategy publish summary must report 15 review rows")

    modules = {str(item) for item in summary.get("manifest_modules") or []}
    missing_modules = sorted(REQUIRED_MODULES - modules)
    if missing_modules:
        raise ValueError(f"strategy publish summary missing modules: {missing_modules}")

    score_audit = summary.get("score_audit")
    if not isinstance(score_audit, dict) or score_audit.get("status") != "success":
        raise ValueError("strategy score audit is not successful")
    strategy_counts = score_audit.get("strategy_counts")
    expected_counts = {strategy_id: 5 for strategy_id in OFFICIAL_STRATEGIES}
    if strategy_counts != expected_counts:
        raise ValueError(f"strategy score audit counts mismatch: {strategy_counts}")

    manifest_rows = _read_csv(root / "review_queue_strategy_manifest.csv")
    if len(manifest_rows) != 15:
        raise ValueError(f"review queue manifest must contain 15 rows, got {len(manifest_rows)}")
    manifest_counts = Counter(str(row.get("strategy_id") or "") for row in manifest_rows)
    if manifest_counts != Counter(expected_counts):
        raise ValueError(f"review queue manifest strategy counts mismatch: {dict(manifest_counts)}")
    _validate_artifact_paths(manifest_rows, output_dir=root)
    for strategy_id in OFFICIAL_STRATEGIES:
        _validate_rows(
            [row for row in manifest_rows if row.get("strategy_id") == strategy_id],
            trade_date=trade_date,
            label=f"manifest {strategy_id}",
        )

    for strategy_id, filename in OFFICIAL_STRATEGIES.items():
        rows = _read_csv(root / filename)
        _validate_rows(rows, trade_date=trade_date, label=filename)
        row_ids = {str(row.get("strategy_id") or "") for row in rows}
        if row_ids != {strategy_id}:
            raise ValueError(f"{filename} strategy_id mismatch: {sorted(row_ids)}")
        manifest_strategy_rows = [
            row for row in manifest_rows if str(row.get("strategy_id") or "") == strategy_id
        ]
        if _row_keys(rows) != _row_keys(manifest_strategy_rows):
            raise ValueError(f"{filename} does not match manifest strategy/rank/asset keys")


def resolve_latest_strategy_release(*, output_root: str | Path) -> str:
    root = Path(output_root)
    if not root.is_dir():
        raise ValueError(f"strategy output root is missing: {root}")
    for candidate in sorted(root.iterdir(), key=lambda path: path.name, reverse=True):
        if not candidate.is_dir() or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", candidate.name):
            continue
        try:
            validate_strategy_release(output_dir=candidate, trade_date=candidate.name)
        except (TypeError, ValueError):
            continue
        return candidate.name
    raise ValueError(f"no contract-valid strategy release found under: {root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one official strategy dashboard release")
    parser.add_argument("--output-dir")
    parser.add_argument("--trade-date")
    parser.add_argument("--output-root")
    parser.add_argument("--resolve-latest", action="store_true")
    args = parser.parse_args()
    try:
        if args.resolve_latest:
            if not args.output_root:
                raise ValueError("--output-root is required with --resolve-latest")
            print(resolve_latest_strategy_release(output_root=args.output_root))
            return 0
        if not args.output_dir or not args.trade_date:
            raise ValueError("--output-dir and --trade-date are required")
        validate_strategy_release(output_dir=args.output_dir, trade_date=args.trade_date)
    except (TypeError, ValueError) as exc:
        parser.exit(2, f"strategy release contract invalid: {exc}\n")
    print(f"strategy release contract valid: {args.trade_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
