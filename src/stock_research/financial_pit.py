"""DATA-R3-P2/P2.1 — financial statements point-in-time interface.

Answers: at historical instant ``as_of``, which statement version could
an observer have known? Read-only; never used to generate signals.

Two-level selection (P2.1-B):
  1. pick the target report_period: explicit, or the latest period whose
     statement was publicly knowable at as_of (never earliest);
  2. within that period pick a version per ``version_policy`` and
     ``source_preference``, with deterministic tie-breaks.

Availability policy: day-level announcement dates cannot prove
pre-market vs post-market publication -> announced on D is knowable
from D+1 (strict ann < as_of). ``announcement_date = 1900-01-01`` is a
missing-date sentinel -> fail closed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

ANN_SENTINEL = "1900-01-01"
STATEMENT_TABLES = {
    "income": "finance.income_statement",
    "balance": "finance.balance_sheet",
    "cash_flow": "finance.cash_flow",
}
VERSION_POLICIES = ("latest_public", "initial_public")
# re-announcement signature: EM records the *latest* announcement of a
# period's figures; initial filing date is then lost.
REANNOUNCE_LAG_DAYS = 240


@dataclass
class FinancialPitResult:
    asset_id: str
    as_of: str
    statement_type: str
    report_period: str | None
    source: str | None
    publication_evidence: str | None      # announcement_date or None
    publicly_available_at_asof: bool
    operationally_available_at_asof: bool | None  # None = UNKNOWN
    selected_statement_version: str | None  # 'source@ann=<date>'
    restatement_of: str | None
    pit_status: str
    restriction_reasons: list[str] = field(default_factory=list)
    evidence_trace: dict[str, Any] = field(default_factory=dict)
    # M1-D credibility tiers
    data_version: str | None = None          # = selected_statement_version
    version_evidence_level: str = "UNKNOWN"  # VERIFIED/INFERRED/UNKNOWN
    missing_reason: str | None = None


def _as_date(v) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v)[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _pick_version(rows: list[dict], policy: str) -> dict:
    if policy == "initial_public":
        return min(rows, key=lambda r: str(r["announcement_date"]))
    return max(rows, key=lambda r: str(r["announcement_date"]))


def _pick_source(rows: list[dict], preference: tuple[str, ...]) -> dict:
    """Among rows already filtered to the chosen version date, pick by
    explicit source preference; stable alphabetical tie-break."""
    def key(r):
        try:
            return (preference.index(r["source"]), r["source"])
        except ValueError:
            return (len(preference), r["source"])
    return sorted(rows, key=key)[0]


def financial_pit_at(
    conn,
    asset_id: str,
    as_of,
    statement_type: str,
    report_period: str | None = None,
    version_policy: str = "latest_public",
    source_preference: tuple[str, ...] = (),
) -> FinancialPitResult:
    """Return the statement version knowable at ``as_of``.

    pit_status:
      verified_public            single version, ann < as_of
      restated_selected          same-source multi-ann versions exist
      historical_version_missing initial_public requested but the
                                 initial published version is
                                 unverifiable (surviving version may
                                 still be public — see reasons)
      not_yet_published          all statements ann >= as_of
      publication_date_missing   only sentinel/NULL ann rows
      period_not_reported        no rows for scope
    """
    if statement_type not in STATEMENT_TABLES:
        raise ValueError(
            f"statement_type must be one of {tuple(STATEMENT_TABLES)}")
    if version_policy not in VERSION_POLICIES:
        raise ValueError(
            f"version_policy must be one of {VERSION_POLICIES}")
    asof_d = _as_date(as_of)
    if asof_d is None:
        raise ValueError(f"illegal as_of: {as_of!r}")
    if report_period is not None and _as_date(report_period) is None:
        raise ValueError(f"illegal report_period: {report_period!r}")

    from stock_research.db import fetch_all
    table = STATEMENT_TABLES[statement_type]
    filters = ["asset_id = %s"]
    params: list[Any] = [asset_id]
    if report_period is not None:
        filters.append("report_period = %s")
        params.append(report_period)
    rows = fetch_all(conn, f"""
        SELECT asset_id, report_period::text AS report_period,
               report_type, announcement_date::text AS announcement_date,
               source, updated_at::text AS updated_at
        FROM {table}
        WHERE {' AND '.join(filters)}""", params)

    reasons: list[str] = []
    res = FinancialPitResult(
        asset_id=asset_id, as_of=str(asof_d),
        statement_type=statement_type, report_period=report_period,
        source=None, publication_evidence=None,
        publicly_available_at_asof=False,
        operationally_available_at_asof=None,
        selected_statement_version=None, restatement_of=None,
        pit_status="period_not_reported", restriction_reasons=reasons,
        evidence_trace={"table": table, "rows_seen": len(rows),
                        "version_policy": version_policy,
                        "source_preference": list(source_preference)})
    if not rows:
        reasons.append("no statement rows for asset/period")
        return res

    real = [r for r in rows if r["announcement_date"]
            and r["announcement_date"] != ANN_SENTINEL]
    if len(real) < len(rows):
        reasons.append(f"{len(rows)-len(real)} row(s) carry sentinel/NULL "
                       f"announcement_date (fail-closed)")
    if not real:
        res.pit_status = "publication_date_missing"
        return res

    known = [r for r in real if _as_date(r["announcement_date"]) < asof_d]
    if not known:
        res.pit_status = "not_yet_published"
        reasons.append("all statements announced at/after as_of "
                       "(D+1 conservative policy)")
        return res

    # level 1 — target report period: explicit or latest publicly known
    if res.report_period is None:
        res.report_period = max(r["report_period"] for r in known)
    period_rows = [r for r in known if r["report_period"]
                   == res.report_period]
    if not period_rows:
        res.pit_status = "not_yet_published"
        reasons.append(f"period {res.report_period} exists but no "
                       f"version was public by as_of")
        return res

    # level 2 — version policy within (period, source), then source pick
    per_src: dict[str, list[dict]] = {}
    for r in period_rows:
        per_src.setdefault(str(r["source"]), []).append(r)
    candidates = [_pick_version(v, version_policy)
                  for v in per_src.values()]
    # keep only candidates at the newest announcement across sources for
    # latest_public; for initial_public keep each source's earliest
    chosen = _pick_source(candidates, source_preference)
    restated = any(len(v) > 1 for v in per_src.values())

    res.source = chosen["source"]
    res.publication_evidence = chosen["announcement_date"]
    res.publicly_available_at_asof = True
    res.selected_statement_version = (
        f"{chosen['source']}@ann={chosen['announcement_date']}")
    others = [f"{r['source']}@ann={r['announcement_date']}"
              for r in period_rows if r is not chosen]
    if others:
        res.restatement_of = ",".join(sorted(set(others)))[:400]

    # updated_at is last-refresh, NOT first-seen: it cannot prove
    # operational availability at a past instant in either direction.
    res.operationally_available_at_asof = None
    reasons.append("operational availability UNKNOWN — updated_at is "
                   "a refresh timestamp, not first_seen evidence")
    res.evidence_trace["last_updated_at"] = chosen.get("updated_at")

    lag = (_as_date(chosen["announcement_date"])
           - _as_date(chosen["report_period"])).days
    # long lag is *suspicion* of re-announcement, not proof of the true
    # initial disclosure date (which may predate this row entirely).
    suspected = lag > REANNOUNCE_LAG_DAYS
    if suspected:
        reasons.append(f"ann-period lag {lag}d — suspected "
                       f"re-announcement (initial date unprovable)")
    # initial-version provability: only the earliest surviving version
    # inside a statutory-window announcement is treated as plausibly
    # initial; nothing here proves the true first publication.
    initial_provable = (not restated) and not suspected
    res.evidence_trace["initial_version_provable"] = initial_provable
    if version_policy == "initial_public" and not initial_provable:
        res.pit_status = "historical_version_missing"
        res.version_evidence_level = "UNKNOWN"
        res.missing_reason = "initial version unverifiable"
        reasons.append(
            "initial_public requested but the initial published version "
            "is unverifiable; the surviving version was public — do not "
            "consume it as a verified initial value")
    elif restated:
        res.pit_status = "restated_selected"
        res.version_evidence_level = "VERIFIED"
        reasons.append(f"same-source re-announcement on key; "
                       f"{version_policy} selected")
    else:
        res.pit_status = "verified_public"
        # window-based inference is not proof of the true first filing
        res.version_evidence_level = ("UNKNOWN" if suspected
                                      else "INFERRED")
        if suspected:
            res.missing_reason = ("suspected re-announcement; "
                                  "initial date unprovable")
    res.data_version = res.selected_statement_version
    if len(per_src) > 1:
        reasons.append(f"{len(per_src)} sources on key; "
                       f"preference={source_preference or 'alpha'}")
    return res
