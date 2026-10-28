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

## Correction 2 — the "unaccounted" gap resolved itself (2026-10-28)

Fresh `du -xhd 1 /System/Volumes/Data` (user scope): **152 GiB readable**
vs df used 160 GiB → **true gap ≈ 8 GiB**, not 40-45.

Root causes of the earlier overestimate:
1. Deleted-but-open blocks: df counts them, du cannot see them. EOD/repair
   temp files, Claude VM intermediate writes, and crash remnants were held
   by live processes. When those processes exited (EOD finished, VM
   SIGTERMed), the space returned — explaining the 4.0→14→25→39 GiB free
   recovery pattern without corresponding du-visible deletions.
2. The earlier "~116 GiB readable" was itself an undercount assembled from
   several partial du runs each skipping different permission-denied
   subtrees.

Remaining ~8 GiB sits in root-owned subtrees (`.Spotlight-V100`,
`.DocumentRevisions-V100`, `/private/var/db`, `/Library` system subtrees).
Owner to run the sudo du commands for the exact split. No bulk deletion
of system-managed paths will be proposed regardless of size — per owner
policy 2026-10-28: locate specific reclaimable objects only.
