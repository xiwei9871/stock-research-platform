# Research Operating Layer V2 R1 Operator Guide

## Purpose

R1 provides a repository-local, artifact-first operating layer for research design. It separates three boundaries:

- V1 is the frozen Theme Research and Technology Industry Catalog knowledge base. R1 reads it only for local reference resolution and drift detection; it never rewrites, migrates, or backfills V1.
- V2 is the Research Project layer: stable project identities, immutable version snapshots, append-only events, manifests, a rebuildable index, validators, gates, and operator CLI.
- Future Promotion is a separately authorized human-review workflow for promoting mature V2 knowledge. R1 performs no promotion.

The four R1 pilots are `ai_compute_pcb_value_migration`, `humanoid_robot_scale_up_bottlenecks`, `new_energy_storage_route_competition`, and `high_end_medical_device_commercialization`. They are research designs, not completed research reports.

## Artifact Layout

The managed root is `artifacts/research_projects/v2/`:

```text
schema/*.schema.json
projects/<project_slug>/project.json
projects/<project_slug>/versions/v<semantic_version>.json
projects/<project_slug>/events/events.jsonl
projects/<project_slug>/version_manifest.jsonl
index/research_project_index_v2.json
fixtures/valid/*.json
fixtures/invalid/**
```

Schemas define contracts; `projects/` contains the four pilots; fixtures exercise positive and prohibited states. V1 remains under `artifacts/theme_decomposition/` and `artifacts/technology_industry_catalog/v1/` and is outside the V2 managed-write boundary.

## Project Identity

`project.json` is the stable identity record. `project_id` and `project_slug` do not change when a new version is created. `current_version` points to the operator-selected current immutable snapshot; `latest_reviewed_version` and `latest_published_version` are independent nullable pointers and must not be inferred from `current_version`. Each pointer uses the full version ID, for example `research_version:ai_compute_pcb_value_migration:0.1.0`.

## Immutable Versions

Each `versions/vX.Y.Z.json` is a complete snapshot. Policy prohibits any byte edit after its manifest row exists; create a direct child version instead. The loader cryptographically detects changes to canonical JSON content or its declared hash. A formatting-only byte rewrite that preserves the same canonical JSON produces the same hash and therefore is not detectable by this canonical-hash enforcement, but it remains a policy violation. `content_hash` uses `sha256-jcs-v1`: RFC 8785/JCS canonical JSON encoded to SHA-256, with the top-level `content_hash` field excluded from its own hash input. Parentage must be explicit through `parent_version_id`.

## Event Stream

`events/events.jsonl` is append-only project history. Existing event rows are never edited, reordered, or deleted. Events explain project-level changes and triggers; they do not replace immutable version snapshots. Historical events and versions must remain readable even when the project identity pointer advances.

## Version Manifest

`version_manifest.jsonl` is append-only and binds version ID, semantic version, parent, relative path, content hash, and creation time. `rebuild-index` verifies manifested versions, hashes, parentage, safe paths, and schemas; it may append rows for valid unmanifested placeholder versions but never rewrites an existing manifest prefix.

Dry run computes a plan without writes. `--write` uses atomic replacement and a multi-target rollback path. Managed symlinks are rejected before I/O, so writes cannot escape the V2 root. If a write in the transaction fails, attempted targets are restored. A second `--write` over the same state must be byte-idempotent.

## CLI Commands

Run from the repository root. The following examples are complete shell commands:

```bash
CLI="${STOCK_RESEARCH_VENV:-/Users/xiwei/stock_research/.venv}/bin/stock-research"

"$CLI" research-project-v2 list

"$CLI" research-project-v2 show \
  --project ai_compute_pcb_value_migration \
  --version 0.1.0

"$CLI" research-project-v2 validate --all

"$CLI" research-project-v2 summary \
  --project ai_compute_pcb_value_migration \
  --version 0.1.0

"$CLI" research-project-v2 audit-references \
  --project ai_compute_pcb_value_migration \
  --version 0.1.0

# Runnable R1 error-path smoke: the pilots currently contain only v0.1.0.
"$CLI" research-project-v2 diff \
  --project ai_compute_pcb_value_migration \
  --from 0.1.0 \
  --to 0.1.0

"$CLI" research-project-v2 gate \
  --project ai_compute_pcb_value_migration \
  --version 0.1.0 \
  --gate design

# Maintainer dry run, then explicit write.
"$CLI" research-project-v2 rebuild-index
"$CLI" research-project-v2 rebuild-index --write
```

`diff` accepts only a direct parent-child pair. Because every shipped R1 pilot has only `v0.1.0`, the complete command above is deliberately an error-path smoke: it exits 7 with `RESEARCH_PROJECT_DIFF_ANCESTRY_INVALID`. It does not imply that a successful pilot diff exists. Verify the CLI error path and the isolated direct-parent success semantics with:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_cli.py -k diff -q

