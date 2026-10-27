# P1 — StatCan Expanded-CSV Three-Gate Verification

Date: 2026-10-27. Authorizes VALIDATION ONLY — no deletion executed.

## ZIP ↔ CSV mapping (authoritative)

| ZIP (kept) | member | expanded on disk | zip size | expanded size |
|---|---|---|---|---|
| `sc_14100378.zip` | `14100378.csv` | `sc_14100378/14100378.csv` | 27 MiB | 396,650,981 B |
| `sc_17100148.zip` | `17100148.csv` | `sc_17100148/17100148.csv` | 22 MiB | 277,885,640 B |
| `sc_18100004.zip` | `18100004.csv` | `sc_18100004/18100004.csv` | 15 MiB | 161,295,102 B |
| `sc_34100066.zip` | `34100066.csv` | `sc_34100066/34100066.csv` | 372 MiB | **9,571,149,733 B** |

Each zip also contains `NNNNNNNN_MetaData.csv` (kept on disk too, ~KB).

## Gate 1 — Source recoverable: PASS

- All four official zips are retained in `raw/statcan/` (they are the
  downloaded artifacts — `fetch_statcan()` skips re-download when present).
- Official source documented in `scripts/macro_v1_acquire.py`:
  `https://www150.statcan.gc.ca/n1/en/tbl/csv/{pid}-eng.zip`
- Recovery of any expanded file:
  `cd data/research/macro/raw/statcan && unzip -o sc_<pid>.zip -d sc_<pid>/`
  (or re-run `.venv/bin/python scripts/macro_v1_acquire.py --only statcan`).

## Gate 2 — Content verified: PASS (4/4)

`verify_statcan_stream.py` streamed each zip member (no disk copy) and
compared SHA-256 + CRC-32 + byte count against the on-disk CSV:

- `34100066.csv`: zip-declared CRC32 `8bdc04d1`, SHA-256
  `b53b04043b3c1c9c12d2cd8b72551fcc893031dbef5f29ee62f9a9a5bc313535` —
  identical on both sides. The other three PASS identically.
- Full JSON: `p1/statcan_verification_evidence.json`.
- Note: filename/size match was NOT accepted as proof; bytes were hashed.

## Gate 3 — Downstream dependencies: PASS (split verdict)

- `extract_statcan()` in `macro_v1_acquire.py`:
  - **34100066 → reads the ZIP directly** (zipfile stream). The expanded
    `sc_34100066/34100066.csv` has ZERO code references — nothing reads it.
  - `sc_18100004`, `sc_14100378`, `sc_17100148` → read the EXPANDED csv
    (each guarded by `src.exists()`; absence silently skips that extract).
- `macro_v1_build_master.py` consumes only the small top-level extracts
  (`cpi_vancouver.csv`, `lfs_vancouver.csv`, `pop_vancouver.csv`,
  `permits_vancouver.csv`) — all already generated (10:35-10:44).
- `macro/master/` + `macro/out/` populated (11:28-17:20).
- `lsof` on all statcan paths: no open handles.

## Execution candidates (awaiting owner approval — NOT executed)

| Candidate | Size | Verdict |
|---|---|---|
| `sc_34100066/34100066.csv` | **8.91 GiB** | EXECUTE-SAFE: all 3 gates PASS, nothing reads it |
| `sc_14100378/14100378.csv` | 0.37 GiB | REVIEW: verified but read by refresh pipeline; re-expandable from zip |
| `sc_17100148/17100148.csv` | 0.26 GiB | REVIEW: same |
| `sc_18100004/18100004.csv` | 0.15 GiB | REVIEW: same |
| MetaData + zips | ~0.4 GiB | KEEP (they are the source/archive) |

Recommendation: delete only the 8.91 GiB expanded file now; keep the three
small expanded CSVs (~0.78 GiB) to avoid refresh-time staleness edge cases.
Net reclaim ≈ **8.9 GiB**, recovery `unzip -o sc_34100066.zip -d sc_34100066/`
(≈30 s).
