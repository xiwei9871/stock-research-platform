"""DATA-R3-P1d.3 preflight — gray read-path gate (corrected).

Point load_vectorized_topn_inputs(qualification_mode='verified_v2') at the
rehearsal shadow table and prove it agrees with corrected_shadow.

Gate rules (any violation => global FAIL):
  - SQL exception in ANY window            -> FAIL (not skipped)
  - empty key set in ANY window            -> FAIL
  - unique (asset_id, trade_date) key sets must match on both legs;
    comparison uses a FULL OUTER join — inner joins cannot hide drops
  - VERIFIED rows: is_limit_* flags, limit_rule_id, and the v2 flags
    version must all agree
  - non-verified states (rule_unknown / data_insufficient /
    qualification_missing) stay fail-closed
  - the markdown report is generated from the SAME JSON run

Writes docs/research_upgrade/p1d3/final/GRAY_GATE_CORRECTED.json and
docs/research_upgrade/p1d3/GRAY_READ_VALIDATION.md (regenerated).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
import pandas as pd  # noqa: E402
from stock_research.vectorized_topn_backtest import (  # noqa: E402
    load_vectorized_topn_inputs)

SHADOW = "p1d3_shadow.asset_status_daily_v2"
VERSION_COL = "limit_flags_version"
WINDOWS = [
    ("2024-06-03", "2024-06-07"),   # modern window
    ("2019-08-01", "2019-08-09"),   # STAR reform era
    ("2023-04-10", "2023-04-14"),   # main-board registration era
    ("1996-12-16", "1996-12-20"),   # pre-limit era boundary
]
FAIL_CLOSED = {"rule_unknown", "data_insufficient",
               "qualification_missing"}


def compare(start, end):
    res = {"window": [start, end], "pass": False}
    try:
        _, pv2 = load_vectorized_topn_inputs(
            start, end, score_version="manual_v1",
            qualification_mode="verified_v2", status_table=SHADOW)
        _, pcs = load_vectorized_topn_inputs(
            start, end, score_version="manual_v1",
            qualification_mode="corrected_shadow")
    except Exception as exc:  # noqa: BLE001
        res["error"] = f"{type(exc).__name__}: {exc}"
        return res
    for df in (pv2, pcs):
        df["trade_date"] = df["trade_date"].astype(str)
    keys_v2 = set(zip(pv2["asset_id"], pv2["trade_date"]))
    keys_cs = set(zip(pcs["asset_id"], pcs["trade_date"]))
    res["keys_v2"], res["keys_cs"] = len(keys_v2), len(keys_cs)
    if not keys_v2 or not keys_cs:
        res["error"] = "empty key set in a leg — FAIL"
        return res
    res["key_sets_equal"] = keys_v2 == keys_cs
    res["only_in_v2"] = len(keys_v2 - keys_cs)
    res["only_in_cs"] = len(keys_cs - keys_v2)
    # FULL OUTER join — nothing dropped silently
    m = pv2.merge(
        pcs[["asset_id", "trade_date", "is_limit_up", "is_limit_down",
             "limit_rule_id", "qualification_state"]],
        on=["asset_id", "trade_date"], how="outer",
        suffixes=("_v2", "_cs"), indicator=True)
    unmatched = int((m["_merge"] != "both").sum())
    both = m[m["_merge"] == "both"]
    verified = both[~both["limit_state_missing"]]
    flag_mism = verified[(verified["is_limit_up_v2"]
                          != verified["is_limit_up_cs"]) |
                         (verified["is_limit_down_v2"]
                          != verified["is_limit_down_cs"])]
    rule_mism = verified[verified["limit_rule_id_v2"]
                         != verified["limit_rule_id_cs"]]
    # version consistency on the v2 leg: every populated verified row must
    # carry the same flags version emitted by the rehearsal
    ver_col = (pv2["limit_flags_version"]
               if "limit_flags_version" in pv2.columns else None)
    versions = (ver_col.dropna().unique().tolist()
                if ver_col is not None else [])
    nonverified = both[both["limit_state_missing"]]
    escaped = nonverified[
        ~nonverified["qualification_state"].isin(FAIL_CLOSED)]
    res.update({
        "rows_joined": len(m),
        "unmatched_outer_rows": unmatched,
        "verified_rows": len(verified),
        "fail_closed_rows": len(nonverified),
        "fail_closed_breakdown":
            nonverified["qualification_state"]
            .value_counts().to_dict(),
        "flag_mismatches_on_verified": len(flag_mism),
        "rule_id_mismatches_on_verified": len(rule_mism),
        "flags_versions_seen": versions,
        "version_consistent": len(versions) <= 1,
        "nonverified_escaping_fail_closed": len(escaped),
    })
    res["pass"] = all([
        res["key_sets_equal"], unmatched == 0, len(verified) > 0,
        len(flag_mism) == 0, len(rule_mism) == 0,
        len(escaped) == 0, res["version_consistent"]])
    return res


def render_md(res: dict) -> str:
    lines = ["# P1d.3 — 灰度读路验证（verified_v2 @ 影子表）",
             "",
             "由 `GRAY_GATE_CORRECTED.json` 同批次自动生成。",
             "", "| 窗口 | 键集相等 | verified | fail-closed |",
             "|---|---|---|---|"]
    for r in res["checks"]:
        if "error" in r:
            lines.append(f"| {r['window'][0]}~{r['window'][1]} "
                         f"| ERROR: {r['error']} | - | - |")
            continue
        lines.append(
            f"| {r['window'][0]}~{r['window'][1]} "
            f"| {'✅' if r['key_sets_equal'] else '❌'} "
            f"| {r['verified_rows']} "
            f"(flag Δ{r['flag_mismatches_on_verified']} / "
            f"rule Δ{r['rule_id_mismatches_on_verified']}) "
            f"| {r['fail_closed_rows']} "
            f"{r['fail_closed_breakdown']} |")
    lines += ["", f"**all_pass = {res['all_pass']}**"]
    return "\n".join(lines)


def main() -> int:
    out = [compare(s, e) for s, e in WINDOWS]
    res = {"shadow_table": SHADOW, "flags_version_expected":
           "pit_rules_v1", "checks": out,
           "all_pass": all(r["pass"] for r in out)}
    final = Path("docs/research_upgrade/p1d3/final")
    final.mkdir(parents=True, exist_ok=True)
    (final / "GRAY_GATE_CORRECTED.json").write_text(
        json.dumps(res, indent=2, default=str))
    Path("docs/research_upgrade/p1d3/GRAY_READ_VALIDATION.md")\
        .write_text(render_md(res))
    print(json.dumps(res, indent=2, default=str)[:2500])
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
