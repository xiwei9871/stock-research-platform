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
from hashlib import sha256
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:  # pragma: no cover - dependency is provided by AkShare in production
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - unit tests can inject a compatible parser
    BeautifulSoup = None

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
MEMBERSHIP_SOURCE = "ths:q.10jqka.com.cn_gn_detail"
THS_MEMBER_CAP = 50
THS_SOURCE_CONTRACT = "ths:q.10jqka.com.cn_gn_detail_top50"

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
    "source_asof",
    "source_effective_date",
    "source_pit_status",
)

SNAPSHOT_REQUIRED_COLUMNS = ("concept_code", "concept_name", "asset_id")
SNAPSHOT_ASOF_COLUMNS = ("source_asof", "source_effective_date", "effective_date")


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


def load_historical_membership_snapshot(
    source: str | Path | pd.DataFrame,
    *,
    target_codes: Iterable[object],
    requested_date: date | str,
    source_asof: date | str | None = None,
) -> tuple[pd.DataFrame, date]:
    """Load and validate an explicit point-in-time membership snapshot.

    This is the file/import boundary for historical backfills.  The payload
    must carry (or the operator must explicitly provide) one effective date;
    current provider responses without that metadata are rejected.  The
    normalized frame contains one row per ``concept_code``/``asset_id`` and
    preserves the concept name needed by the board upsert.
    """

    requested = _parse_date(requested_date)
    codes = normalize_target_codes(target_codes)
    frame, metadata_asof = _read_membership_snapshot_payload(source)
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in SNAPSHOT_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"snapshot_missing_columns:{','.join(missing)}")
    if frame.empty:
        raise ValueError("snapshot_empty")

    asof_values: list[date] = []
    for column in SNAPSHOT_ASOF_COLUMNS:
        if column not in frame.columns:
            continue
        for value in frame[column].tolist():
            parsed = _parse_source_asof(value)
            if parsed is not None:
                asof_values.append(parsed)
    if metadata_asof is not None:
        asof_values.append(metadata_asof)
    if source_asof is not None:
        asof_values.append(_parse_source_asof(source_asof))
    distinct_asof = sorted({value for value in asof_values if value is not None})
    if not distinct_asof:
        raise ValueError("source_asof_unknown")
    if len(distinct_asof) != 1:
        raise ValueError("source_asof_mismatch")
    effective = distinct_asof[0]
    valid_asof, reason = validate_membership_source_asof(
        source_asof=effective,
        requested_date=requested,
    )
    if not valid_asof:
        raise ValueError(reason)

    target_set = set(codes)
    normalized_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for record in frame.to_dict("records"):
        concept_code = str(record.get("concept_code") or "").strip()
        if not TARGET_CODE_PATTERN.fullmatch(concept_code):
            raise ValueError(f"invalid_snapshot_concept_code:{concept_code!r}")
        if concept_code not in target_set:
            raise ValueError(f"snapshot_concept_code_outside_target:{concept_code}")
        concept_name = str(record.get("concept_name") or "").strip()
        if not concept_name:
            raise ValueError(f"snapshot_concept_name_missing:{concept_code}")
        asset_id = _normalize_source_asset_id(record.get("asset_id"))
        if asset_id is None:
            raise ValueError(f"invalid_snapshot_asset_id:{record.get('asset_id')!r}")
        key = (concept_code, asset_id)
        if key in seen:
            raise ValueError(f"duplicate_membership:{concept_code}:{asset_id}")
        seen.add(key)
        normalized_rows.append(
            {
                "concept_code": concept_code,
                "concept_name": concept_name,
                "asset_id": asset_id,
            }
        )
    present = {row["concept_code"] for row in normalized_rows}
    missing_codes = sorted(target_set - present)
    if missing_codes:
        raise ValueError(f"snapshot_missing_target_codes:{','.join(missing_codes)}")
    normalized = pd.DataFrame(
        sorted(normalized_rows, key=lambda row: (row["concept_code"], row["asset_id"])),
        columns=list(SNAPSHOT_REQUIRED_COLUMNS),
    )
    normalized.attrs["source_asof"] = effective
    normalized.attrs["source_effective_date"] = effective
    normalized.attrs["source_pit_status"] = "verified"
    normalized.attrs["source_payload_sha256"] = _snapshot_payload_sha256(source)
    normalized.attrs["source_kind"] = "historical_membership_snapshot"
    return normalized, effective


