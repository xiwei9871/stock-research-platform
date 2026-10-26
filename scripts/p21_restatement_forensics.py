#!/usr/bin/env python3
"""P2.1-D — restatement forensics over raw_*_payload hash sequences.

Classifies every (asset_id, period-key) fetch history:
  single_fetch          one snapshot only — no version evidence
  duplicate_refetch     >=2 fetches, identical payload_hash — no change
  payload_changed_same_metrics  hash differs but tracked metrics equal
  metrics_changed       tracked metrics differ across fetches
                        → earliest payload = recoverable initial (if kept)
Outputs restatement_forensics.json. READ-ONLY.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402

OUT = Path("docs/research_upgrade/p21")
TRACKED = ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "NETPROFIT",
           "PARENT_NETPROFIT", "TOTAL_ASSETS", "TOTAL_LIABILITIES",
           "NETCASH_OPERATE", "营业总收入", "营业收入", "净利润",
           "归属于母公司所有者的净利润", "TOTAL_PARENT_NETPROFIT"]


def extract_metrics(payload):
    out = {}
    if not isinstance(payload, dict):
        return out
    for row in payload.get("data") or payload.get("result") or []:
        if not isinstance(row, dict):
            continue
        for k in TRACKED:
            if k in row and row[k] is not None:
                out[k] = row[k]
    return out


def period_key(payload, params):
    for src in (params, payload):
        if isinstance(src, dict):
            for k in ("REPORT_DATE", "report_date", "REPORT_PERIOD",
                      "period"):
                if src.get(k):
                    return str(src[k])[:10]
    return "unknown"


def main():
    with connect(SETTINGS.research_service) as conn:
        n_bs = fetch_all(conn,
                         "SELECT count(*) n FROM raw_baostock.finance_payload"
                         )[0]["n"]
        rows = fetch_all(conn, """
          SELECT asset_id, source_endpoint, request_params::text params,
                 payload::text payload, fetched_at::text, payload_hash
          FROM raw_akshare.finance_payload ORDER BY asset_id, fetched_at""")

    groups = defaultdict(list)
    for r in rows:
        p = json.loads(r["payload"]) if r["payload"] else {}
        q = json.loads(r["params"]) if r["params"] else {}
        groups[(r["asset_id"], r["source_endpoint"],
                period_key(p, q))].append({**r, "_m": extract_metrics(p)})

    cls = defaultdict(int)
    changed, recoverable = [], []
    for (asset, ep, pk), fs in groups.items():
        fs.sort(key=lambda f: f["fetched_at"])
        hashes = {f["payload_hash"] for f in fs}
        if len(fs) == 1:
            cls["single_fetch"] += 1
            continue
        if len(hashes) == 1:
            cls["duplicate_refetch"] += 1
            continue
        sigs = [json.dumps(f["_m"], sort_keys=True) for f in fs]
        if len(set(sigs)) == 1:
            cls["payload_changed_same_metrics"] += 1
            continue
        cls["metrics_changed"] += 1
        first_metrics = fs[0]["_m"]
        ok = bool(first_metrics)
        rec = {"asset_id": asset, "endpoint": ep, "period": pk,
               "fetches": len(fs), "first": fs[0]["fetched_at"],
               "last": fs[-1]["fetched_at"],
               "initial_recoverable": ok,
               "hash_seq": [f["payload_hash"][:12] for f in fs]}
        changed.append(rec)
        if ok:
            recoverable.append(rec)

    summary = {
        "raw_akshare_rows": len(rows),
        "raw_baostock_rows": n_bs,
        "baostock_note": "empty table — baostock payloads never "
                         "persisted; baostock-side restatement evidence "
                         "permanently unavailable",
        "version_keys": len(groups),
        "classification": dict(cls),
        "metrics_changed_keys": len(changed),
        "initial_recoverable": len(recoverable),
        "initial_unrecoverable": len(changed) - len(recoverable),
        "changed_events": changed[:200],
    }
    (OUT / "restatement_forensics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "changed_events"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
