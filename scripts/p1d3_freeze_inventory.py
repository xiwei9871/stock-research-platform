"""DATA-R3-P1d.3 — A. migration freeze inventory (read-only).

Captures the pre-migration baseline: table shape, v1 baseline, rule
engine commit, mislabel baselines, unknown/insufficient sets, EOD
writer, consumers, run_id + batch ledger + rollback checkpoints.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.db import connect, fetch_all  # noqa: E402

OUT = Path("docs/research_upgrade/p1d3/final")
T = "p1d3_shadow.asset_status_daily_v2"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()
    with connect(SETTINGS.research_service) as conn:
        inv = {"run_id": f"p1d3-freeze-{sha[:8]}",
               "rule_engine_commit": sha,
               "flags_version": "pit_rules_v1"}
        t = fetch_all(conn, """
            SELECT count(*) AS rows,
                   pg_size_pretty(pg_total_relation_size(
                       'core.asset_status_daily')) AS size,
                   pg_total_relation_size('core.asset_status_daily')
                       AS size_bytes,
                   min(trade_date)::text AS d0,
                   max(trade_date)::text AS d1
            FROM core.asset_status_daily""")[0]
        inv["table"] = {k: (int(v) if k in ("rows", "size_bytes") else v)
                        for k, v in t.items()}
        inv["indexes"] = fetch_all(conn, """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname='core' AND tablename='asset_status_daily'""")
        inv["partitioning"] = fetch_all(conn, """
            SELECT inhparent::regclass::text AS parent FROM pg_inherits
            WHERE inhrelid='core.asset_status_daily'::regclass""")
        inv["v1_null_flags"] = fetch_all(conn, """
            SELECT count(*) FILTER (WHERE is_limit_up IS NULL) AS up_null,
                   count(*) FILTER (WHERE is_limit_down IS NULL) AS dn_null,
                   count(*) FILTER (WHERE is_suspended IS NULL) AS susp_null
            FROM core.asset_status_daily""")[0]
        inv["mislabel_baselines"] = {
            "targeted_scan_unique_keys": 62937,
            "full_census_row_diffs": 84844,
            "full_census_v1_mislabeled_confirmed": 76031,
            "note": ("62,937 = 定向扫描去重键；84,844 = 全表 v1!=v2 行级"
                     "普查；76,031 = 其中 v1 明确错误。UPDATE 行数按普查口径")}
        inv["v2_state_distribution"] = fetch_all(conn, f"""
            SELECT limit_state_v2, count(*) AS n FROM {T}
            GROUP BY 1 ORDER BY 1""")
        inv["rule_unknown_set"] = {
            "rows": fetch_all(conn, f"""
                SELECT count(*) AS n FROM {T} WHERE limit_state_v2=2""")[0],
            "sample": fetch_all(conn, f"""
                SELECT asset_id, trade_date::text, limit_rule_id_v2
                FROM {T} WHERE limit_state_v2=2 LIMIT 20""")}
        inv["data_insufficient_set"] = {
            "rows": fetch_all(conn, f"""
                SELECT count(*) AS n FROM {T} WHERE limit_state_v2=3""")[0],
            "sample": fetch_all(conn, f"""
                SELECT asset_id, trade_date::text, limit_rule_id_v2
                FROM {T} WHERE limit_state_v2=3 LIMIT 20""")}
        inv["batch_ledger"] = fetch_all(conn, """
            SELECT count(*) AS batches,
                   count(*) FILTER (WHERE status='done') AS done
            FROM p1d3_shadow.migration_log""")
    inv["eod_writer"] = {
        "function": "core_data.build_asset_status_daily",
        "v1_logic": "static CASE threshold (ST 4.8 / bj 29.8 / star+chinext 19.8 / else 9.8) — mislabel producer",
        "v2_writer": "emit_v2_flags (guarded pure UPDATE) + build_asset_status_daily(emit_v2_target=...) same-tx dual-write switch, default OFF"}
    inv["consumers"] = [
        "vectorized_topn_backtest.load_vectorized_topn_inputs (3 modes + status_table)",
        "backtest.load_backtest_inputs / load_backtest_bars (retention bars)",
        "dashboard/backtests loader",
        "intraday_risk_control_v2", "intraday_risk_filter_backtest",
        "mid_trend_shadow_backtest", "serenity_tight3b_c2_experiment",
        "dragon_case_library._is_limit_up (rule engine)",
        "market_emotion_state_v1 (stored v1 — NEEDS_REVALIDATION)",
        "lhb_eligibility (rule engine)"]
    p = OUT / "MIGRATION_FREEZE.json"
    p.write_text(json.dumps(inv, indent=2, default=str))
    print(json.dumps(inv, indent=2, default=str)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
