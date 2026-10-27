#!/usr/bin/env python3
"""P2.1-Final-A — CORRECTED raw-payload restatement forensics.

Payloads are list[dict]: each snapshot contains MANY report-period rows
(REPORT_DATE / NOTICE_DATE / REPORT_TYPE + metrics). Expand every
snapshot to (asset, endpoint, report_period, report_type) keys and
compare full metric vectors across fetched_at. Field-level classes:
missing_in_a / missing_in_b / null_asymmetry / precision / changed /
metadata_only. Empty extraction is counted as coverage failure, never
as "unchanged". READ-ONLY.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402

OUT = Path("docs/research_upgrade/p21/final")
PERIOD_KEYS = ("REPORT_DATE", "REPORTDATE", "报告期")
ANN_KEYS = ("NOTICE_DATE", "公告日期")
TYPE_KEYS = ("REPORT_TYPE",)
META_KEYS = {"UPDATE_DATE", "更新日期", "ORG_CODE", "ORG_TYPE", "CURRENCY",
             "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR", "公告日期",
             "NOTICE_DATE", "REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME",
             "序号", "变动日期"}


def to_rows(payload):
    """Expand a payload to list of period-row dicts."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("data", "result", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        return [payload]
    return []


def pkey(row):
    for k in PERIOD_KEYS:
        if row.get(k):
            return str(row[k])[:10]
    return None


def classify_fields(a: dict, b: dict):
    """a=earlier snapshot metrics, b=later. Return per-field class + worst."""
    keys = set(a) | set(b)
    per, worst = {}, "metadata_only"
    rank = {"changed": 5, "precision": 4, "null_asymmetry": 3,
            "missing": 2, "equal": 1, "metadata_only": 0}
    for k in keys:
        if k in META_KEYS:
            continue
        va, vb = a.get(k, "∅"), b.get(k, "∅")
        if va == "∅" or vb == "∅":
            c = "missing"
        elif va is None or vb is None:
            c = "null_asymmetry" if va != vb else "equal"
        else:
            try:
                fa, fb = float(va), float(vb)
                if fa == fb:
                    c = "equal"
                elif abs(fa - fb) <= max(abs(fa), abs(fb)) * 1e-4:
                    c = "precision"
                else:
                    c = "changed"
            except (TypeError, ValueError):
                c = "changed" if str(va) != str(vb) else "equal"
        per[k] = c
        if rank[c] > rank[worst]:
            worst = c
    return per, worst


def metrics_of(row):
    return {k: v for k, v in row.items() if k not in META_KEYS
            and not k.endswith("_YOY") and not k.endswith("DATE")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        n_bs = fetch_all(conn, "SELECT count(*) n FROM "
                         "raw_baostock.finance_payload")[0]["n"]
        rows = fetch_all(conn, """
          SELECT id, asset_id, source_endpoint ep, fetched_at::text ft,
                 payload::text pl, payload_hash ph
          FROM raw_akshare.finance_payload ORDER BY id""")

    # expand snapshots -> per (asset, ep, period) -> [(ft, metrics, row)]
    keys = defaultdict(list)
    extraction = Counter()
    for r in rows:
        try:
            pl = json.loads(r["pl"])
        except Exception:
            extraction["unparseable"] += 1
            continue
        prows = to_rows(pl)
        extraction["payload_rows"] += len(prows)
        for pr in prows:
            pk = pkey(pr)
            if pk is None:
                extraction["no_period_key"] += 1
                continue
            m = metrics_of(pr)
            extraction["extracted_nonempty" if m else
                       "extracted_empty"] += 1
            keys[(r["asset_id"], r["ep"], pk)].append(
                {"ft": r["ft"], "ph": r["ph"], "m": m, "id": r["id"],
                 "ann": pr.get("NOTICE_DATE") or pr.get("公告日期")})

    cls = Counter()
    events = []
    for (asset, ep, pk), snaps in keys.items():
        snaps.sort(key=lambda s: s["ft"])
        if len(snaps) == 1:
            cls["single_fetch"] += 1
            continue
        # earliest vs each later snapshot, pairwise worst
        first = snaps[0]
        key_worst, details = "equal", []
        for later in snaps[1:]:
            if later["ph"] == first["ph"]:
                c = "duplicate_refetch"
                continue
            if not first["m"] or not later["m"]:
                c = "extraction_empty"  # cannot claim unchanged
            else:
                per, w = classify_fields(first["m"], later["m"])
                c = {"equal": "payload_changed_same_metrics",
                     "metadata_only": "payload_changed_same_metrics",
                     "precision": "precision_only",
                     "missing": "field_missing_delta",
                     "null_asymmetry": "null_asymmetry_delta",
                     "changed": "metrics_changed"}[w]
                if w in ("changed", "missing", "null_asymmetry",
                         "precision"):
                    details.append({
                        "later_fetch": later["ft"], "raw_id": later["id"],
                        "field_diffs": {k: v for k, v in per.items()
                                        if v != "equal"}})
            rank2 = {"metrics_changed": 6, "field_missing_delta": 5,
                     "null_asymmetry_delta": 4, "precision_only": 3,
                     "extraction_empty": 2,
                     "payload_changed_same_metrics": 1,
                     "duplicate_refetch": 0, "equal": 0}
            if rank2[c] > rank2.get(key_worst, 0):
                key_worst = c
        cls[key_worst or "duplicate_refetch"] += 1
        if details:
            events.append({"asset_id": asset, "endpoint": ep,
                           "report_period": pk,
                           "first_fetch": first["ft"],
                           "first_raw_id": first["id"],
                           "first_ann": first["ann"],
                           "diffs": details[:5],
                           "initial_recoverable": bool(first["m"])})

    summary = {
        "raw_akshare_rows": len(rows), "raw_baostock_rows": n_bs,
        "expanded_snapshot_rows": extraction["payload_rows"],
        "extraction": dict(extraction),
        "version_keys": len(keys),
        "classification": dict(cls),
        "metrics_changed_keys": sum(1 for e in events),
        "initial_recoverable": sum(1 for e in events
                                   if e["initial_recoverable"]),
        "changed_events": events,
        "correction_note": "v1 grouped by params/top-level dict key -> "
                           "most list payloads collapsed into 'unknown'; "
                           "empty metric extraction counted as unchanged. "
                           "v2 expands every list row by REPORT_DATE.",
    }
    (OUT / "RESTATEMENT_FORENSICS_CORRECTED.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "changed_events"}, ensure_ascii=False,
                     indent=1))


if __name__ == "__main__":
    main()
