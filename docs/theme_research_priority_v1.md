# Theme Research Priority And Human Review Queue v1

Updated: 2026-07-11

## Purpose

Phase 6 ranks research work across the Theme-driven Research Engine:

```text
Theme Node Priority
Company Research Priority
Evidence Gap Priority
Human Review Queue
```

The scores are queue-ordering tools. They are not expected returns, probabilities, recommendations, ratings, entry signals, or admission decisions.

## Policy Artifact

The versioned policy lives at:

```text
artifacts/theme_decomposition/priority_policies/
  theme_research_priority_policy_v1.json
```

It contains weights, thresholds, materiality conversion, allowed dimensions, forbidden dimensions, and read-only guardrails. The calculator rejects unknown fields and weights that do not sum to one.

All numeric policy values and Phase 4 mapping confidence values must be finite. `NaN`, infinity, booleans, and out-of-range values are rejected before scoring.

## Score Scale

All components use the existing `0-5` scale and are normalized to `0-100`:

```text
score = 100 * sum(component * weight) / 5
```

Scores are rounded to two decimals. Every output includes raw and weighted components.

## Theme Node Scores

Deep-research readiness:

| Dimension | Weight |
|---|---:|
| value capture | 0.25 |
| bottleneck | 0.25 |
| localization gap | 0.10 |
| supply tightness | 0.10 |
| evidence strength | 0.30 |

Evidence-gap priority:

| Dimension | Weight |
|---|---:|
| value capture | 0.20 |
| bottleneck | 0.25 |
| localization gap | 0.10 |
| supply tightness | 0.10 |
| `5 - evidence_strength` | 0.35 |

Classification:

- evidence strength `<= 2` and gap score `>= 68`: `evidence_collection_priority`;
- evidence strength `>= 3` and deep-research score `>= 70`: `deep_research_priority`;
- otherwise `monitor`.

Current output covers all 34 nodes:

- 15 evidence-collection priorities;
- 2 deep-research priorities;
- 17 monitor nodes.

Examples:

- `transformer`: evidence-gap score `73.0`, collect evidence;
- `liquid_cooling`: deep-research score `77.0`, proceed to deep research.

Each evidence-gap row also includes `affected_mapping_count` and a stable `affected_company_mappings` list. The list identifies mapped companies, their P5 integration state, and their company research action without changing either the node or company merit score.

## Company Priority

| Dimension | Weight |
|---|---:|
| value capture | 0.15 |
| bottleneck | 0.20 |
| localization gap | 0.10 |
| supply tightness | 0.10 |
| evidence strength | 0.10 |
| company relevance | 0.20 |
| business materiality | 0.15 |

`company_relevance_score = Phase 4 mapping confidence * 5`.

Business materiality:

| Level | Score |
|---|---:|
| `core_business` | 5 |
| `meaningful_segment` | 4 |
| `emerging_segment` | 3 |
| `reserve_only` | 1 |
| `concept_only` | 0 |
| `unknown` | 1 |

Current company ordering:

| Company | Score | Band | Recommended action |
|---|---:|---|---|
| 英维克 `002837.SZ` | 78.8 | high | deep company research |
| 中恒电气 `002364.SZ` | 77.2 | high | review crosswalk coverage gap |
| 欧陆通 `300870.SZ` | 75.6 | high | review crosswalk coverage gap |
| 科华数据 `002335.SZ` | 68.4 | medium | strengthen node evidence |

P5 integration status never enters the weighted score. It only changes queue routing.

Both P5 integration state and existing tech-bottleneck review context are explicitly regression-tested as non-scoring context.

## Human Review Queue

The current queue has 21 items:

- 15 `collect_node_evidence`;
- 2 `deep_node_research`;
- 1 `deep_company_research`;
- 1 `strengthen_node_evidence_for_company`;
- 2 `review_crosswalk_coverage_gap`.

Every item uses `human_review_status = pending_human_review`. Existing tech-bottleneck review state is returned as `existing_review_context`, remains separate, and is not changed by P6.

P6 v1 has no review-decision ingest or writeback command.

## Guardrails

The policy and outputs enforce:

- research-only operation;
- no signal or admission use;
- no automatic reviewer decision;
- no database writes;
- no price or market-position inputs;
- no valuation, return, momentum, freshness, low-position, technical-signal, or entry-timing dimensions.

The existing stock-level tech-bottleneck `research_priority_score` is not reused because it contains dimensions outside the Theme-driven Research Engine contract.

## CLI

```bash
.venv/bin/python -m stock_research.theme_research_priority validate
.venv/bin/python -m stock_research.theme_research_priority summary
.venv/bin/python -m stock_research.theme_research_priority theme-nodes
.venv/bin/python -m stock_research.theme_research_priority companies
.venv/bin/python -m stock_research.theme_research_priority evidence-gaps
.venv/bin/python -m stock_research.theme_research_priority review-queue
.venv/bin/python -m stock_research.theme_research_priority show-company \
  --company-code 002837.SZ
```

Validation and upstream artifact/file failures return structured JSON on stderr with exit code `2`; successful commands emit JSON on stdout.

## Current Boundary

- artifact policy and read-only calculator only;
- no dashboard changes;
- no persistent review events;
- no automatic evidence collection;
- no company admission for P5 coverage gaps;
- no DB productionization;
- Phase 7 remains the read-only dashboard phase.
