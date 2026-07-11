# Theme Decomposition Artifact Schema v1.5 Migration

Updated: 2026-07-10

## Purpose

Schema v1.5 adds a deterministic review gate to the Phase 1 read-only artifact baseline. It does not add database writes, network access, automatic company mapping, or dashboard writeback.

## Version Change

Old artifact version:

```text
theme_decomposition_v1
```

New artifact version:

```text
theme_decomposition_v1_5
```

The loader rejects unsupported versions with `UNSUPPORTED_ARTIFACT_VERSION`. Artifacts must be migrated before loading.

## Required Fields

### source_item.review_status

Allowed values:

```text
accepted
needs_full_text
lead_only
rejected
unknown
```

### content_claim.platform_use_status

Allowed values:

```text
research_lead
draft
reviewed
blocked
```

### theme_node.node_review_status

Allowed values:

```text
draft
reviewed
needs_evidence
blocked
```

## Review Gate Rules

The loader enforces:

1. An `S4` source cannot be `accepted`.
2. A reviewed claim cannot be supported only by `S4` sources.
3. Every reviewed claim must have at least one accepted source.
4. A reviewed claim cannot use a rejected source.
5. A reviewed node must have `evidence_strength >= 3`.
6. A reviewed node cannot use a rejected source through its value-capture assessment evidence.
7. High-value, high-bottleneck, low-evidence nodes are included in `high_priority_evidence_gap`.

High-priority evidence-gap thresholds are:

```text
value_capture_score >= 4
bottleneck_score >= 4
evidence_strength < 3
```

## Stable Error Codes

Phase 1.5 adds stable validation codes suitable for CLI, tests, and future API consumers:

```text
MISSING_ARTIFACT_VERSION
UNSUPPORTED_ARTIFACT_VERSION
INVALID_SOURCE_REVIEW_STATUS
INVALID_CLAIM_PLATFORM_USE_STATUS
INVALID_NODE_REVIEW_STATUS
S4_SOURCE_CANNOT_BE_ACCEPTED
REVIEWED_CLAIM_S4_ONLY
REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE
REVIEWED_CLAIM_USES_REJECTED_SOURCE
REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE
REVIEWED_NODE_USES_REJECTED_SOURCE
```

On validation failure, the CLI returns exit code `2` and writes JSON to stderr:

```json
{
  "error_code": "S4_SOURCE_CANNOT_BE_ACCEPTED",
  "message": "sources[1] S4 source cannot be accepted",
  "status": "error"
}
```

## Sample Artifact Migration

Both sample themes now use v1.5:

- no placeholder source is accepted before full text or an excerpt is reviewed;
- official and filing source slots are `needs_full_text`;
- media, social, and video sources are `lead_only`;
- partially verified claims remain `draft`;
- oral claims remain `research_lead`;
- unverified stock mappings are `blocked`;
- high-priority evidence gaps are marked `needs_evidence` at node level.

## Validation

```bash
.venv/bin/pytest tests/test_theme_decomposition.py -q
.venv/bin/python -m stock_research.theme_decomposition validate
.venv/bin/stock-research theme-decomposition summary
```

