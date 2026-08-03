"""Explicit, target-scoped THS concept membership backfill.

This module is intentionally outside the rolling-oversold strategy path.  It
is the only place in the target repair workflow that may call the AkShare/THS
source adapter.  The default mode is a read-only preview; database writes are
performed only when ``dry_run=False`` and are committed by the existing
``stock_research.db.connect`` transaction boundary.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.core_data import _asset_id_from_cn_stock_code
from stock_research.db import connect, execute, execute_many, fetch_all

try:  # pragma: no cover - optional dependency is injected in unit tests
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


DEFAULT_OUTPUT_DIR = Path("outputs/research/rolling_sector_target_membership_backfill")
TARGET_CODE_PATTERN = re.compile(r"^[0-9]{6}$")
TARGET_CONCEPT_SYSTEM = "ths"
BOARD_SOURCE = "akshare:stock_board_concept_name_ths"
MEMBERSHIP_SOURCE = "akshare:stock_board_concept_cons_em"

BOARD_UPSERT_SQL = """
INSERT INTO core.concept_board (
    concept_system,
    concept_code,
    concept_name,
    source,
    is_active
)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (concept_system, concept_code) DO UPDATE SET
    concept_name = EXCLUDED.concept_name,
    source = EXCLUDED.source,
    is_active = EXCLUDED.is_active,
    updated_at = now()
