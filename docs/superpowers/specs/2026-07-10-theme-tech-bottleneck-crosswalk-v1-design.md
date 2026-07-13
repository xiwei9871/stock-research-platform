# Theme To Tech Bottleneck Crosswalk v1 Design

Updated: 2026-07-10

## Purpose

Phase 5 connects the evidence-backed Phase 4 company mappings to the existing 378-company tech-bottleneck review universe without changing either system's admission, review, evidence, or writeback behavior.

Target relationship:

```text
theme -> theme node -> bottleneck problem -> company -> evidence
                                      |
                                      +-> existing tech-bottleneck review row
```

This is research context, not a recommendation, signal, quality-pool admission, or reviewer decision.

## Chosen Approach

Use an independent, versioned JSON crosswalk artifact plus an offline standard-library loader.

Rejected alternatives:

1. Writing crosswalk rows to the database would cross the current artifact-first boundary and require migrations, write permissions, and rollback policy before the schema is stable.
2. Adding theme columns directly to the 378-row frontend CSV would mix generated research context into the authoritative review-universe dataset and make reversibility harder to prove.
3. An independent artifact preserves both upstream datasets, can be deleted without data loss, and can validate its references against current files on every load.

## Authoritative Inputs

The existing review universe remains authoritative at:

```text
outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/
  tech_bottleneck_review_universe_frontend_dataset.csv
  tech_bottleneck_review_universe_frontend_evidence_index.csv
  tech_bottleneck_review_universe_frontend_source_index.csv
```

Phase 4 company mappings remain authoritative under:

```text
artifacts/theme_decomposition/company_mappings/
```

The P5 loader reads these files. It never rewrites them.

## Crosswalk Artifact

Location:

```text
artifacts/theme_decomposition/tech_bottleneck_crosswalks/
```

Each artifact contains:

- `artifact_version`;
- `theme_id`;
- `universe_snapshot` with paths, SHA-256 digests, and expected universe count;
- `crosswalks` for companies present in the existing universe;
- `coverage_gaps` for Phase 4 mappings whose companies are absent;
- explicit read-only guardrails.

A crosswalk record contains the roadmap fields:

```text
theme_node_id
company_code
existing_review_universe_id
existing_evidence_ids
new_theme_evidence_ids
confidence
review_status
```

It also records `crosswalk_id`, `theme_id`, `company_name`, `mapping_id`, `relationship_type`, and `notes` for traceability.

## Stable IDs

The existing CSV has no row IDs. P5 derives deterministic IDs without modifying it:

```text
tech_bottleneck_review_universe_v1:{stock_code}
tech_bottleneck_evidence_v1:{stock_code}:{sha256(row identity)[:24]}
tech_bottleneck_source_v1:{stock_code}:{sha256(row identity)[:24]}
```

Evidence identity uses stock code, repository-relative source reference, page, claim type, and evidence text. Source identity uses stock code, repository-relative source reference, source type, and source title. The 96-bit digest ignores the local checkout prefix and CSV row order. Duplicate IDs and ambiguous company/source-reference keys are rejected.

## Validation Gates

The loader rejects a package when:

- an input path differs from the three authoritative review-universe paths, escapes the repository, or is missing;
- a stored snapshot digest does not match the current authoritative file;
- an authoritative CSV is missing required columns or its evidence/source stock coverage differs from the universe;
- the universe does not contain exactly the declared number of unique stocks;
- a crosswalk references a missing P4 mapping, theme node, company, existing evidence row, or new evidence item;
- a selected existing evidence row belongs to another company;
- a reviewed crosswalk has confidence below `0.7` or has no evidence on either side;
- a P4 mapping is neither linked nor represented by one coverage gap;
- a coverage gap claims a company is absent when it is actually present;
- any record attempts to set `used_for_signal`, `used_for_admission`, `auto_added_to_quality_pool`, or reviewer-decision fields.
- any artifact record contains unknown fields that could imitate existing review or admission state.

## Initial AI Power Coverage

The current 378-company universe contains:

- Envicool `002837` -> `liquid_cooling`;
- Kehua Data `002335` -> `ups`.

It does not contain:

- Oulutong `300870` -> `server_power_supply`;
- Zhongheng Electric `002364` -> `hvdc_power`.

The first artifact therefore has two reviewed crosswalks and two explicit coverage gaps. Absence from the existing universe is not treated as a rejection or admission decision.

## Read Model And CLI

The loader exposes normalized package data plus detailed lookups by theme and company. Detailed rows resolve:

- the Phase 4 mapping and its new evidence;
- the unchanged existing review-universe row, nested separately from `crosswalk_review_status`;
- selected existing evidence rows and their source records;
- any optional current manual-review overlay as separate read-only context.

CLI commands:

```text
validate
summary
show-theme --theme-id ...
show-company --company-code ...
coverage-gaps
```

## Boundaries

- no DB writes;
- no dashboard changes in P5 v1;
- no update to the 378-row CSV, evidence index, source index, or manual decision overlay;
- no quality-pool admission, watchlist action, signal, score, or recommendation;
- no automatic addition of the two missing companies to the review universe;
- Phase 6 scoring and Phase 7 dashboard remain separate.

## Acceptance

P5 is complete when the artifact validates against the current 378-company snapshot, all four P4 mappings are accounted for as links or gaps, detailed CLI output resolves both evidence systems, relevant P1-P5 tests pass, input hashes remain unchanged, and independent review finds no unresolved high- or medium-risk issue.
