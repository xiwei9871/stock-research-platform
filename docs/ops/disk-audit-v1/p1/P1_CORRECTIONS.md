# P1-E — Corrections to the V1 audit attribution

## Error 1: unit conflation (GB vs GiB)

The V1 report compared `diskutil` **decimal GB** against `du`/`df` **binary
GiB** and manufactured a "78 GB unexplained" gap:

- `diskutil apfs list` → Data "Capacity Consumed: **193.8 GB**" (decimal)
- 193.8 GB ÷ 1.073741824 = **180.5 GiB**
- `df -h` → **181 Gi used** — the SAME figure in binary units. df and
  diskutil never disagreed; the report did.

## Error 2: mixed scan times

The "~116 GiB readable" total came from the morning scan and was then
subtracted from the *evening* consumption figure — after +22 GiB of
confirmed new growth had already landed.

## Corrected accounting

| Item | Value | Scan time |
|---|---|---|
| df used (Data volume) | 181 GiB | 22:35 |
| df free | **6.1 GiB — EMERGENCY** | 22:35 |
| Readable du, morning snapshot | ~116 GiB | ~14:00 |
| Confirmed new growth since (statcan 10.2 + claudevm 12.0 + misc ~1.5) | ~23.7 GiB | 14:45-22:30 |
| ⇒ Readable-accounted estimate now | ~139-140 GiB | mixed |
| ⇒ **Unaccounted, permission-blocked** | **~40-45 GiB** | estimate |

So the true unresolved mass is ~40-45 GiB (not ~70-78), sitting in
root-owned subtrees (`.Spotlight-V100`, `/private/var/db/*`, `/Library`
system subtrees — see `system_permission_gaps.md`). Spotlight rebuild
remains a *suspect* only — still UNKNOWN until the owner runs the sudo du
command. `.fseventsd` (884 KiB) and snapshots (none) are confirmed ruled
out.

## Tier-1 reclaim — deduplicated recount

| Cache | MiB |
|---|---|
| GoogleUpdater crx_cache | 755 |
| .gradle/caches + wrapper | 911 |
| ms-playwright | 572 |
| pip + pip-tools | 277 |
| Homebrew + typescript + helpd + misc | ~120 |
| **Tier-1 total** | **≈ 2,635 MiB ≈ 2.6 GiB** |

Plus Tier-2 now-verified: `sc_34100066/34100066.csv` **8.91 GiB** (gates
PASS — awaiting approval). Combined approved-now reclaim ≈ **11.5 GiB**,
which would take free space from 6.1 → ~17.6 GiB (WARNING band).
