"""Weekly Yanbaoke report top-up: gap-driven, budget-bounded collection.

Pipeline (A2 of the Data Assets & Operations line):
  candidate pool -> evidence-gap priority -> strict dedup -> weekly queue
  -> download (max 25/week, quota-ledgered) -> validated ingest ->
  source/event upsert -> pdf parse -> weekly ledger report.

Dedup identity: canonical ``report_id = yanbaoke_<uuid>``. The legacy
``hash(uuid + local_pdf_uri)`` scheme produced different report_ids for the
same report across machines/paths (293 duplicate groups / 595 rows found in
production at audit time); the uuid-only scheme is path-independent and makes
re-downloads naturally idempotent under the existing ON CONFLICT upsert.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.theme_company_yanbaoke_quota import (
    normalize_report_title,
)


DEFAULT_WEEKLY_LIMIT = 25
DEFAULT_PER_STOCK_CAP = 2
DEFAULT_PER_BROKER_CAP = 8
DEFAULT_STALE_DAYS = 120


def yanbaoke_report_id(row: dict[str, Any] | pd.Series) -> str:
    """Canonical, path-independent report id.

    uuid is the Yanbaoke global id -> ``yanbaoke_<uuid>``. Fallback for rows
    without uuid: a stable composite of content fields (never file paths).
    """

    import hashlib

    uuid = str(row.get("uuid") or "").strip()
    if uuid:
        return f"yanbaoke_{uuid}"
    token = hashlib.sha1(
        "|".join(
            [
                str(row.get("title") or row.get("report_title") or ""),
                str(row.get("ts_code") or ""),
                str(row.get("publish_date") or "")[:10],
                str(row.get("broker") or ""),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"yanbaoke_{token}"


def build_stock_priority_queue(
    coverage: pd.DataFrame,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    asof: str | None = None,
    thin_threshold: int = 3,
) -> pd.DataFrame:
    """Rank stocks by report-evidence gap.

    Buckets (research value of the next report, high -> low):
      ``no_coverage``     - zero reports on file;
      ``stale_coverage``  - newest report older than ``stale_days``;
      ``thin_recent``     - current but only <= thin_threshold reports;
      ``current``         - adequately covered (lowest fill priority).
    """

    frame = coverage.copy()
    if frame.empty:
        return frame.assign(priority_bucket=pd.Series(dtype="string"))
    asof_ts = pd.Timestamp(asof) if asof else pd.Timestamp.now().normalize()
    frame["report_count"] = pd.to_numeric(frame["report_count"], errors="coerce").fillna(0)
    frame["last_report_date"] = pd.to_datetime(frame["last_report_date"], errors="coerce")
    frame["days_since_last_report"] = (asof_ts - frame["last_report_date"]).dt.days

    def bucket(row: pd.Series) -> str:
        if int(row["report_count"]) == 0 or pd.isna(row["last_report_date"]):
            return "no_coverage"
        if int(row["days_since_last_report"] or 10**9) > stale_days:
            return "stale_coverage"
        if int(row["report_count"]) <= thin_threshold:
            return "thin_recent"
        return "current"

    frame["priority_bucket"] = frame.apply(bucket, axis=1)
    order = {"no_coverage": 0, "stale_coverage": 1, "thin_recent": 2, "current": 3}
    frame["_rank"] = frame["priority_bucket"].map(order)
    return frame.sort_values(
        ["_rank", "last_report_date", "report_count", "ts_code"],
        ascending=[True, True, True, True],
        na_position="first",
    ).drop(columns=["_rank"]).reset_index(drop=True)


def dedupe_weekly_candidates(
    candidates: pd.DataFrame,
    *,
    existing_uuids: set[str],
    existing_keys: set[tuple[str, str, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop candidates already collected.

    Identity = uuid, then composite (ts_code, broker, publish_date,
    normalized_title). Returns (kept, dropped-with-reasons).
    """

    frame = candidates.copy()
    if frame.empty:
        return frame, frame.assign(drop_reason=pd.Series(dtype="string"))
    frame["uuid"] = frame["uuid"].astype(str).str.strip()
    frame["_norm_title"] = frame.get(
        "normalized_title",
        frame.get("title", frame.get("report_title", pd.Series("", index=frame.index))),
    )
    frame["_norm_title"] = frame["_norm_title"].map(normalize_report_title)
    frame["_key"] = frame.apply(
        lambda r: (
            str(r.get("ts_code") or ""),
            str(r.get("broker") or ""),
            str(r.get("publish_date") or "")[:10],
            str(r["_norm_title"]),
        ),
        axis=1,
    )

    drop_reasons = []
    for _, row in frame.iterrows():
        key = row["_key"]
        if not row["uuid"]:
            drop_reasons.append("missing_uuid")
        elif not str(key[1]):
            drop_reasons.append("missing_broker")
        elif not str(key[2]):
            drop_reasons.append("missing_publish_date")
        elif row["uuid"] in set(existing_uuids):
            drop_reasons.append("uuid_exists")
        elif key in set(existing_keys):
            drop_reasons.append("composite_exists")
        else:
            drop_reasons.append("")
    frame["drop_reason"] = drop_reasons
    dropped = frame[frame["drop_reason"].ne("")].drop(
        columns=["_norm_title", "_key"]
    ).reset_index(drop=True)
    kept = frame[frame["drop_reason"].eq("")].reset_index(drop=True)
    # within-batch dedup: uuid first, then full composite incl. normalized
    # title so same broker+date *different* reports both survive.
    kept = kept.drop_duplicates(subset=["uuid"], keep="first")
    kept = kept.drop_duplicates(subset=["_key"], keep="first")
    kept = kept.drop(
        columns=["_norm_title", "_key", "drop_reason"]
    ).reset_index(drop=True)
    return kept, dropped