def _read_membership_snapshot_payload(
    source: str | Path | pd.DataFrame,
) -> tuple[pd.DataFrame, date | None]:
    if isinstance(source, pd.DataFrame):
        attrs = getattr(source, "attrs", {}) or {}
        metadata = _parse_source_asof(
            attrs.get("source_asof") or attrs.get("source_effective_date")
        )
        return source, metadata
    path = Path(source).expanduser()
    if not path.exists() or not path.is_file():
        raise ValueError(f"snapshot_file_not_found:{path}")
    suffix = path.suffix.lower()
    metadata_asof: date | None = None
    if suffix == ".csv":
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    elif suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"snapshot_json_invalid:{path}") from exc
        if isinstance(payload, Mapping):
            metadata_asof = _parse_source_asof(
                payload.get("source_asof") or payload.get("source_effective_date")
            )
            records = payload.get("rows") or payload.get("memberships") or payload.get("data")
        else:
            records = payload
        if not isinstance(records, list):
            raise ValueError("snapshot_json_rows_missing")
        frame = pd.DataFrame(records)
    else:
        raise ValueError(f"snapshot_file_type_unsupported:{suffix or 'none'}")
    return frame, metadata_asof


def _snapshot_payload_sha256(source: str | Path | pd.DataFrame) -> str | None:
    if isinstance(source, pd.DataFrame):
        payload = source.to_csv(index=False).encode("utf-8")
    else:
        path = Path(source).expanduser()
        try:
            payload = path.read_bytes()
        except OSError:
            return None
    return sha256(payload).hexdigest()


def fetch_target_concept_boards() -> Any:
    """Fetch the THS board list through the explicit AkShare adapter boundary."""

    if ak is None:
        raise RuntimeError("akshare package is required for target membership backfill")
    return ak.stock_board_concept_name_ths()


def fetch_target_concept_constituents(symbol: str) -> Any:
    """Fetch one board's constituents through the explicit THS adapter.

    ``symbol`` is the six-digit THS concept code when called by the executor.
    The previous EastMoney adapter remains available as
    :func:`fetch_target_concept_constituents_em` and is never selected
    implicitly.
    """

    return fetch_ths_detail_constituents(symbol)


def fetch_target_concept_constituents_em(symbol: str) -> Any:
    """Explicit EastMoney/AkShare fallback for operator-selected use only."""

    if ak is None:
        raise RuntimeError("akshare package is required for target membership backfill")
    return ak.stock_board_concept_cons_em(symbol)


# Keep an identity sentinel so tests/operator-injected fetchers cannot be
# mistaken for the production live THS endpoint.  A manually supplied
# ``--source-asof`` must never be enough to bless an unannotated live response.
_DEFAULT_THS_CONSTITUENT_FETCHER = fetch_target_concept_constituents


@lru_cache(maxsize=1)
def _get_ths_v_code() -> str:
    """Generate the THS ``v`` cookie using AkShare's bundled JavaScript."""

    try:
        import py_mini_racer
        from akshare.stock_feature.stock_board_concept_ths import _get_file_content_ths
    except Exception as exc:  # pragma: no cover - exercised with missing deps
        raise RuntimeError("THS adapter requires akshare and py_mini_racer") from exc
    try:
        js = py_mini_racer.MiniRacer()
        js.eval(_get_file_content_ths("ths.js"))
        value = str(js.call("v") or "").strip()
    except Exception as exc:  # noqa: BLE001 - source setup must fail closed
        raise RuntimeError(f"unable to generate THS v cookie: {exc}") from exc
    if not value:
        raise RuntimeError("THS v cookie is empty")
    return value


