from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import time
from typing import Any

import pandas as pd

from .config import SETTINGS
from .db import connect, execute_many, fetch_all


VENDOR_SOURCE = "akshare:stock_board_concept_index_ths"
UPSERT_COLUMNS = (
    "concept_system",
    "concept_code",
    "concept_name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "preclose",
    "volume",
    "amount",
    "stock_count",
    "up_count",
    "down_count",
    "source",
)


def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def normalize_concept_history(
    frame: pd.DataFrame,
    *,
    concept_system: str,
    concept_code: str,
    concept_name: str,
    source: str = VENDOR_SOURCE,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> list[dict[str, Any]]:
    required = {"日期", "收盘价"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"concept history missing columns: {sorted(missing)}")

    start = _as_date(start_date)
    end = _as_date(end_date)
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["日期"], errors="coerce").dt.date
    normalized["close"] = pd.to_numeric(normalized["收盘价"], errors="coerce")
    for vendor_column, local_column in (
        ("开盘价", "open"),
        ("最高价", "high"),
        ("最低价", "low"),
        ("成交量", "volume"),
        ("成交额", "amount"),
    ):
        normalized[local_column] = pd.to_numeric(
            normalized[vendor_column], errors="coerce"
        ) if vendor_column in normalized.columns else None

    normalized = normalized.dropna(subset=["trade_date", "close"])
    if start is not None:
        normalized = normalized[normalized["trade_date"] >= start]
    if end is not None:
        normalized = normalized[normalized["trade_date"] <= end]
    normalized = normalized.sort_values("trade_date").drop_duplicates(
        subset=["trade_date"], keep="last"
    )
    normalized["preclose"] = normalized["close"].shift(1)

    rows: list[dict[str, Any]] = []
    for item in normalized.to_dict("records"):
        rows.append(
            {
                "concept_system": concept_system,
                "concept_code": concept_code,
                "concept_name": concept_name,
                "trade_date": item["trade_date"],
                "open": _as_float(item.get("open")),
                "high": _as_float(item.get("high")),
                "low": _as_float(item.get("low")),
                "close": _as_float(item.get("close")),
                "preclose": _as_float(item.get("preclose")),
                "volume": _as_float(item.get("volume")),
                "amount": _as_float(item.get("amount")),
                "stock_count": None,
                "up_count": None,
                "down_count": None,
                "source": source,
            }
        )
    return rows


