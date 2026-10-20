# 02 — V7 Quality-Pool Lineage Reconstruction (M0.6)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.
Workspace: `outputs/research/m0_6_v7_lineage_rebuild_20261020/` (gitignored research artifacts; canonical outputs unchanged after incident restore — see below).

## Verdict: PASS (with one unrecoverable generation gap, documented)

The full V2→V7 chain was re-executed from authoritative inputs in an isolated mirror
workspace. **Every stage output is byte-identical (SHA-256) to the stock-prod artifacts.**
The 281/307/359 test contract describes a different, older generation whose intermediate
inputs are not present in local, archive, or stock-prod copies — the +11-row delta is
unrecoverable and is preserved as historical reference only, per review decision.

## 1. Method

- Inputs pulled from stock-prod (the authoritative copies) into `inputs/` —
  untouched, with original mtimes.
- Stage outputs written only to `stages/` by `rebuild_driver.py`, which monkey-patches
  each generator module's `Path` constants at runtime (no code edits to the modules).
  Priority order on each path lookup: rebuilt `stages/` first, then `inputs/`, so
  downstream stages consume the rebuilt chain while human artifacts (manual decisions,
  approval ledgers) resolve to the authoritative `inputs/` copies.
- Per-stage outputs, row counts, SHA-256: `lineage_manifest.csv`, `stage_comparison.json`.
- Integrity log: `INCIDENT_NOTES.md`.

## 2. Rebuilt chain vs. recovered artifacts vs. test contract

| Stage | Rebuilt rows | = stock-prod (sha) | = canonical local | Contract | Δ |
|---|---|---|---|---|---|
| V2 manifest | 181 | ✓ | ✓ | — | — |
| V3 manifest | 205 | ✓ | ✓ | — | — |
| V4 manifest | 246 | ✓ | ✓ | — | — |
| V5 manifest | 270 | ✓ | ✓ | 281 | −11 |
| V6 proposal | 296 | ✓ | ✓ | 307 | −11 |
| V6 manual approved | 0 | ✓ | ✓ | — | all 26 additions on hold |
| V7 proposal | 348 | ✓ | ✓ | 359 | −11 |
| V7 review packet | 348 | ✓ | ✓ | 359 | −11 |
| V7 ingest ledger | 78 | ✓ | ✓ | — | 52 pending + 26 hold, 0 approved |

Addition arithmetic is consistent within the recovered generation:
V5 = 270 = V4(246) + 24 `latent_standard_core_equivalent` additions;
V6p = 296 = V5 + 26 batch-1 proposals; V7 = 348 = V6 + 52 standard proposals.
Under the lost contract generation the same additions would read
281 = (V4′) + 35, 307 = 281 + 26, 359 = 307 + 52 — i.e. the missing **11 rows enter at or
before V5** via the `tech_bottleneck_latent_manual_review_standard_*` sidecars
(standard equivalence gate / backfill). Current authoritative sidecars contribute only 24
keepers; the 11 additional ones exist in no accessible artifact version.

## 3. Where the −11 lives (evidence)

- `quality_pool_layer_v5_summary.json` (rebuilt = prod): `latent_standard_core_equivalent_added=24`,
  `rescue_core_equivalent_count=38` — the authoritative **38-row** rescue artifact was used
  (local's stale 20-row variant was deliberately NOT used; preserved as lineage divergence
  evidence, not merged).
- Contract-era V5=281 ⇒ its standard-gate/backfill inputs had ~11 more
  `latent_standard_core_equivalent` candidates than the recovered authoritative versions.
  Those sidecar versions were not found locally, in `stock_research_archive/`, or on
  stock-prod. **No rows were fabricated.**
- V4 metadata drift: recovered prod `quality_pool_layer_v4_summary.json` records
  `quality_pool_v3_count=234`; rebuild records 215. The V4 *manifest* is byte-identical
  either way — the count is an informational metric, not membership. Documented as
  internal evidence that prod artifacts themselves span >1 generation.

## 4. Guardrail verification on the rebuilt chain

All stage summaries confirm: `research_only=true`, `used_for_signal_count=0`,
`used_for_admission_count=0`, `auto_added_to_quality_pool_count=0`,
`baseline_admission_changed_count=0`, `formal_strategy_files_modified=false`,
`strategy_file_diff_clean=true`, `lookahead_violation_rows=0`.
V6 manual approval: 0 approved, 26 hold-for-review (the `manual_decisions.csv` filename
quirk is benign — module fallback produced prod-identical output).
V7 ingest: `approved_count=0`, `can_freeze_v7=false`, decision
`..._no_approved_candidates`; freeze pre-check `allowed_base.v5_baseline=300` is the
freeze reference, not the 270 manifest count. **Nothing was promoted; the frozen 148
formal pool is untouched.**

## 5. Known contract failures → proposed disposition

Current focused suite: 425 passed / 5 failed — all five are the count-contract assertions
(281/307/359) in `tests/test_tech_bottleneck_quality_pool_layer_v5.py`,
`_v6_proposal.py`, `_v7_proposal.py`, `_v7_manual_review_packet.py`,
`_v7_manual_approval_ingest.py`. Per review decision these are **not** to be edited to
match present artifacts. Proposal awaiting approval: pin a new test contract to the
verified reproducible lineage (270/296/348/78) with a comment recording the
historical 281/307/359 contract and its unrecoverable provenance gap. New contract takes
effect only after approval.

## 6. Incidents

See `INCIDENT_NOTES.md`. Two path-isolation escapes (a driver `setattr` bug; a same-day
earlier probe) briefly wrote regenerated content into canonical V4/V7 dirs. V4/V6-outputs
were byte-identical to prod; V7 local had a 1-stock membership drift (603722 vs 300687).
All canonical dirs were restored byte-identical to stock-prod and re-verified by sha256.
The driver is fixed (OUTPUT_DIR setattr applied; packet_dir passed explicitly) — a
full clean rerun produced `stage_comparison.json` with `rebuilt_eq_prod=true` for all 9 stages.

## 7. Remaining blocker

The −11 generation gap is **unrecoverable** with available artifacts: no accessible copy
of the standard-equivalence/backfill inputs (or an earlier V2-rescue generation) that would
produce 281/307/359 exists. Options for the record: (a) accept the verified 270/296/348
lineage as the new contract (recommended — fully reproducible byte-for-byte), or
(b) regenerate the standard-equivalence gate from its own upstream if that upstream still
exists. No third option identified.
