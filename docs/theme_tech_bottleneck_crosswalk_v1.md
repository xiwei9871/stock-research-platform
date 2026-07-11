# Theme To Tech Bottleneck Crosswalk v1

Updated: 2026-07-10

## Purpose

Phase 5 connects evidence-backed theme-node company mappings to the existing tech-bottleneck review universe:

```text
theme -> node -> company -> new theme evidence
                    |
                    +-> existing review-universe row -> existing evidence
```

The crosswalk adds research context only. It does not change admission, manual review, quality-pool membership, signals, watchlists, or recommendations.

## Inputs

The loader reads the existing 378-company dataset and its evidence/source indexes from:

```text
outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/
```

It reads Phase 4 mappings from:

```text
artifacts/theme_decomposition/company_mappings/
```

The P5 artifact is separate:

```text
artifacts/theme_decomposition/tech_bottleneck_crosswalks/
  ai_power_tech_bottleneck_crosswalk_v1.json
```

No input file is rewritten.

## Stable IDs

The existing CSV rows do not have IDs, so the loader derives deterministic identifiers from row content:

```text
tech_bottleneck_review_universe_v1:{stock_code}
tech_bottleneck_evidence_v1:{stock_code}:{digest}
tech_bottleneck_source_v1:{stock_code}:{digest}
```

Evidence IDs include stock code, repository-relative source reference, page, claim type, and evidence text. Source IDs include stock code, repository-relative source reference, source type, and title. The 96-bit digest is independent of the local checkout prefix and CSV row order; duplicate derived IDs and ambiguous source keys are rejected.

The artifact also pins SHA-256 digests for the dataset, evidence index, and source index. Upstream changes therefore produce an explicit `INPUT_SNAPSHOT_DIGEST_MISMATCH` instead of silently changing the crosswalk.

## Crosswalk Fields

Roadmap fields:

- `theme_node_id`;
- `company_code`;
- `existing_review_universe_id`;
- `existing_evidence_ids`;
- `new_theme_evidence_ids`;
- `confidence`;
- `review_status`.

Traceability fields:

- `crosswalk_id`;
- `theme_id`;
- `company_name`;
- `mapping_id`;
- `relationship_type`;
- `notes`.

Every reviewed crosswalk needs confidence of at least `0.7`, existing evidence for the same company, and new evidence belonging to the exact Phase 4 mapping.

## AI Power Result

Linked to the existing universe:

| Company | Theme node | Existing universe state | Result |
|---|---|---|---|
| 英维克 `002837.SZ` | `liquid_cooling` | Existing pending-review row retained | Linked with two existing annual-report evidence rows and two Phase 4 evidence items |
| 科华数据 `002335.SZ` | `ups` | Existing pending-review row retained | Linked with one existing annual-report evidence row and two Phase 4 evidence items |

Explicit coverage gaps:

| Company | Theme node | Reason |
|---|---|---|
| 欧陆通 `300870.SZ` | `server_power_supply` | Not present in the existing 378-company universe |
| 中恒电气 `002364.SZ` | `hvdc_power` | Not present in the existing 378-company universe |

A coverage gap is not a rejection and does not add the company to the universe.

## Validation Gates

The loader rejects:

- any input path other than the three authoritative review-universe CSV paths;
- missing or changed input snapshots;
- missing required CSV columns or evidence/source stock coverage outside the 378-company universe;
- universe-count or duplicate-code drift;
- missing Phase 4 mappings or incomplete mapping coverage;
- cross-theme, cross-node, or cross-company references;
- existing evidence belonging to another company;
- new evidence outside the Phase 4 mapping;
- present companies mislabeled as coverage gaps;
- duplicate coverage of one Phase 4 mapping;
- low-confidence reviewed crosswalks;
- admission, signal, quality-pool, or reviewer-decision fields;
- unknown artifact fields that could masquerade as review or admission state;
- any guardrail enabling DB, CSV, or manual-review writes.

## CLI

```bash
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk validate
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk summary
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk show-theme \
  --theme-id ai_power_value_capture_v1
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk show-company \
  --company-code 002837.SZ
.venv/bin/python -m stock_research.theme_tech_bottleneck_crosswalk coverage-gaps
```

`show-theme` and `show-company` resolve the unchanged review-universe row, selected existing evidence and source metadata, the Phase 4 mapping, and new theme evidence. Crosswalk review state is exposed only as `crosswalk_review_status`; existing `frontend_review_status` and any current manual-review overlay remain nested, separate, and unmodified.

## Current Boundary

- artifact and CLI only; no dashboard changes;
- no DB writes or CSV writeback;
- no automatic universe admission for coverage gaps;
- no scoring or research-priority ranking;
- no investment conclusions;
- Phase 6 remains the next scoring/review-workflow phase.