def build_upsert_rows(rows: Iterable[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [tuple(row.get(column) for column in UPSERT_COLUMNS) for row in rows]


UPSERT_SQL = """
INSERT INTO market.concept_daily_bar AS target (
    concept_system,
    concept_code,
    concept_name,
    trade_date,
    open,
    high,
    low,
    close,
    preclose,
    volume,
    amount,
    stock_count,
    up_count,
    down_count,
    source
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (concept_system, concept_code, trade_date) DO UPDATE SET
    concept_name = EXCLUDED.concept_name,
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    preclose = EXCLUDED.preclose,
    volume = EXCLUDED.volume,
    amount = EXCLUDED.amount,
    stock_count = COALESCE(target.stock_count, EXCLUDED.stock_count),
    up_count = COALESCE(target.up_count, EXCLUDED.up_count),
    down_count = COALESCE(target.down_count, EXCLUDED.down_count),
    source = EXCLUDED.source,
    updated_at = now()
"""


def load_active_concept_boards(conn, concept_system: str = "ths") -> list[dict[str, Any]]:
    return fetch_all(
        conn,
        """
        SELECT concept_code, concept_name
        FROM core.concept_board
        WHERE concept_system = %s
          AND is_active
        ORDER BY concept_code
        """,
        [concept_system],
    )


def load_latest_market_date(conn) -> date:
    rows = fetch_all(
        conn,
        """
        SELECT max(trade_date) AS latest_date
        FROM public.market_daily_bar
        WHERE adjust_type = 'qfq'
        """,
    )
    latest = rows[0].get("latest_date") if rows else None
    if latest is None:
        raise RuntimeError("public.market_daily_bar has no qfq trade date")
    return latest


def fetch_concept_history(
    board: dict[str, Any],
    *,
    start_date: date,
    end_date: date,
    fetcher: Callable[..., pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    if fetcher is None:
        import akshare as ak

        fetcher = ak.stock_board_concept_index_ths
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        frame = fetcher(
            symbol=str(board["concept_name"]),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
    return normalize_concept_history(
        frame,
        concept_system=str(board["concept_system"]),
        concept_code=str(board["concept_code"]),
        concept_name=str(board["concept_name"]),
        source=VENDOR_SOURCE,
        start_date=start_date,
        end_date=end_date,
    )


def upsert_concept_daily_rows(conn, rows: Iterable[dict[str, Any]]) -> int:
    payload = build_upsert_rows(rows)
    if not payload:
        return 0
    execute_many(conn, UPSERT_SQL, payload)
    return len(payload)


@dataclass
class BackfillSummary:
    concept_system: str
    start_date: date
    end_date: date
    boards_total: int
    boards_succeeded: int = 0
    boards_empty: int = 0
    rows_upserted: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "concept_system": self.concept_system,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "boards_total": self.boards_total,
            "boards_succeeded": self.boards_succeeded,
            "boards_empty": self.boards_empty,
            "rows_upserted": self.rows_upserted,
            "failures": self.failures,
        }


def backfill_concept_daily_bars(
    *,
    start_date: date,
    end_date: date | None = None,
    concept_system: str = "ths",
    service: str = SETTINGS.research_service,
    workers: int = 1,
    offset: int = 0,
    limit: int | None = None,
    concept_name: str | None = None,
    dry_run: bool = False,
    fetcher: Callable[..., pd.DataFrame] | None = None,
    retry_attempts: int = 3,
) -> dict[str, Any]:
    if workers != 1:
        raise ValueError(
            "AkShare THS history uses py_mini_racer and must run with workers=1; "
            "use separate offset/limit processes for parallel shards"
        )
    if offset < 0:
        raise ValueError("offset must be non-negative")
    with connect(service) as conn:
        latest_market_date = load_latest_market_date(conn)
        boards = load_active_concept_boards(conn, concept_system)
    resolved_end = min(end_date or latest_market_date, latest_market_date)
    if concept_name:
        boards = [board for board in boards if board["concept_name"] == concept_name]
    if offset:
        boards = boards[offset:]
    if limit is not None:
        boards = boards[: max(0, limit)]

    for board in boards:
        board["concept_system"] = concept_system
    summary = BackfillSummary(
        concept_system=concept_system,
        start_date=start_date,
        end_date=resolved_end,
        boards_total=len(boards),
    )

    def fetch_one(board: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        last_error: Exception | None = None
        for attempt in range(max(1, retry_attempts)):
            try:
                return board, fetch_concept_history(
                    board,
                    start_date=start_date,
                    end_date=resolved_end,
                    fetcher=fetcher,
                )
            except Exception as exc:  # noqa: BLE001 - one vendor failure must not stop all boards.
                last_error = exc
                if attempt + 1 < max(1, retry_attempts):
                    time.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    def persist(board: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        if dry_run or not rows:
            return
        with connect(service) as conn:
            upsert_concept_daily_rows(conn, rows)

    def consume(result) -> None:
        board, rows = result
        if rows:
            persist(board, rows)
            summary.boards_succeeded += 1
            summary.rows_upserted += len(rows)
        else:
            summary.boards_empty += 1

    if workers <= 1:
        for board in boards:
            try:
                consume(fetch_one(board))
            except Exception as exc:  # noqa: BLE001 - record and continue.
                summary.failures.append(
                    {
                        "concept_code": str(board["concept_code"]),
                        "concept_name": str(board["concept_name"]),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return summary.as_dict()
