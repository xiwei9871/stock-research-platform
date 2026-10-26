# Storage Governance V1 — Operations Log

## 2026-10-26 P3: disable completed watchdogs

| Action | Detail |
|---|---|
| `launchctl bootout gui/501/com.stockresearch.r2-minute-rebuild-watchdog` | rc=0; verified absent from `launchctl list` |
| `launchctl bootout gui/501/com.stockresearch.factor-gate-backfill-watchdog` | rc=0; verified absent |
| plists moved | `~/Library/LaunchAgents/*.plist` → `~/Library/LaunchAgents/.disabled/` (won't auto-load at login) |
| plists backed up | `docs/ops/storage-governance-v1/com.stockresearch.*.plist` |
| Evidence for completion | r2: `minute phase done` in run log; factor-gate: sentinel `wave5-factor-gate-watchdog.completed` (2026-05-22) current |
| **Recovery** | `cp .disabled/<name>.plist ../ && launchctl bootstrap gui/501 <plist>` — restores schedule. Scripts/data untouched: `scripts/r2_minute_rebuild_watchdog.sh`, `scripts/run_wave5_factor_gate_watchdog_host.sh` |

## 2026-10-26 P1: compression + dedup — EXECUTED

| Action | Result |
|---|---|
| gzip -9 ×9 files (5 dragon CSV + 3 research CSV + r2 features ledger) | all verified: decompressed sha256 == original; atomic tmp->rename; orig removed only after verify |
| net saved (compression) | **3,379,458,412 bytes ≈ 3.15 GiB** |
| outputs/research total | 7.06 GB -> **3.5 GB** |
| PDF dedup via hardlink | 5 links (sha256-verified groups), ~70MB reclaimed; all paths remain valid |
| NOT compressed | `r2_downstream_minute_done.json` (470KB) — live input for `src/stock_research/tradeability.py:949` + `scripts/p1d1_audit.py` |
| Manifests | `compression_manifest.csv` (orig/gz sha256 + sizes + recovery cmd), `dedup_manifest.csv` |
| Recovery | per-file `gunzip -k <path>.gz`; hardlinks: `cp canonical linked_path` restores independent copy |

## EOD RCA fix (pending PR merge)

- `src/stock_research/strategy_daily_eod.py` `check_strategy_daily_eod_dependencies` now also fails `common` when `factor.stock_score_daily` (manual_v1) has 0 rows for trade_date — aligns wait-gate with publish base-check. See `EOD_20261023_RCA.md`.
- Tests: `test_..._waits_for_score_rows` regression added; `pytest tests/test_strategy_daily_eod.py` 52 passed; `test_daily_close_pipeline.py` 65 passed.