def choose_weekly_queue(
    candidates: pd.DataFrame,
    *,
    weekly_limit: int = DEFAULT_WEEKLY_LIMIT,
    per_stock_cap: int = DEFAULT_PER_STOCK_CAP,
    per_broker_cap: int = DEFAULT_PER_BROKER_CAP,
) -> pd.DataFrame:
    """Pick up to ``weekly_limit`` candidates — underfill, never pad.

    Ordering: allocation-bucket priority (evidence-gap stocks first) then
    priority_score then publish recency. Caps bound per-stock and
    per-broker concentration so 25 slots diversify.
    """

    frame = candidates.copy()
    if frame.empty or weekly_limit <= 0:
        return frame.head(0)
    if "priority_score" not in frame.columns:
        frame["priority_score"] = 0.0
    frame["priority_score"] = pd.to_numeric(frame["priority_score"], errors="coerce").fillna(0.0)
    bucket_order = {
        "no_coverage": 0,
        "stale_coverage": 1,
        "evidence_gap": 2,
        "thin_recent": 3,
        "new_candidate": 4,
        "current": 5,
        "general": 6,
    }
    frame["_bucket_rank"] = (
        frame.get("allocation_bucket", pd.Series("general", index=frame.index))
        .astype(str).map(bucket_order).fillna(6)
    )
    frame = frame.sort_values(
        ["_bucket_rank", "priority_score", "publish_date", "uuid"],
        ascending=[True, False, False, True],
        na_position="last",
    )
    chosen, stock_counts, broker_counts = [], {}, {}
    for row in frame.to_dict("records"):
        if len(chosen) >= weekly_limit:
            break
        code = str(row.get("ts_code") or "")
        broker = str(row.get("broker") or "")
        if stock_counts.get(code, 0) >= per_stock_cap:
            continue
        if broker and broker_counts.get(broker, 0) >= per_broker_cap:
            continue
        chosen.append(row)
        stock_counts[code] = stock_counts.get(code, 0) + 1
        if broker:
            broker_counts[broker] = broker_counts.get(broker, 0) + 1
    return pd.DataFrame(chosen, columns=frame.columns).drop(
        columns=["_bucket_rank"], errors="ignore"
    ).reset_index(drop=True)


def load_quota_ledger(path: str | Path) -> dict[str, Any]:
    """Persistent per-quota-period download attempt ledger."""

    p = Path(path)
    if not p.exists():
        return {"periods": {}}
    return json.loads(p.read_text())


def _write_quota_ledger(path: str | Path, ledger: dict[str, Any]) -> None:
    import os
    import tempfile

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(ledger, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


from contextlib import contextmanager


@contextmanager
def _quota_lock(path: str | Path):
    """Cross-process mutex for quota ledger read-modify-write."""

    import fcntl

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p.with_suffix(p.suffix + ".lock"), "a")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def record_download_intent(
    path: str | Path, period: str, uuid: str, ts_code: str
) -> bool:
    """Atomically record a download intent BEFORE the API call.

    Returns False if the uuid was already attempted this period — callers
    must not issue a second (possibly charged) request for it.
    """

    with _quota_lock(path):
        ledger = load_quota_ledger(path)
        slot = ledger["periods"].setdefault(period, {"attempts": {}})
        if uuid in slot["attempts"]:
            return False
        slot["attempts"][uuid] = {
            "ts_code": ts_code,
            "status": "attempted",
            "at": pd.Timestamp.now().isoformat(),
            "error": None,
        }
        _write_quota_ledger(path, ledger)
        return True


