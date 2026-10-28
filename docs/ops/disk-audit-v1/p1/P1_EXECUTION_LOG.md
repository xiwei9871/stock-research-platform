# P1 Execution Log — 2026-10-27 ~22:55

Owner approved: item 1 (statcan CSV) + item 2 (Tier-1 caches).

## Executed

| Path | Bytes freed | Gate evidence |
|---|---|---|
| `.../statcan/sc_34100066/34100066.csv` | 9,571,149,733 (8.91 GiB) | 3-gate PASS — sha256 `b53b0404…` byte-equal to retained `sc_34100066.zip`; pipeline reads zip directly; zero open handles |
| `.../GoogleUpdater/crx_cache` (2 blobs) | ~791,674,880 (0.74 GiB) | applied update payloads, regenerable |
| `~/Library/Caches/{pip,pip-tools}` | ~290,455,552 (0.27 GiB) | wheel caches, regenerable |
| `~/Library/Caches/{Homebrew,typescript,com.apple.helpd}` | ~86,000,000 (0.08 GiB) | regenerable caches |

## Deferred (were in approved list but found LIVE at execution)

| Path | ~Size | Blocker | Re-run when |
|---|---|---|---|
| `~/Library/Caches/ms-playwright` | 572 MiB | playwright screenshot job running (pid 42142, northshore market_pulse) | after run finishes |
| `~/.gradle/caches` + `~/.gradle/wrapper` | 911 MiB | 2 GradleDaemon 9.3.1 alive (pids 11100/11932), classpath inside wrapper/dists | after daemons exit / IDE closed |

## Result

- df free: **4.0 GiB → 14 GiB** (+~10.0 GiB reclaimed, matches expected)
- Level: DATA_WRITE_RISK → WARNING band boundary (still <15 CRIT, >8 EMERG)
- stock_research EOD untouched and still running; northshore pipeline
  unaffected (extract reads the retained zip; small-table expanded CSVs
  deliberately kept).
- Verification command if 34100066.csv is ever needed again:
  `cd data/research/macro/raw/statcan && unzip -o sc_34100066.zip -d sc_34100066/`
  (restores byte-identical file, sha256 b53b0404…).

## Round 2 — 2026-10-28 morning (owner: "继续安全清理")

Blockers rechecked: GradleDaemons exited → `.gradle/caches` +
`.gradle/wrapper` (911 MiB) deleted. ms-playwright (572 MiB) deleted after
`lsof +D` confirmed zero open handles — the owning screenshot job
(pid 42142/42144) has been hung ~20h pre-launch and is reported to owner
separately for kill decision.

df free: 25 GiB → **26 GiB**. Cumulative P1 reclaim ≈ **11.5 GiB**.

Still held: claudevm.bundle 12 GiB (VM pid 56459 live, rootfs.img written
09:22 today); devin sessions.db (cli running); ~40-45 GiB
permission-blocked system space pending owner `sudo du`.
