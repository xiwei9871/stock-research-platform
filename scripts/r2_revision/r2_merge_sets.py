"""Merge baostock-window outputs into the canonical r2_disjoint_sets.json.

Inputs:
  r2_disjoint_sets.json      — canonical sets the driver consumes
  r2_classification_sets.json — fresh statuses from reclassification
  r2_review_verdicts.jsonl   — 40-sample verdicts (AUTO_RELEASABLE/KEEP_REVIEW)

Merge rules:
  - reclassified assets adopt their NEW status (ERROR -> CONFIRMED_DIRTY etc.)
  - AUTO_RELEASABLE -> CONFIRMED_DIRTY (released into repair queue)
  - KEEP_REVIEW / ERROR-verdict stays NEEDS_REVIEW / ERROR
  - statuses missing from the new classification keep their previous set
  - a merge report is written; the canonical file is replaced atomically
    only after pairwise-disjoint and cardinality checks pass.
"""
from __future__ import annotations

import json
import os
import sys

BASE = "outputs/research/data01r1_finance_q2_20261020"
DISJOINT = f"{BASE}/r2_disjoint_sets.json"
FRESH = f"{BASE}/r2_classification_sets.json"
VERDICTS = f"{BASE}/r2_review_verdicts.jsonl"
REPORT = f"{BASE}/r2_merge_report.json"

STATUS_KEYS = ("CONFIRMED_DIRTY", "NEEDS_REVIEW", "ERROR",
               "ALREADY_CORRECT", "REPAIRED")


def main() -> None:
    sets = {k: set(v) for k, v in json.load(open(DISJOINT)).items()
            if k in STATUS_KEYS}
    fresh = json.load(open(FRESH)) if os.path.exists(FRESH) else {}
    verdicts = {}
    if os.path.exists(VERDICTS):
        for line in open(VERDICTS):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            verdicts[r["asset_id"]] = r["verdict"]

    before = {k: len(v) for k, v in sets.items()}
    universe_before = set().union(*sets.values()) if sets else set()
    moves = []

    def move(asset: str, new_status: str, reason: str) -> None:
        if new_status not in STATUS_KEYS:
            new_status = "NEEDS_REVIEW"
        for k in STATUS_KEYS:
            if asset in sets[k]:
                if k != new_status:
                    sets[k].discard(asset)
                    sets[new_status].add(asset)
                    moves.append({"asset": asset, "from": k,
                                  "to": new_status, "reason": reason})
                return
        sets[new_status].add(asset)
        moves.append({"asset": asset, "from": None,
                      "to": new_status, "reason": reason})

    # 1) reclassification overrides ONLY assets that were actually
    #    re-attempted (previously ERROR or brand-new); unchanged assets
    #    keep their post-fix status — stale CSV statuses must not revert
    #    corrected classifications
    for status, assets in fresh.items():
        for a in assets:
            prior = next((k for k in STATUS_KEYS if a in sets[k]), None)
            if prior == "ERROR" or prior is None:
                move(a, status, "reclassified")

    # 2) REVIEW verdicts: releasable -> dirty queue; others stay review
    for a, v in verdicts.items():
        if v == "AUTO_RELEASABLE":
            move(a, "CONFIRMED_DIRTY", "review_verified")
        elif v == "KEEP_REVIEW":
            move(a, "NEEDS_REVIEW", "review_hold")
        # ERROR verdict -> leave in place, flag in report

    # pairwise-disjoint + conservation checks
    seen = set()
    for k in STATUS_KEYS:
        overlap = seen & sets[k]
        if overlap:
            sys.exit(f"FATAL: sets overlap {k}: {sorted(overlap)[:5]}")
        seen |= sets[k]
    # universe conservation: no asset lost, none invented
    universe_after = set().union(*sets.values()) if sets else set()
    if universe_after != universe_before:
        lost = universe_before - universe_after
        gained = universe_after - universe_before
        sys.exit(f"FATAL: universe changed lost={sorted(lost)[:5]} "
                 f"gained={sorted(gained)[:5]}")
    after = {k: len(v) for k, v in sets.items()}

    report = {"before": before, "after": after,
              "union_total": len(seen), "moves": len(moves),
              "moves_detail": moves,
              "verdict_summary": {
                  "AUTO_RELEASABLE": sum(1 for v in verdicts.values()
                                         if v == "AUTO_RELEASABLE"),
                  "KEEP_REVIEW": sum(1 for v in verdicts.values()
                                     if v == "KEEP_REVIEW"),
                  "ERROR": sum(1 for v in verdicts.values()
                               if v == "ERROR")}}
    tmp = DISJOINT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({k: sorted(v) for k, v in sets.items()}, f, indent=1)
    os.replace(tmp, DISJOINT)  # atomic
    with open(REPORT, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("disjoint sets merged atomically:")
    for k in STATUS_KEYS:
        print(f"  {k}: {before.get(k,0)} -> {after[k]}")
    print(f"  union={len(seen)} moves={len(moves)}")


if __name__ == "__main__":
    main()