def update_download_status(
    path: str | Path,
    period: str,
    uuid: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    with _quota_lock(path):
        ledger = load_quota_ledger(path)
        attempt = ledger["periods"].setdefault(period, {"attempts": {}})["attempts"].setdefault(
            uuid, {"ts_code": "", "at": pd.Timestamp.now().isoformat()}
        )
        attempt["status"] = status
        attempt["error"] = error
        _write_quota_ledger(path, ledger)


def period_attempt_count(ledger: dict[str, Any], period: str) -> int:
    return len(ledger.get("periods", {}).get(period, {}).get("attempts", {}))


def attempted_uuids(ledger: dict[str, Any], period: str) -> set[str]:
    return set(ledger.get("periods", {}).get(period, {}).get("attempts", {}))


def load_weekly_ledger(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"weeks": []}
    return json.loads(p.read_text())


def append_weekly_ledger(path: str | Path, entry: dict[str, Any]) -> dict[str, Any]:
    ledger = load_weekly_ledger(path)
    weeks = [w for w in ledger["weeks"] if w.get("week_key") != entry.get("week_key")]
    weeks.append(entry)
    weeks = sorted(weeks, key=lambda w: str(w.get("week_key") or ""))
    ledger["weeks"] = weeks
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
    return ledger


def load_report_coverage(conn: Any, ts_codes: list[str] | None = None) -> pd.DataFrame:
    """Per-stock report coverage: count, last date, parsed-text count."""

    from stock_research.db import fetch_all

    # distinct report identity = uuid when present else report_id, so legacy
    # same-uuid/multi-report_id duplicates cannot inflate coverage.
    sql = """
    SELECT e.ts_code,
           count(DISTINCT COALESCE(NULLIF(s.metadata->'yanbaoke'->>'uuid',''), s.report_id))
               AS report_count,
           max(e.report_date)::text AS last_report_date,
           count(DISTINCT COALESCE(NULLIF(s.metadata->'yanbaoke'->>'uuid',''), s.report_id))
               FILTER (WHERE s.metadata->'yanbaoke'->>'local_pdf_path' IS NOT NULL
                       OR s.metadata->>'local_pdf_path' IS NOT NULL
                       OR s.metadata->>'pdf_path' IS NOT NULL
                       OR starts_with(s.source_url, 'file:'))
               AS pdf_count,
           count(DISTINCT COALESCE(NULLIF(s.metadata->'yanbaoke'->>'uuid',''), s.report_id))
               FILTER (WHERE (e.metadata->'pdf_extract'->>'pdf_text_extract_chars')::int > 0)
               AS parsed_count,
           count(DISTINCT COALESCE(NULLIF(s.metadata->'yanbaoke'->>'uuid',''), s.report_id))
               FILTER (WHERE (e.metadata->'pdf_extract'->>'pdf_text_extract_chars')::int > 0
                       AND (NULLIF(btrim(e.company_view), '') IS NOT NULL
                            OR NULLIF(btrim(e.risk_summary), '') IS NOT NULL
                            OR NULLIF(btrim(e.industry_view), '') IS NOT NULL))
               AS evidence_count
    FROM research.stock_report_event e
    JOIN research.stock_report_source s ON s.report_id = e.report_id
    {where}
    GROUP BY e.ts_code
    """
    params: list[Any] = []
    where = ""
    if ts_codes:
        where = "WHERE e.ts_code = ANY(%s)"
        params = [ts_codes]
    return pd.DataFrame(fetch_all(conn, sql.format(where=where), params))


def load_existing_uuids(conn: Any) -> set[str]:
    """Yanbaoke uuids already in the catalog (canonical dedup key)."""

    from stock_research.db import fetch_all

    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT metadata->'yanbaoke'->>'uuid' AS uuid
        FROM research.stock_report_source
        WHERE source_type = 'yanbaoke_api'
          AND metadata->'yanbaoke'->>'uuid' IS NOT NULL
        """,
        [],
    )
    return {str(row["uuid"]).strip() for row in rows if row.get("uuid")}


def load_existing_report_keys(conn: Any) -> set[tuple[str, str, str, str]]:
    """Composite dedup keys (ts_code, broker, publish_date, norm title)."""

    from stock_research.db import fetch_all

    rows = fetch_all(
        conn,
        """
        SELECT e.ts_code, s.broker, s.publish_date::text AS publish_date,
               s.report_title
        FROM research.stock_report_event e
        JOIN research.stock_report_source s ON s.report_id = e.report_id
        """,
        [],
    )
    return {
        (
            str(row.get("ts_code") or ""),
            str(row.get("broker") or ""),
            str(row.get("publish_date") or "")[:10],
            normalize_report_title(row.get("report_title")),
        )
        for row in rows
    }


def load_duplicate_uuid_inventory(conn: Any) -> pd.DataFrame:
    """READ-ONLY inventory of legacy same-uuid -> multi-report_id duplicates.

    One row per (uuid, report_id): pdf path, event count, downstream links.
    No cleanup is performed — remediation needs an explicit approved path.
    """

    from stock_research.db import fetch_all

    return pd.DataFrame(
        fetch_all(
            conn,
            """
            WITH dup AS (
                SELECT metadata->'yanbaoke'->>'uuid' AS uuid
                FROM research.stock_report_source
                WHERE source_type = 'yanbaoke_api'
                  AND NULLIF(metadata->'yanbaoke'->>'uuid','') IS NOT NULL
                GROUP BY 1 HAVING count(DISTINCT report_id) > 1
            )
            SELECT d.uuid, s.report_id, s.broker, s.publish_date::text AS publish_date,
                   s.report_title,
                   s.metadata->'yanbaoke'->>'local_pdf_path' AS pdf_path,
                   (SELECT count(*) FROM research.stock_report_event e
                     WHERE e.report_id = s.report_id) AS event_count
            FROM dup d
            JOIN research.stock_report_source s
              ON s.metadata->'yanbaoke'->>'uuid' = d.uuid
            ORDER BY d.uuid, s.report_id
            """,
            [],
        )
    )


def load_priority_universe(conn: Any) -> pd.DataFrame:
    """Priority stocks: tech-bottleneck review universe + theme-mapped names."""

    from stock_research.db import fetch_all

    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT u.stock_code AS symbol
        FROM research.tech_bottleneck_review_universe_stock u
        UNION
        SELECT DISTINCT m.company_code AS symbol
        FROM research.theme_research_company_mapping m
        WHERE m.is_active IS TRUE AND m.company_code ~ '^[0-9]{6}$'
        """,
        [],
    )
    symbols = [str(r["symbol"]).strip() for r in rows if r.get("symbol")]
    assets = fetch_all(
        conn,
        """
        SELECT ts_code, symbol, name AS stock_name, is_active
        FROM core.asset_master
        WHERE symbol = ANY(%s) AND is_active IS TRUE
        """,
        [symbols],
    )
    return pd.DataFrame(assets)


