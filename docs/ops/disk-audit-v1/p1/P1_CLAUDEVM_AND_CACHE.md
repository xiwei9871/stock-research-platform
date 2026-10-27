# P1-B — Claude VM status / P1-C — cache recount / P1-D — EOD gate

## B. claudevm.bundle — LIVE, DO NOT TOUCH (observed only)

- Holder: `com.apple.Virtualization.VirtualMachine` XPC pid **56459**,
  elapsed 07:50:45, parent launchd — the VM is running.
- Open RW handles: `rootfs.img` (fd 8u, 10.0 GiB), `sessiondata.img`
  (fd 13u, 559 MiB). rootfs.img last written 22:22 today.
- Persistent state: `sessiondata.img` + `machineIdentifier` +
  `.cowork-adopted` marker → bundle carries this cowork session's mutated
  filesystem. NOT purely regenerable — the `.zst` origins are only the
  1.2 GiB boot image; the 10 GiB rootfs is the live disk.
- Cleanup flow once Claude app is fully quit (owner-triggered, not executed):
  1. Quit Claude.app; confirm `pgrep -fl claudevm` and lsof on the bundle
     return empty.
  2. Optionally export VM work products first if the session matters.
  3. Delete `~/Library/Application Support/Claude-3p/vm_bundles/` — app
     re-creates on next VM use. Reclaim ~12 GiB.

## C. Cache recount (deduplicated, concrete objects only)

| Object | Size | Verdict |
|---|---|---|
| `~/Library/Application Support/Google/GoogleUpdater/crx_cache` | 755 MiB | SAFE (update payloads; re-downloads) |
| `~/.gradle/caches` + `~/.gradle/wrapper` | 911 MiB | SAFE (rebuilds); `.gradle/jdks` 525 MiB optional-review |
| `~/Library/Caches/ms-playwright` | 572 MiB | SAFE (auto re-download on next run) |
| `~/Library/Caches/pip` + `pip-tools` | 277 MiB | SAFE |
| `~/Library/Caches/Homebrew` + `typescript` + `com.apple.helpd` + misc | ~120 MiB | SAFE |
| rest of `~/Library/Caches` (app-state, uuremote, etc.) | — | EXCLUDE (in use / app state) |

Deduped Tier-1 total ≈ **2.6 GiB** (vs earlier loose 2.4 GiB — recount adds
gradle wrapper + pip-tools, subtracts app-state exclusions).

## D. EOD safety gate — EMERGENCY, no interference

- Free space: **6.1 GiB < 8 GiB → EMERGENCY** (not yet <5 GiB
  DATA_WRITE_RISK; ~1.1 GiB margin).
- EOD is RUNNING: cron pid 4553 (`run_strategy_daily_eod_cron.sh`),
  strategy CLI pids 18822/19436, `eod_auto_repair` pid 13470,
  `platform-ready-check` pid 13426 — all for trade-date 2026-10-27.
- Action taken: none. No stock_research paths touched; no process
  signalled; disk audit is read-only and I/O-light.
- Risk note: tonight's EOD writes `outputs/research/strategy_daily_eod/`
  plus sync payload — a few hundred MiB typical; 6.1 GiB free is workable
  but the margin is thin. The 8.9 GiB statcan reclaim is the single
  highest-leverage safe action once approved.
