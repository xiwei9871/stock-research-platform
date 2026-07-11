# Theme Research Priority And Human Review Queue v1 Design

Updated: 2026-07-11

## Purpose

Phase 6 converts the reviewed theme, node, company-mapping, and crosswalk layers into transparent research-work ordering:

```text
Theme Node Priority
Company Research Priority
Evidence Gap Priority
Human Review Queue
```

It does not score expected return, valuation, price momentum, entry timing, or trading merit. It cannot write an admission decision, reviewer decision, watchlist action, signal, or quality-pool change.

## Chosen Approach

Use a versioned scoring-policy artifact plus a deterministic standard-library calculator.

Rejected alternatives:

1. Hard-coded Python weights would make formula changes difficult to review and version.
2. Reusing the existing stock-level `research_priority_score` would import market-understanding, low-position, freshness, and fundamental-risk factors that are outside Theme-driven Research Engine Phase 6.
3. A database review workflow is premature before the scoring contract and human queue fields stabilize; DB persistence remains Phase 9.

## Inputs

The calculator reads only validated P1-P5 artifacts:

- themes and nodes from `artifacts/theme_decomposition/*.json`;
- Phase 4 company mappings;
- Phase 5 tech-bottleneck crosswalk details and existing manual-review context;
- one versioned policy from `artifacts/theme_decomposition/priority_policies/`.

No external network, price series, valuation data, return data, or database query is allowed.

## Score Scale

All component dimensions use the existing `0-5` scale. Weighted sums are normalized to `0-100`:

```text
score = 100 * sum(component_score * weight) / 5
```

Scores are rounded to two decimals. They rank research work only and are not probabilities.

## Theme Node Priority

Deep-research readiness weights:

```text
value_capture_score       0.25
bottleneck_score          0.25
localization_gap_score    0.10
supply_tightness_score    0.10
evidence_strength         0.30
```

Evidence-gap weights:

```text
value_capture_score       0.20
bottleneck_score          0.25
localization_gap_score    0.10
supply_tightness_score    0.10
evidence_gap_score        0.35
```

`evidence_gap_score = 5 - evidence_strength`.

Classification:

- `evidence_collection_priority`: evidence strength at most `2` and evidence-gap score at least `68`;
- `deep_research_priority`: evidence strength at least `3` and deep-research score at least `70`;
- otherwise `monitor`.

## Company Research Priority

Company dimensions:

```text
value_capture_score       0.15
bottleneck_score          0.20
localization_gap_score    0.10
supply_tightness_score    0.10
evidence_strength         0.10
company_relevance_score   0.20
business_materiality      0.15
```

`company_relevance_score = mapping confidence * 5`. Mapping confidence is already gated by Phase 4 evidence and relationship validation, so P6 does not add an opaque mapping-type multiplier.

Business-materiality conversion:

```text
core_business       5
meaningful_segment  4
emerging_segment    3
reserve_only        1
concept_only        0
unknown             1
```

P5 integration state is reported as `linked_existing_universe` or `coverage_gap`. It never changes the company priority score.

## Priority Bands

```text
high    score >= 75
medium  score >= 60
low     score < 60
```

These bands are queue labels, not investment ratings.

## Evidence Gap Priority

Evidence-gap output is node-first. It contains nodes classified as `evidence_collection_priority`, ordered by evidence-gap score and stable node ID. Company mappings attached to those nodes are listed as affected mappings, but a company is not automatically downgraded or rejected because node evidence is incomplete.

P5 crosswalk gaps remain an `integration_status` concern and are surfaced in the human review queue separately from evidence gaps.

## Human Review Queue

The queue combines actionable node and company research items. Every row has:

```text
queue_item_id
item_type
theme_id
theme_node_id
company_code
priority_score
priority_band
recommended_action
rationale_codes
human_review_status
integration_status
source_refs
```

Allowed recommended actions:

- `collect_node_evidence`;
- `deep_node_research`;
- `strengthen_node_evidence_for_company`;
- `deep_company_research`;
- `review_crosswalk_coverage_gap`;
- `monitor`.

All generated rows use `human_review_status = pending_human_review`. P6 v1 has no decision-ingest or writeback command.

## Guardrails

The policy must assert:

```text
research_only = true
used_for_signal = false
used_for_admission = false
auto_reviewer_decision = false
database_write_enabled = false
price_inputs_allowed = false
market_position_inputs_allowed = false
```

The loader rejects unknown policy fields, weights that do not sum to one, unsupported dimensions, incomplete materiality mappings, invalid thresholds, and any price/valuation/return/momentum/freshness/low-position dimension.

## Read Model And CLI

Commands:

```text
validate
summary
theme-nodes
companies
evidence-gaps
review-queue
show-company --company-code ...
```

Each output includes component scores and rationale codes so reviewers can reconstruct the ranking.

## Acceptance

P6 is complete when all 34 current nodes and all four Phase 4 company mappings are deterministically scored, evidence-gap and deep-research examples follow the policy, P5 link/gap status does not alter merit scores, every actionable item appears in a read-only human queue, forbidden market/trading fields are absent, P1-P6 regression tests pass, and independent review finds no unresolved high- or medium-risk issue.