def build_weekly_plan(
    conn: Any,
    *,
    week_key: str,
    stale_days: int = DEFAULT_STALE_DAYS,
    thin_threshold: int = 3,
) -> dict[str, Any]:
    """Offline plan: priority stocks + dedup state. No API calls."""

    universe = load_priority_universe(conn)
    coverage = load_report_coverage(conn)
    merged = universe.merge(
        coverage, on="ts_code", how="left"
    ) if not coverage.empty else universe.assign(
        report_count=0, last_report_date=None, parsed_count=0
    )
    for col in ("report_count", "parsed_count"):
        merged[col] = merged.get(col, 0).fillna(0)
    queue = build_stock_priority_queue(
        merged, stale_days=stale_days, thin_threshold=thin_threshold
    )
    return {
        "week_key": week_key,
        "universe_size": int(len(universe)),
        "priority_queue": queue,
        "bucket_counts": queue["priority_bucket"].value_counts().to_dict()
        if not queue.empty else {},
        "existing_uuids": load_existing_uuids(conn),
        "existing_keys": load_existing_report_keys(conn),
    }


def run_yanbaoke_weekly_topup(
    *,
    week_key: str | None = None,
    weekly_limit: int = DEFAULT_WEEKLY_LIMIT,
    per_stock_cap: int = DEFAULT_PER_STOCK_CAP,
    per_broker_cap: int = DEFAULT_PER_BROKER_CAP,
    stale_days: int = DEFAULT_STALE_DAYS,
    search_top_stocks: int = 40,
    search_window_days: int = 45,
    output_dir: str | Path = "outputs/research/yanbaoke_weekly",
    ledger_path: str | Path = "outputs/research/yanbaoke_weekly/ledger.json",
    download_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
    dry_run: bool = True,
    write_db: bool = False,
    search_fn: Any | None = None,
    download_dir_root: str | Path | None = None,
    import_fn: Any | None = None,
    conn: Any | None = None,
    quota_ledger_path: str | Path | None = None,
    quota_budget: int | None = None,
    quota_period_key: str | None = None,
    filter_fn: Any | None = None,
    institutions_path: str | Path | None = None,
) -> dict[str, Any]:
    """One weekly top-up cycle. ``dry_run=True`` emits the plan with zero API.

    Quota: every download *attempt* is persisted in ``quota_ledger_path``
    BEFORE the API call, so a crash or rerun in the same ``quota_period_key``
    can never re-issue (and possibly re-charge) the same request. Total
    attempts per period are capped by ``quota_budget`` (default
    ``weekly_limit``); ``confirmed_charged`` stays None until the account
    balance is verified — attempts are a ceiling on possible charges, not a
    measurement of them.
    """

    from stock_research.db import connect

    week = week_key or pd.Timestamp.now().strftime("%G-W%V")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    managed = connect(service) if conn is None else None
    active = managed.__enter__() if managed else conn
    try:
        plan = build_weekly_plan(active, week_key=week, stale_days=stale_days)
        priority = plan["priority_queue"]
        search_universe = priority.head(search_top_stocks)
        plan_path = output / f"weekly_plan_{week}.csv"
        priority.to_csv(plan_path, index=False)

        if dry_run:
            return {
                "week_key": week,
                "dry_run": True,
                "priority_queue_path": str(plan_path),
                "bucket_counts": plan["bucket_counts"],
                "existing_uuids": len(plan["existing_uuids"]),
                "existing_keys": len(plan["existing_keys"]),
                "search_universe": int(len(search_universe)),
            }

        # --- candidate search (API) --------------------------------------
        if search_fn is None:
            from stock_research.yanbaoke_reports import search_yanbaoke_reports

            def search_fn(**kw):
                return search_yanbaoke_reports(**kw)

        if filter_fn is None:
            from stock_research.yanbaoke_reports import filter_yanbaoke_reports

            def filter_fn(reports, **kw):
                if institutions_path is not None:
                    kw.setdefault("institutions_path", institutions_path)
                return filter_yanbaoke_reports(reports, **kw)

        end = pd.Timestamp.now().strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=search_window_days)).strftime("%Y-%m-%d")
        candidate_rows = []
        search_calls = 0
        for row in search_universe.to_dict("records"):
            ts_code = str(row["ts_code"])
            name = str(row.get("stock_name") or ts_code.split(".")[0])
            try:
                result = search_fn(
                    keyword=name, size=30, search_type="title",
                    start_date=start, end_date=end,
                )
                search_calls += 1
            except Exception as exc:  # noqa: BLE001 - logged, continue
                candidate_rows.append({"ts_code": ts_code, "search_error": str(exc)})
                continue
            frame = result.get("reports")
            if frame is None or frame.empty:
                continue
            # standardize real API fields (org_name->broker, time->publish_date,
            # formats must include pdf, broker must match known institutions)
            frame = filter_fn(
                frame, ts_code=ts_code, stock_name=name,
                start_date=start, end_date=end,
            )
            if frame is None or frame.empty:
                continue
            frame = frame.copy()
            frame["ts_code"] = ts_code
            frame["allocation_bucket"] = row.get("priority_bucket", "general")
            candidate_rows.extend(frame.to_dict("records"))
        candidates = pd.DataFrame(candidate_rows)
        if not candidates.empty:
            for col in ("broker", "publish_date", "title", "uuid", "priority_score"):
                if col not in candidates.columns:
                    candidates[col] = "" if col != "priority_score" else 0.0
            candidates["priority_score"] = pd.to_numeric(
                candidates["priority_score"], errors="coerce"
            ).fillna(0.0)
            candidates["normalized_title"] = candidates.get(
                "title", candidates.get("report_title", "")
            ).map(normalize_report_title)

        kept, dropped = dedupe_weekly_candidates(
            candidates,
            existing_uuids=plan["existing_uuids"],
            existing_keys=plan["existing_keys"],
        )
        chosen = choose_weekly_queue(
            kept,
            weekly_limit=weekly_limit,
            per_stock_cap=per_stock_cap,
            per_broker_cap=per_broker_cap,
        )

        # --- persistent quota gate ----------------------------------------
        quota_path = Path(
            quota_ledger_path or Path(ledger_path).parent / "quota_ledger.json"
        )
        # quota refreshes MONTHLY (verified: 2026-07-01 refresh in prior ops
        # docs) — default period = calendar month, weekly_limit stays a plan cap.
        period = quota_period_key or pd.Timestamp.now().strftime("%Y-%m")
        # quota_budget = account-level attempts cap for the whole quota
        # period (monthly refresh). It is NOT the weekly plan limit and has
        # no safe default: when unverified (None), allowed=0 and no paid
        # download is issued — pass --quota-budget after balance check.
        quota_budget = int(quota_budget) if quota_budget is not None else 0
        quota = load_quota_ledger(quota_path)
        spent = period_attempt_count(quota, period)
        allowed = max(0, quota_budget - spent)
        already = attempted_uuids(quota, period)
        pre_filter = len(chosen)
        if already and not chosen.empty:
            chosen = chosen[~chosen["uuid"].astype(str).isin(already)]
        skipped_attempted = pre_filter - len(chosen)
        if len(chosen) > allowed:
            chosen = chosen.head(allowed)
        chosen_path = output / f"weekly_queue_{week}.csv"
        chosen.to_csv(chosen_path, index=False)

        # --- download + ingest -------------------------------------------
        downloads_dir = Path(download_dir or download_dir_root or output / f"pdfs_{week}")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        ledger = {
            "week_key": week,
            "quota_period": period,
            "weekly_limit": weekly_limit,
            "quota_budget": quota_budget,
            "search_calls": search_calls,
            "candidates_found": int(len(candidates)),
            "dedup_dropped": int(len(dropped)),
            "planned_downloads": int(len(chosen)),
            "attempts_period_before": spent,
            "attempts_this_run": 0,
            "confirmed_charged": None,  # unknown until balance verification
            "skipped_already_attempted": skipped_attempted,
            "downloaded": 0,
            "not_pdf": 0,
            "failed": 0,
            "imported": 0,
            "remaining_quota": None,
            "carryover_uuids": [],
            "errors": [],
        }
        downloaded_rows = []
        for row in chosen.to_dict("records"):
            uuid = str(row.get("uuid") or "")
            ts_code = str(row.get("ts_code") or "")
            if uuid in already or not record_download_intent(
                quota_path, period, uuid, ts_code
            ):
                ledger["skipped_already_attempted"] += 1
                ledger["carryover_uuids"].append(uuid)
                continue
            ledger["attempts_this_run"] += 1
            try:
                from stock_research.yanbaoke_reports import download_yanbaoke_report_pdf

                result = download_yanbaoke_report_pdf(uuid=uuid, output_dir=downloads_dir)
            except Exception as exc:  # noqa: BLE001
                update_download_status(quota_path, period, uuid, "failed", error=str(exc))
                ledger["failed"] += 1
                ledger["errors"].append(f"{uuid}: {exc}")
                ledger["carryover_uuids"].append(uuid)
                continue
            status = str(result.get("status") or "")
            update_download_status(quota_path, period, uuid, status or "not_pdf")
            if status == "downloaded":
                ledger["downloaded"] += 1
                downloaded_rows.append({**row, **result, "status": "downloaded"})
            else:
                ledger["not_pdf"] += 1
                ledger["carryover_uuids"].append(uuid)
        ledger["attempts_period_total"] = spent + ledger["attempts_this_run"]

        if downloaded_rows:
            downloads_df = pd.DataFrame(downloaded_rows)
            if import_fn is None:
                from stock_research.yanbaoke_reports import import_yanbaoke_report_downloads

                def import_fn(downloads, **kw):
                    return import_yanbaoke_report_downloads(downloads, **kw)

            import_result = import_fn(
                downloads_df,
                output_dir=output / f"import_{week}",
                write_db=write_db,
                service=service,
            )
            ledger["imported"] = int(
                import_result.get("summary", {}).get("source_rows", 0)
            )
        ledger["carryover_uuids"] = sorted(set(ledger["carryover_uuids"]))
        append_weekly_ledger(ledger_path, ledger)
        return {
            "week_key": week,
            "dry_run": False,
            "plan_path": str(plan_path),
            "queue_path": str(chosen_path),
            "ledger": ledger,
        }
    finally:
        if managed is not None:
            managed.__exit__(None, None, None)