def fetch_ths_detail_constituents(
    concept_code: str,
    *,
    timeout_seconds: int = 20,
) -> pd.DataFrame:
    """Fetch all constituents from the paginated THS concept detail table."""

    code = normalize_target_codes((concept_code,))[0]
    if BeautifulSoup is None:
        raise RuntimeError("THS adapter requires beautifulsoup4")
    v_code = _get_ths_v_code()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Cookie": f"v={v_code}",
    }
    session = requests.Session()
    try:
        first_url = _ths_detail_url(code, 1)
        first_response = session.get(first_url, headers=headers, timeout=timeout_seconds)
        first_soup = _validate_ths_response(first_response)
        total_pages = _parse_ths_total_pages(first_soup, expected_page=1)
        rows: list[dict[str, str]] = []
        seen_codes: set[str] = set()
        _append_new_ths_page_rows(
            rows,
            _parse_ths_detail_table(first_soup),
            seen_codes,
        )
        if len(rows) >= THS_MEMBER_CAP:
            rows = rows[:THS_MEMBER_CAP]
        for page in range(2, total_pages + 1):
            if len(rows) >= THS_MEMBER_CAP:
                break
            response = session.get(
                _ths_detail_url(code, page),
                headers=headers,
                timeout=timeout_seconds,
            )
            soup = _validate_ths_response(response)
            page_total = _parse_ths_total_pages(soup, expected_page=page)
            if page_total != total_pages:
                raise RuntimeError("page_count_mismatch")
            page_rows = _parse_ths_detail_table(soup)
            _append_new_ths_page_rows(rows, page_rows, seen_codes)
            if len(rows) >= THS_MEMBER_CAP:
                rows = rows[:THS_MEMBER_CAP]
                break
        if not rows:
            raise RuntimeError("empty_response")
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if row["代码"] in seen:
                continue
            seen.add(row["代码"])
            deduped.append(row)
        frame = pd.DataFrame(deduped[:THS_MEMBER_CAP], columns=["代码", "名称"])
        frame.attrs["member_cap_applied"] = len(rows) >= THS_MEMBER_CAP
        frame.attrs["source_contract_complete"] = True
        frame.attrs["source_total_pages"] = total_pages
        frame.attrs["source_member_cap"] = THS_MEMBER_CAP
        # This endpoint is a live ranking sorted by field 199112 (涨跌幅).  It
        # exposes no historical effective date, so callers must never infer
        # that the returned constituents are valid for a requested past date.
        frame.attrs["source_asof"] = None
        frame.attrs["source_effective_date"] = None
        frame.attrs["source_pit_status"] = "current_unknown_asof"
        return frame
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def _ths_detail_url(
    concept_code: str,
    page: int,
    *,
    cache_buster: str | int | None = None,
) -> str:
    value = page if cache_buster is None else cache_buster
    return (
        "https://q.10jqka.com.cn/gn/detail/board/0/field/199112/order/desc/"
        f"page/{page}/code/{concept_code}/?cb={value}"
    )


def _validate_ths_response(response: Any):
    status_code = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", "") or "")
    if status_code == 401:
        raise RuntimeError("ths_auth_challenge HTTP 401")
    if status_code != 200:
        raise RuntimeError(f"HTTP {status_code}")
    if not text.strip() or _looks_like_ths_auth_challenge(text):
        raise RuntimeError("ths_auth_challenge")
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type", headers.get("content-type", ""))).lower()
    if "html" not in content_type and "<html" not in text.lower():
        raise RuntimeError("non_html_response")
    soup = BeautifulSoup(text, features="lxml")
    if soup is None:
        raise RuntimeError("non_html_response")
    return soup


