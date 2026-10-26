"""DATA-R3-P2 — financial statements point-in-time interface.

Answers: at historical instant ``as_of``, which statement version could
an observer have known? Read-only; never used to generate signals.

Date semantics (P0-C):
  report_period_end  — period the statement covers (column report_period)
  announcement_date  — public disclosure DATE (day-level only in our DB)
  updated_at         — ingestion timestamp (operational availability)
  as_of              — the strategy decision instant (date or datetime)

Conservative availability policy: with day-level announcement dates we
cannot prove pre-market vs post-market publication. A statement
announced on date D is treated as knowable from D+1 (next calendar day
00:00). Same-day use is NOT allowed — a post-close filing must not be
visible at that day's open. ``announcement_date = 1900-01-01`` is a
missing-date sentinel and must fail closed, never pass as "long ago".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

ANN_SENTINEL = "1900-01-01"
STATEMENT_TABLES = {
    "income": "finance.income_statement",
    "balance": "finance.balance_sheet",
    "cash_flow": "finance.cash_flow",
}
VERSION_POLICIES = ("latest_public", "initial_public")


@dataclass
class FinancialPitResult:
    asset_id: str
    as_of: str
    statement_type: str
    report_period: str | None
    source: str | None
    publication_evidence: str | None      # announcement_date or None
    publicly_available_at_asof: bool
    operationally_available_at_asof: bool | None  # updated_at <= as_of
    selected_statement_version: str | None  # 'ann=<date>' or None
    restatement_of: str | None
    pit_status: str
    restriction_reasons: list[str]
    evidence_trace: dict[str, Any]


def _as_date(v) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def _pick_version(rows: list[dict], policy: str) -> dict | None:
    if not rows:
        return None
    if policy == "initial_public":
        return min(rows, key=lambda r: str(r["announcement_date"]))
    return max(rows, key=lambda r: (str(r["announcement_date"]),
                                    str(r["report_period"])))


def financial_pit_at(
    conn,
    asset_id: str,
    as_of: str | dt.date,
    statement_type: str,
    report_period: str | None = None,
    version_policy: str = "latest_public",
) -> FinancialPitResult:
    """Return the statement version knowable at ``as_of``.

    pit_status values:
      verified_public      — announcement_date known and strictly before
                             as_of+1 day (day-level conservatism)
      not_yet_published    — period ended but ann date after as_of
      publication_date_missing — sentinel/NULL announcement date
      period_not_reported  — no row at all for the requested scope
      restated_selected    — multiple versions exist; policy picked one
                             (annotated in restriction_reasons)
    """
    if statement_type not in STATEMENT_TABLES:
        raise ValueError(f"statement_type must be one of "
                         f"{tuple(STATEMENT_TABLES)}")
    if version_policy not in VERSION_POLICIES:
        raise ValueError(f"version_policy must be one of {VERSION_POLICIES}")
    table = STATEMENT_TABLES[statement_type]
    asof_d = _as_date(as_of)
    filters = ["asset_id = %s"]
    params: list[Any] = [asset_id]
    if report_period is not None:
        filters.append("report_period = %s")
        params.append(report_period)
    rows = conn_execute(
        conn, f"""
        SELECT asset_id, report_period::text AS report_period,
               report_type, announcement_date::text AS announcement_date,
               source, updated_at::text AS updated_at
        FROM {table}
        WHERE {' AND '.join(filters)}""", params)

    reasons: list[str] = []
    res = FinancialPitResult(
        asset_id=asset_id, as_of=str(asof_d or as_of),
        statement_type=statement_type, report_period=report_period,
        source=None, publication_evidence=None,
        publicly_available_at_asof=False,
        operationally_available_at_asof=None,
        selected_statement_version=None, restatement_of=None,
        pit_status="period_not_reported",
        restriction_reasons=reasons,
        evidence_trace={"table": table, "rows_seen": len(rows),
                        "version_policy": version_policy})
    if not rows:
        reasons.append("no statement rows for asset/period")
        return res

    valid = [r for r in rows
             if r["announcement_date"]
             and r["announcement_date"] != ANN_SENTINEL]
    sentinel = [r for r in rows
                if not r["announcement_date"]
                or r["announcement_date"] == ANN_SENTINEL]
    if sentinel:
        reasons.append(f"{len(sentinel)} row(s) lack a real "
                       f"announcement_date (sentinel/NULL)")
    if not valid:
        res.pit_status = "publication_date_missing"
        return res

    # day-level conservatism: announced on D -> knowable from D+1, so the
    # announcement day itself must be blocked (strict ann < as_of).
    known = [r for r in valid
             if _as_date(r["announcement_date"]) < asof_d
             if asof_d is not None]
    if asof_d is None:
        known = valid
    if not known:
        res.pit_status = "not_yet_published"
        periods = sorted({r["report_period"] for r in valid})
        reasons.append("all statements announced at/after "
                       f"as_of+1d (periods {periods[:4]})")
        return res

    chosen = _pick_version(known, version_policy)
    res.report_period = chosen["report_period"]
    res.source = chosen["source"]
    res.publication_evidence = chosen["announcement_date"]
    res.publicly_available_at_asof = True
    res.selected_statement_version = (
        f"{chosen['source']}@ann={chosen['announcement_date']}")
    upd = chosen.get("updated_at")
    if upd:
        res.operationally_available_at_asof = (
            _as_date(upd) <= asof_d if asof_d else None)
        if res.operationally_available_at_asof is False:
            reasons.append("statement was public by as_of but only "
                           "ingested later (operational gap)")
    # Restatement = same source carrying >1 announcement date for the key;
    # dual suppliers are NOT restatements.
    per_src: dict[str, set] = {}
    for r in rows:
        per_src.setdefault(str(r["source"]), set()).add(
            r["announcement_date"])
    restated = any(len(v) > 1 for v in per_src.values())
    if restated or len(known) > 1:
        res.pit_status = "restated_selected" if restated else "verified_public"
        if len(known) > 1 and not restated:
            res.pit_status = "verified_public"
        others = [r for r in rows if r is not chosen]
        res.restatement_of = ",".join(
            sorted({f"{r['source']}@ann={r['announcement_date']}"
                    for r in others}))[:400]
        if restated:
            reasons.append(f"{len(rows)} version row(s) incl. same-source "
                           f"re-announcement; {version_policy} selected")
        elif len(known) > 1:
            reasons.append(f"{len(known)} rows knowable at as_of "
                           f"(multi-source/period); {version_policy} selected")
    else:
        res.pit_status = "verified_public"
    return res


def conn_execute(conn, sql: str, params: list[Any]) -> list[dict]:
    from stock_research.db import fetch_all
    return fetch_all(conn, sql, params)