"""

MEMBERSHIP_UPSERT_SQL = """
INSERT INTO core.concept_membership (
    asset_id,
    concept_system,
    concept_code,
    concept_name,
    start_date,
    source
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (asset_id, concept_system, concept_code, start_date) DO UPDATE SET
    concept_name = EXCLUDED.concept_name,
    source = EXCLUDED.source,
    end_date = NULL,
    updated_at = now()
"""

CLOSE_MEMBERSHIP_SQL = """
UPDATE core.concept_membership
SET end_date = %s,
    updated_at = now()
WHERE concept_system = %s
  AND concept_code = %s
  AND end_date IS NULL
  AND start_date < %s
  AND NOT (asset_id = ANY(%s))
"""

ASSET_MASTER_SQL = """
SELECT
    asset_id,
    symbol,
    name,
    exchange,
    list_date,
    delist_date,
    is_active,
    is_beijing
FROM core.asset_master
WHERE asset_id = ANY(%s)
"""

DETAIL_COLUMNS = (
    "concept_code",
    "concept_name",
    "asset_id",
    "status",
    "reason",
)


def load_target_codes(source: str | Path | Sequence[object] | pd.DataFrame) -> tuple[str, ...]:
    """Read and validate a target code CSV or one-code-per-line list.

    A CSV must expose a ``concept_code`` column.  A plain list is one code per
    line.  Validation is deliberately strict: target THS board identifiers are
    exactly six decimal digits, and duplicate codes are rejected rather than
    silently changing the frozen universe.
    """

    if isinstance(source, pd.DataFrame):
        if "concept_code" not in source.columns:
            raise ValueError("target CSV must contain concept_code column")
        values = source["concept_code"].tolist()
        return normalize_target_codes(values)

    if isinstance(source, (str, Path)):
        path = Path(source).expanduser()
        if path.exists():
            return _load_codes_from_path(path)
        # A single code or a comma-separated explicit code list is useful for
        # programmatic callers, while paths remain the CLI contract.
        values = [item for item in str(source).split(",")]
        return normalize_target_codes(values)

    return normalize_target_codes(source)


def normalize_target_codes(values: Iterable[object]) -> tuple[str, ...]:
    """Normalize an explicit iterable of six-digit concept codes."""

    if isinstance(values, (set, frozenset)):
        values = sorted(values)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            raise ValueError("target concept code list contains a blank line")
        if not TARGET_CODE_PATTERN.fullmatch(value):
            raise ValueError(f"target concept code must be six-digit: {value!r}")
        if value in seen:
            raise ValueError(f"duplicate target concept code: {value}")
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise ValueError("target concept code list must not be empty")
    return tuple(normalized)


def _load_codes_from_path(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"unable to read target concept code file: {path}") from exc
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise ValueError("target concept code file must not be empty")

    header = [str(value).strip() for value in rows[0]]
    code_index = next(
        (index for index, value in enumerate(header) if value == "concept_code"),
        None,
    )
    if code_index is not None:
        values: list[object] = []
        for row in rows[1:]:
            if not row or not any(str(value).strip() for value in row):
                raise ValueError("target concept code CSV contains a blank row")
            if code_index >= len(row):
                raise ValueError("target concept code CSV row is missing concept_code")
            values.append(row[code_index])
        return normalize_target_codes(values)

    values = []
    for row in rows:
        if not row or not any(str(value).strip() for value in row):
            raise ValueError("target concept code list contains a blank line")
        if len(row) != 1:
            raise ValueError("plain target concept code list must contain one code per line")
        values.append(row[0])
    return normalize_target_codes(values)


def fetch_target_concept_boards() -> Any:
    """Fetch the THS board list through the explicit AkShare adapter boundary."""

    if ak is None:
        raise RuntimeError("akshare package is required for target membership backfill")
    return ak.stock_board_concept_name_ths()


def fetch_target_concept_constituents(symbol: str) -> Any:
    """Fetch one board's constituents through the existing AkShare adapter."""

    if ak is None:
        raise RuntimeError("akshare package is required for target membership backfill")
    # AkShare exposes the THS board names but the existing constituent adapter
    # is EastMoney-backed and accepts the board name.  Keeping this call here
    # makes the source boundary explicit and prevents strategy code from
    # discovering or downloading a universe.
    return ak.stock_board_concept_cons_em(symbol)


def load_target_asset_master(
    asset_ids: Iterable[str],
    trade_date: date,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Read the PIT asset master rows needed to validate source constituents."""

    normalized = sorted({str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()})
    if not normalized:
        return []
    with connect(service) as conn:
        return fetch_all(conn, ASSET_MASTER_SQL, [normalized])


def validate_target_membership_rows(
    rows: Iterable[Mapping[str, object]], *, target_codes: Iterable[object]
) -> list[dict[str, str]]:
    """Strictly validate already-normalized target membership rows.

    This helper is intentionally stricter than the executor's reporting path:
    callers using it are asserting that every row is valid, so BSE rows raise a
    clear error instead of being silently filtered.
    """

    codes = set(normalize_target_codes(target_codes))
    validated: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        concept_code = _row_concept_code(row)
        if concept_code not in codes:
            raise ValueError(f"concept_code outside target scope: {concept_code!r}")
        asset_id = _normalize_source_asset_id(_row_asset_value(row))
        if asset_id is None:
            raise ValueError("invalid_asset_id")
        if asset_id.startswith("CN:BJ:"):
            raise ValueError("out_of_scope_bse")
        key = (concept_code, asset_id)
        if key in seen:
            continue
        seen.add(key)
        validated.append({"concept_code": concept_code, "asset_id": asset_id})
    return validated


def run_target_membership_backfill(
    *,
    trade_date: date | str,
    target_codes: str | Path | Iterable[object] | pd.DataFrame,
    service: str = SETTINGS.research_service,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = True,
    board_fetcher=None,
    constituent_fetcher=None,
    asset_master_loader=None,
) -> dict[str, Any]:
    """Preview or execute a frozen target-scoped THS membership backfill."""

    cutoff = _parse_date(trade_date)
    codes = load_target_codes(target_codes)
    fetch_boards = board_fetcher or fetch_target_concept_boards
    fetch_constituents = constituent_fetcher or fetch_target_concept_constituents
    load_master = asset_master_loader or load_target_asset_master

    source_missing_codes: list[str] = []
    failed_concepts: list[str] = []
    source_error = ""
    boards_by_code: dict[str, dict[str, str]] = {}
    try:
        for board in _normalize_board_rows(fetch_boards()):
            code = board["concept_code"]
            if code in codes and code not in boards_by_code:
                boards_by_code[code] = board
    except Exception as exc:  # noqa: BLE001 - source failure is an auditable gap
        source_error = str(exc)

    source_missing_codes = [code for code in codes if code not in boards_by_code]
    source_members: dict[str, list[dict[str, str]]] = {}
    detail_rows: list[dict[str, Any]] = []
    candidate_assets: set[str] = set()
    out_of_scope_bse: list[str] = []
    out_of_scope_900xxx: list[str] = []

    for code in codes:
        board = boards_by_code.get(code)
        if board is None:
            detail_rows.append(
                _detail(code, "", "", "source_missing", "target code not present in THS board list")
            )
            continue
        try:
            raw_constituents = fetch_constituents(board["concept_name"])
            if _is_empty_source_response(raw_constituents):
                failed_concepts.append(code)
                detail_rows.append(
                    _detail(code, board["concept_name"], "", "source_failed", "empty_response")
                )
                continue
            normalized, excluded_900xxx = _normalize_constituent_rows_with_exclusions(
                raw_constituents,
                concept_code=code,
            )
            for raw_code in excluded_900xxx:
                out_of_scope_900xxx.append(raw_code)
                detail_rows.append(
                    _detail(
                        code,
                        board["concept_name"],
                        raw_code,
                        "out_of_scope_900xxx",
                        "900xxx B-share code is excluded",
                    )
                )
            if not normalized:
                failed_concepts.append(code)
                detail_rows.append(
                    _detail(
                        code,
                        board["concept_name"],
                        "",
                        "source_failed",
                        "empty_or_invalid_response",
                    )
                )
                # No member rows from an invalid response may be interpreted
                # as a legitimate empty board.  Do not add this concept to
                # source_members, so it cannot close existing history.
                continue
        except Exception as exc:  # noqa: BLE001 - preserve old history on source failure
            failed_concepts.append(code)
            detail_rows.append(_detail(code, board["concept_name"], "", "source_failed", str(exc)))
            continue

        source_members[code] = []
        for item in normalized:
            raw_asset = item["asset_id"]
            if raw_asset.startswith("CN:BJ:"):
                out_of_scope_bse.append(raw_asset)
                detail_rows.append(
                    _detail(code, board["concept_name"], raw_asset, "out_of_scope_bse", "BSE is excluded")
                )
                continue
            source_members[code].append(
                {
                    "concept_code": code,
                    "concept_name": board["concept_name"],
                    "asset_id": raw_asset,
                }
            )
            candidate_assets.add(raw_asset)

    master_rows = (
        list(load_master(sorted(candidate_assets), cutoff, service))
        if candidate_assets
        else []
    )
    master_by_asset = {
        str(row.get("asset_id") or "").strip(): row
        for row in master_rows
        if str(row.get("asset_id") or "").strip()
    }

    valid_rows: list[dict[str, str]] = []
    valid_assets_by_concept: dict[str, list[str]] = {}
    invalid_statuses: dict[str, int] = {}
    for code in codes:
        board = boards_by_code.get(code)
        if board is None or code not in source_members:
            continue
        valid_assets_by_concept[code] = []
        for item in source_members[code]:
            asset_id = item["asset_id"]
            master = master_by_asset.get(asset_id)
            status, reason = _asset_eligibility(master, cutoff)
            if status != "valid":
                invalid_statuses[status] = invalid_statuses.get(status, 0) + 1
                detail_rows.append(_detail(code, item["concept_name"], asset_id, status, reason))
                continue
            valid_rows.append(item)
            valid_assets_by_concept[code].append(asset_id)
            detail_rows.append(_detail(code, item["concept_name"], asset_id, "valid", ""))

    # Deduplicate the source while retaining deterministic concept order.
    valid_rows = _dedupe_memberships(valid_rows)
    for code in valid_assets_by_concept:
        valid_assets_by_concept[code] = sorted(set(valid_assets_by_concept[code]))
    board_rows = [
        (TARGET_CONCEPT_SYSTEM, code, boards_by_code[code]["concept_name"], BOARD_SOURCE, True)
        for code in codes
        if code in boards_by_code
    ]
    membership_rows = [
        (
            item["asset_id"],
            TARGET_CONCEPT_SYSTEM,
            item["concept_code"],
            item["concept_name"],
            cutoff,
            MEMBERSHIP_SOURCE,
        )
        for item in valid_rows
    ]

    source_incomplete = bool(source_error or source_missing_codes or failed_concepts)
    write_blocked = bool(not dry_run and source_incomplete)
    write_blocked_reason = "source_incomplete" if write_blocked else ""
    database_writes = 0
    if not dry_run and not write_blocked:
        with connect(service) as conn:
            if board_rows:
                execute_many(conn, BOARD_UPSERT_SQL, board_rows)
                database_writes += len(board_rows)
            if membership_rows:
                execute_many(conn, MEMBERSHIP_UPSERT_SQL, membership_rows)
                database_writes += len(membership_rows)
            for code, assets in valid_assets_by_concept.items():
                # ``source_members`` is populated only after a successful
                # constituent response; failed/missing concepts never enter
                # this loop and therefore cannot close historical membership.
                execute(conn, CLOSE_MEMBERSHIP_SQL, [cutoff, TARGET_CONCEPT_SYSTEM, code, cutoff, assets])
                database_writes += 1

    out_of_scope_bse = sorted(set(out_of_scope_bse))
    failed_concepts = [code for code in codes if code in set(failed_concepts)]
    detail_rows.sort(key=lambda row: (row["concept_code"], row["asset_id"], row["status"]))
    summary: dict[str, Any] = {
        "schema_version": "rolling_sector_target_membership_backfill_v1",
        "trade_date": cutoff.isoformat(),
        "target_codes": list(codes),
        "target_code_count": len(codes),
        "source_board_count": len(boards_by_code),
        "source_missing_codes": source_missing_codes,
        "failed_concepts": failed_concepts,
        "source_error": source_error,
        "valid_non_bj_memberships": len(valid_rows),
        "valid_non_bj_membership_rows": valid_rows,
        "out_of_scope_bse": out_of_scope_bse,
        "out_of_scope_bse_count": len(out_of_scope_bse),
        "out_of_scope_900xxx": sorted(set(out_of_scope_900xxx)),
        "out_of_scope_900xxx_count": len(set(out_of_scope_900xxx)),
        "invalid_status_counts": invalid_statuses,
        "database_writes": 0 if dry_run else database_writes,
        "dry_run": bool(dry_run),
        "write_blocked": write_blocked,
        "write_blocked_reason": write_blocked_reason,
        "upsert_conflict_key": ["asset_id", "concept_system", "concept_code", "start_date"],
        "close_history_only_for_successful_concepts": True,
        "paths": {},
    }
    paths = _write_reports(summary, detail_rows, output_dir)
    summary["paths"] = paths
    summary["report_path"] = paths["json"]
    return summary


def _normalize_board_rows(frame: Any) -> list[dict[str, str]]:
    if frame is None:
        return []
    if isinstance(frame, pd.DataFrame):
        records = frame.to_dict("records")
    elif isinstance(frame, Mapping):
        records = [frame]
    else:
        records = list(frame)
    rows: list[dict[str, str]] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        name = str(
            item.get("concept_name")
            or item.get("name")
            or item.get("概念名称")
            or item.get("板块名称")
            or ""
        ).strip()
        code = str(
            item.get("concept_code")
            or item.get("code")
            or item.get("代码")
            or item.get("板块代码")
            or ""
        ).strip()
        if name and code:
            rows.append({"concept_code": code, "concept_name": name})
    return rows


def _normalize_constituent_rows(frame: Any, *, concept_code: str) -> list[dict[str, str]]:
    rows, _excluded_900xxx = _normalize_constituent_rows_with_exclusions(
        frame,
        concept_code=concept_code,
    )
    return rows


def _normalize_constituent_rows_with_exclusions(
    frame: Any,
    *,
    concept_code: str,
) -> tuple[list[dict[str, str]], list[str]]:
    if frame is None:
        return [], []
    if isinstance(frame, pd.DataFrame):
        records = frame.to_dict("records")
    elif isinstance(frame, Mapping):
        records = [frame]
    else:
        records = list(frame)
    rows: list[dict[str, str]] = []
    excluded_900xxx: list[str] = []
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, Mapping):
            continue
        raw = _row_asset_value(item)
        raw_900xxx = _raw_900xxx_code(raw)
        if raw_900xxx is not None:
            if raw_900xxx not in excluded_900xxx:
                excluded_900xxx.append(raw_900xxx)
            continue
        asset_id = _normalize_source_asset_id(raw)
        if asset_id is None:
            continue
        if asset_id in seen:
            continue
        seen.add(asset_id)
        rows.append({"concept_code": concept_code, "asset_id": asset_id})
    return rows, excluded_900xxx


def _is_empty_source_response(frame: Any) -> bool:
    if frame is None:
        return True
    if isinstance(frame, pd.DataFrame):
        return frame.empty
    if isinstance(frame, Mapping):
        return not frame
    if isinstance(frame, (str, bytes)):
        return not frame.strip()
    if isinstance(frame, (list, tuple, set, frozenset)):
        return len(frame) == 0
    return False


def _raw_900xxx_code(raw: object) -> str | None:
    value = str(raw or "").strip().upper()
    if not value:
        return None
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) == 6 and digits.startswith("900"):
        return digits
    return None


def _normalize_source_asset_id(raw: object) -> str | None:
    value = str(raw or "").strip().upper()
    if not value:
        return None
    if value.startswith("CN:"):
        parts = value.split(":")
        if len(parts) != 3:
            return None
        exchange, symbol = parts[1], parts[2]
        return _asset_id_from_cn_stock_code(f"{symbol}.{exchange}")
    return _asset_id_from_cn_stock_code(value)


def _row_asset_value(row: Mapping[str, object]) -> object:
    return (
        row.get("asset_id")
        or row.get("代码")
        or row.get("code")
        or row.get("股票代码")
        or row.get("symbol")
        or ""
    )


def _row_concept_code(row: Mapping[str, object]) -> str:
    return str(row.get("concept_code") or row.get("代码") or "").strip()


def _asset_eligibility(master: Mapping[str, object] | None, cutoff: date) -> tuple[str, str]:
    if master is None:
        return "missing_master", "asset is absent from core.asset_master"
    asset_id = str(master.get("asset_id") or "").upper()
    exchange = str(master.get("exchange") or "").upper()
    if exchange == "BJ" or asset_id.startswith("CN:BJ:") or bool(master.get("is_beijing")):
        return "out_of_scope_bse", "BSE is excluded"
    list_date = _optional_date(master.get("list_date"))
    delist_date = _optional_date(master.get("delist_date"))
    if list_date is not None and list_date > cutoff:
        return "inactive_pit", "asset was listed after trade_date"
    if delist_date is not None and delist_date <= cutoff:
        return "delisted", "asset was delisted by trade_date"
    if not bool(master.get("is_active", True)):
        # A current inactive flag can be observed before the frozen cutoff
        # because the asset was delisted later.  Only a known delist date after
        # the cutoff proves PIT eligibility; without that proof fail closed.
        if delist_date is not None and delist_date > cutoff:
            return "valid", ""
        return "inactive_pit", "asset_master.is_active is false without post-cutoff delist proof"
    return "valid", ""


def _dedupe_memberships(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["concept_code"], row["asset_id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
    return result


def _detail(concept_code: str, concept_name: str, asset_id: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "concept_code": concept_code,
        "concept_name": concept_name,
        "asset_id": asset_id,
        "status": status,
        "reason": reason,
    }


def _write_reports(
    summary: Mapping[str, Any], detail_rows: Sequence[Mapping[str, Any]], output_dir: str | Path
) -> dict[str, str]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "target_membership_backfill_summary.json"
    csv_path = root / "target_membership_backfill_rows.csv"
    payload = dict(summary)
    payload["paths"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in DETAIL_COLUMNS} for row in detail_rows])
    return {"json": str(json_path), "csv": str(csv_path)}


def _parse_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError(f"trade_date must be an ISO date: {value!r}") from exc


def _optional_date(value: object) -> date | None:
    if value is None or str(value).strip() in {"", "None", "nan", "NaT"}:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None