def _append_new_ths_page_rows(
    rows: list[dict[str, str]],
    page_rows: Iterable[Mapping[str, str]],
    seen_codes: set[str],
) -> None:
    """Append one page while rejecting a repeated/stalled page.

    THS occasionally returns the previous page (or a challenge response that
    parses as the same table) without changing the page number.  Treating
    that as a successful empty delta would silently produce an incomplete
    snapshot, so every page before the member cap must contribute a new code.
    """

    page_codes = {str(row.get("代码") or "").strip() for row in page_rows}
    page_codes.discard("")
    new_codes = page_codes - seen_codes
    if not new_codes:
        raise RuntimeError("duplicate_or_stalled_page")
    for row in page_rows:
        code = str(row.get("代码") or "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        rows.append(dict(row))


def _parse_ths_total_pages(soup: Any, *, expected_page: int | None = None) -> int:
    page_info = soup.select_one(".m-page .page_info") or soup.select_one(".page_info")
    text = page_info.get_text(" ", strip=True) if page_info is not None else ""
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match is None:
        table = soup.select_one(".m-table.m-pager-table")
        if expected_page in (None, 1) and table is not None and _table_has_code_row(table):
            return 1
        raise RuntimeError("page_count_unavailable")
    current = int(match.group(1))
    total = int(match.group(2))
    if expected_page is not None and current != expected_page:
        raise RuntimeError("page_mismatch")
    if total < 1 or total > 10000:
        raise RuntimeError("invalid_page_count")
    return total


def _table_has_code_row(table: Any) -> bool:
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        if re.search(r"\d{6}", cells[1].get_text(" ", strip=True)):
            return True
    return False


def _looks_like_ths_auth_challenge(text: str) -> bool:
    # Normal THS detail pages are large full HTML documents and may include
    # client-side challenge/login script names in otherwise valid markup.  A
    # short response is the reliable signal for the compact login/challenge
    # body returned by the endpoint when the cookie is rejected.
    if len(text) > 5000:
        return False
    lower = text.lower()
    return any(
        marker in lower
        for marker in (
            "请先登录",
            "请登录",
            "登录后",
            "captcha",
            "challenge",
            "verify you are human",
            "upass.10jqka.com.cn/login",
            "location.href",
            "chameleon",
        )
    )


def _parse_ths_detail_table(soup: Any) -> list[dict[str, str]]:
    table = soup.select_one(".m-table.m-pager-table")
    if table is None:
        raise RuntimeError("table_not_found")
    rows: list[dict[str, str]] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        code_text = cells[1].get_text(" ", strip=True)
        code_match = re.search(r"\d{6}", code_text)
        if code_match is None:
            continue
        name = cells[2].get_text(" ", strip=True) if len(cells) >= 3 else ""
        rows.append({"代码": code_match.group(0), "名称": name})
    if not rows:
        raise RuntimeError("empty_response")
    return rows


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


def validate_membership_source_asof(
    *,
    source_asof: date | str | None,
    requested_date: date | str,
) -> tuple[bool, str]:
    """Return whether source metadata proves a point-in-time snapshot.

    Historical writes require an explicit source effective date that is no
    later than the requested snapshot date.  Missing metadata and live/future
    snapshots fail closed with stable machine-readable reasons.
    """

    requested = _parse_date(requested_date)
    effective = _parse_source_asof(source_asof)
    if effective is None:
        return False, "source_asof_unknown"
    if effective > requested:
        return False, "source_asof_after_requested_date"
    return True, ""


def run_target_membership_backfill(
    *,
    trade_date: date | str,
    target_codes: str | Path | Iterable[object] | pd.DataFrame,
    source_asof: date | str | None = None,
    membership_snapshot_file: str | Path | pd.DataFrame | None = None,
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
    source_effective = _parse_source_asof(source_asof)
    snapshot_frame: pd.DataFrame | None = None
    snapshot_error = ""
    snapshot_payload_sha256: str | None = None
    source_kind = "ths_current_unknown_asof"
    board_source = BOARD_SOURCE
    membership_source = MEMBERSHIP_SOURCE
    if membership_snapshot_file is not None:
        try:
            snapshot_frame, snapshot_effective = load_historical_membership_snapshot(
                membership_snapshot_file,
                target_codes=codes,
                requested_date=cutoff,
                source_asof=source_effective,
            )
            source_effective = snapshot_effective
            source_kind = str(snapshot_frame.attrs.get("source_kind") or "historical_membership_snapshot")
            snapshot_payload_sha256 = snapshot_frame.attrs.get("source_payload_sha256")
            source_label = (
                f"file:{Path(membership_snapshot_file).name}"
                if not isinstance(membership_snapshot_file, pd.DataFrame)
                else "file:in_memory_snapshot"
            )
            board_source = source_label
            membership_source = source_label
        except Exception as exc:  # noqa: BLE001 - import boundary fails closed
            snapshot_error = str(exc)
    source_pit_verified, source_asof_reason = validate_membership_source_asof(
        source_asof=source_effective,
        requested_date=cutoff,
    )
    source_effective_text = source_effective.isoformat() if source_effective else None
    if source_pit_verified:
        source_pit_status = "verified"
    elif source_asof_reason == "source_asof_unknown":
        source_pit_status = "current_unknown_asof"
    else:
        source_pit_status = "after_requested_date"
    if snapshot_frame is not None:
        snapshot_boards = (
            snapshot_frame[["concept_code", "concept_name"]]
            .drop_duplicates(subset=["concept_code"])
            .to_dict("records")
        )

        def fetch_boards_from_snapshot():
            return snapshot_boards

        def fetch_constituents_from_snapshot(symbol):
            frame = snapshot_frame.loc[
                snapshot_frame["concept_code"].astype(str) == str(symbol).strip(),
                ["asset_id", "concept_name"],
            ].copy()
            frame.attrs.update(snapshot_frame.attrs)
            return frame

        fetch_boards = fetch_boards_from_snapshot
        fetch_constituents = fetch_constituents_from_snapshot
        custom_constituent_fetcher = False
    elif membership_snapshot_file is not None:
        # A requested snapshot file that failed validation must not fall back
        # to the live THS endpoint.  Keep the report auditable and preserve DB.
        fetch_boards = lambda: []
        fetch_constituents = lambda _symbol: []
        custom_constituent_fetcher = False
    else:
        fetch_boards = board_fetcher or fetch_target_concept_boards
        fetch_constituents = constituent_fetcher or fetch_target_concept_constituents
        custom_constituent_fetcher = constituent_fetcher is not None
    using_live_ths_source = (
        snapshot_frame is None
        and membership_snapshot_file is None
        and constituent_fetcher is None
        and fetch_target_concept_constituents is _DEFAULT_THS_CONSTITUENT_FETCHER
    )
    load_master = asset_master_loader or load_target_asset_master

    source_missing_codes: list[str] = []
    failed_concepts: list[str] = []
    source_error = snapshot_error
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
    member_cap_applied_concepts: list[str] = []
    live_source_asof_values: set[date] = set()
    live_source_asof_unknown = False

    for code in codes:
        board = boards_by_code.get(code)
        if board is None:
            detail_rows.append(
                _detail(code, "", "", "source_missing", "target code not present in THS board list")
            )
            continue
        try:
            # The default THS detail adapter requires the board code.  An
            # injected adapter keeps the historical name-based test/operator
            # boundary, without re-fetching the full board list per concept.
            fetch_symbol = board["concept_name"] if custom_constituent_fetcher else code
            raw_constituents = fetch_constituents(fetch_symbol)
            source_attrs = getattr(raw_constituents, "attrs", {})
            if using_live_ths_source:
                live_asof = _parse_source_asof(
                    source_attrs.get("source_asof")
                    or source_attrs.get("source_effective_date")
                    if isinstance(source_attrs, Mapping)
                    else None
                )
                if live_asof is None:
                    live_source_asof_unknown = True
                else:
                    live_source_asof_values.add(live_asof)
            if isinstance(source_attrs, Mapping) and source_attrs.get("member_cap_applied"):
                member_cap_applied_concepts.append(code)
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

        if not source_members[code]:
            failed_concepts.append(code)
            detail_rows.append(
                _detail(
                    code,
                    board["concept_name"],
                    "",
                    "source_failed",
                    "no_valid_non_bj_source_members",
                )
            )
            # A source response containing only BSE members is not a valid
            # snapshot for this strategy.  Do not let it close old history.
            source_members.pop(code, None)

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

    for code in list(valid_assets_by_concept):
        if valid_assets_by_concept[code]:
            continue
        board = boards_by_code[code]
        failed_concepts.append(code)
        detail_rows.append(
            _detail(
                code,
                board["concept_name"],
                "",
                "source_failed",
                "no_valid_non_bj_pit_members",
            )
        )
        # A source response whose every member fails PIT/master eligibility is
        # incomplete for the frozen snapshot.  Preserve prior history by
        # excluding the concept from the history-close loop.
        del valid_assets_by_concept[code]

    # Deduplicate the source while retaining deterministic concept order.
    valid_rows = _dedupe_memberships(valid_rows)
    for code in valid_assets_by_concept:
        valid_assets_by_concept[code] = sorted(set(valid_assets_by_concept[code]))
    board_rows = [
        (TARGET_CONCEPT_SYSTEM, code, boards_by_code[code]["concept_name"], board_source, True)
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
            membership_source,
        )
        for item in valid_rows
    ]

    source_incomplete = bool(source_error or source_missing_codes or failed_concepts)
    if using_live_ths_source:
        if live_source_asof_unknown:
            source_pit_verified = False
            source_asof_reason = "source_asof_unknown"
            source_pit_status = "current_unknown_asof"
        elif len(live_source_asof_values) != 1:
            source_pit_verified = False
            source_asof_reason = "source_asof_unknown"
            source_pit_status = "current_unknown_asof"
        else:
            live_source_asof = next(iter(live_source_asof_values))
            if source_effective is None:
                source_effective = live_source_asof
                source_effective_text = source_effective.isoformat()
                source_pit_verified, source_asof_reason = validate_membership_source_asof(
                    source_asof=source_effective,
                    requested_date=cutoff,
                )
                source_pit_status = "verified" if source_pit_verified else "after_requested_date"
            elif source_effective != live_source_asof:
                source_pit_verified = False
                source_asof_reason = "source_asof_mismatch"
                source_pit_status = "current_unknown_asof"
    write_blocked = not source_pit_verified or source_incomplete
    if not source_pit_verified:
        write_blocked_reason = source_asof_reason
    elif source_incomplete:
        write_blocked_reason = "source_incomplete"
    else:
        write_blocked_reason = ""
    database_writes = 0
    if not dry_run and not write_blocked:
        with connect(service) as conn:
            if board_rows:
                execute_many(conn, BOARD_UPSERT_SQL, board_rows)
                database_writes += len(board_rows)
            if membership_rows:
                execute_many(conn, MEMBERSHIP_UPSERT_SQL, membership_rows)
                database_writes += len(membership_rows)
            for code in valid_assets_by_concept:
                # ``source_members`` is populated only after a successful
                # constituent response; failed/missing concepts never enter
                # this loop and therefore cannot close historical membership.
                execute(conn, CLOSE_MEMBERSHIP_SQL, [cutoff, TARGET_CONCEPT_SYSTEM, code, cutoff])
                database_writes += 1

    out_of_scope_bse = sorted(set(out_of_scope_bse))
    failed_concepts = [code for code in codes if code in set(failed_concepts)]
    detail_rows.sort(key=lambda row: (row["concept_code"], row["asset_id"], row["status"]))
    summary: dict[str, Any] = {
        "schema_version": "rolling_sector_target_membership_backfill_v1",
        "trade_date": cutoff.isoformat(),
        "source_asof": source_effective_text,
        "source_effective_date": source_effective_text,
        "source_pit_status": source_pit_status,
        "source_kind": source_kind,
        "membership_snapshot_file": (
            str(membership_snapshot_file) if membership_snapshot_file is not None else None
        ),
        "snapshot_payload_sha256": snapshot_payload_sha256,
        "target_codes": list(codes),
        "target_code_count": len(codes),
        "source_board_count": len(boards_by_code),
        "source_missing_codes": source_missing_codes,
        "failed_concepts": failed_concepts,
        "source_error": source_error,
        "source_member_cap": THS_MEMBER_CAP,
        "source_contract": THS_SOURCE_CONTRACT,
        "member_cap_applied_concepts": sorted(set(member_cap_applied_concepts)),
        "member_cap_applied_concept_count": len(set(member_cap_applied_concepts)),
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
    source_fields = {
        "source_asof": summary.get("source_asof"),
        "source_effective_date": summary.get("source_effective_date"),
        "source_pit_status": summary.get("source_pit_status", ""),
    }
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            [
                {
                    key: row.get(key, source_fields.get(key, ""))
                    for key in DETAIL_COLUMNS
                }
                for row in detail_rows
            ]
        )
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


def _parse_source_asof(value: date | str | None) -> date | None:
    if value is None or not str(value).strip():
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError(f"source_asof must be an ISO date: {value!r}") from exc


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