/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_diff.py::test_diff_reports_metadata_added_claim_and_unchanged_question -q
```

The other command examples in this section are normal success-path smoke commands against the shipped R1 artifacts; the `diff` command is explicitly the exception.

## Exit Codes

| Exit | Meaning |
|---:|---|
| 0 | Success, including a non-applicable later gate for a research-design snapshot |
| 2 | CLI argument, schema, or semantic validation error |
| 3 | Reference audit failure or reference-domain error |
| 4 | Applicable gate failed |
| 5 | Immutability, hash, unsafe-path, or manifest integrity violation |
| 6 | Project or version not found |
| 7 | Invalid version diff or ancestry |
| 10 | Unexpected runtime or transaction error |

## Research Design Gate

The R1 Design Gate contains 12 structural checks: primary question; included scope; excluded scope; complete router decision; acyclic and valid question tree; evidence requirement coverage for required questions; counter/alternative coverage for critical claims; validation metric plan; invalidation condition plan; auditable references; complete provenance; and absence of premature evidence, conclusions, company capture assessments, or investment judgments.

A pass means only that the research design is structurally ready for later work. It does not mean evidence readiness, publication readiness, a supported claim, a company conclusion, or an investment conclusion. Evidence and Publication gates are later-phase contracts and are `not_applicable` to R1 research-design snapshots.

## Reference Drift

R1 locally resolves `theme_research_v1` and `industry_catalog_v1` references against read-only V1 artifacts. Audit issues are reported without rewriting either the V2 snapshot or V1. Per-reference precedence is: `duplicate`; `unresolvable` namespace/source-content/resolver error; `missing`; `type_mismatch`; `version_mismatch`; `deprecated`; then `hash_mismatch`. A clean reference increments `resolved`.

The audit statuses are therefore `duplicate`, `unresolvable`, `missing`, `type_mismatch`, `version_mismatch`, `deprecated`, and `hash_mismatch`; the command-level result is `pass` only when no issue exists. Hash mismatches report `sha256-jcs-v1` and the selected hash scope. V1 resolver indexes are process-local read caches only: they provide deterministic reads and never become a write-back cache.

## Adding A Design Project

Use this checklist in order:

1. Create `projects/<slug>/project.json` with stable identity and pointers.
2. Create `versions/vX.Y.Z.json` as a research-design placeholder with `content_hash` set to 64 zeroes or its correct calculated hash.
3. Do not create or hand-edit a manifest row for the placeholder.
4. Run `rebuild-index` without `--write` and inspect the plan.
5. Run `rebuild-index --write` to hash the placeholder, append its manifest row, and rebuild the index transactionally.
6. Run `validate --project <slug> --version <version>`.
7. Run `audit-references --project <slug> --version <version>`.
8. Run `gate --project <slug> --version <version> --gate design` with the explicit version.
9. Run `rebuild-index --write` a second time and confirm there is no artifact diff.

At design stage, do not add supported claims, evidence assessments, company capture conclusions, published conclusions, investment judgments, or buy/sell recommendations. Record hypotheses, counterclaims, evidence requirements, planned metrics, and falsification conditions only.

## R1 Non-goals

R1 does not implement a database, API route, Dashboard/UI, evidence collection, Evidence Assessment workflow, Publication Gate, automatic promotion, company-value-capture conclusion, or downstream strategy integration. It does not claim that causal diagrams are evidence-backed; they are a design model for later validation.

## Production Migration Prohibition

No production migration was created or executed in R1. No database schema, migration file, production table, or API route is part of this delivery. Any artifact-to-database mapping is Future-phase design only; production migration requires a new explicit authorization after the artifact model and evidence workflow are stable.

### Scope Attribution

R1 attribution must never use a broad range such as `5548068..HEAD`, because unrelated V1 user commits were interleaved during implementation. The scope guard contains the 26 approved full commit SHAs and directly runs `git show --pretty= --name-only <sha>` for each one. It asserts the sorted unique union has exactly 58 paths, contains required package, schema, pilot, index, documentation, and test paths, and stays inside a precise allowlist. CI therefore needs complete commit history; for GitHub Actions use `fetch-depth: 0`.

`/private/tmp/research_project_v2_changed_files.txt` is optional operator evidence, not a test prerequisite. When present, its contents must exactly equal the computed sorted union; a missing file is accepted, while a stale, truncated, or forged file fails. To run the hermetic check:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_research_project_v2_scope_guard.py -q
```

### Verification Evidence

Verification performed on 2026-07-17 in the R1 integration worktree produced these actual results before final documentation commit:

- Scope guard intentional Red: `1 failed, 1 passed`; real 24-commit union plus Task10 paths: 58 files and `2 passed`.
- `pytest tests/test_research_project_v2_*.py -q`: `230 passed, 4 warnings`.
- Selected V1 regression (`test_theme_decomposition.py`, `test_theme_company_mapping.py`, `test_technology_industry_catalog.py`, `test_dashboard_theme_research.py`): `373 passed, 4 warnings`.
- Actual CLI `list`, AI `show 0.1.0`, `validate --all`, AI `summary`, AI reference audit, explicit AI Design Gate, rebuild dry run, and two rebuild writes: exit 0. The list contained four projects; validate covered four versions; audit resolved 2/2; all 12 Design checks passed; the second write left no V2 artifact diff.
- Focused diff success and invalid exits 2, 3, 4, 5, and 7 (also covering not-found 6 and runtime 10 in the combined node): `6 passed, 2 warnings`.
- Python compile succeeded; JSON parsing covered 25 `.json` and 9 `.jsonl` artifacts; `git diff --check` and the independent forbidden-path scan succeeded.

Warnings were non-blocking existing deprecations, principally `jsonschema.RefResolver` and Python 3.14 `py_mini_racer` structure-layout warnings. Final post-commit scope and V2 test evidence is recorded in the Task10 handoff because the Task10 SHA does not exist until after this document is committed.
