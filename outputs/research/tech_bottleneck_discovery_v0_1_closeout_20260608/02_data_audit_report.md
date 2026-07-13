# Tech Bottleneck Discovery v0.1 Data Audit Report

## Scope

This audit freezes the v0.1 data state for the ST-only strict pool. It covers 148 candidates and focuses on source-backed readiness for the three highest-priority Serenity method fields.

## Source-Backed Coverage

| field                        |   missing |   artifact_only |   primary_partial |   primary_strong |   total |   artifact_only_or_missing |   source_backed |
|:-----------------------------|----------:|----------------:|------------------:|-----------------:|--------:|---------------------------:|----------------:|
| supplier_concentration_type  |         0 |             101 |                13 |               34 |     148 |                        101 |              47 |
| customer_certification_stage |         0 |              97 |                16 |               35 |     148 |                         97 |              51 |
| revenue_exposure_bucket      |         0 |              93 |                 2 |               53 |     148 |                         93 |              55 |

## Asset-Level Coverage Distribution

|   source_backed_field_count |   asset_count |
|----------------------------:|--------------:|
|                           0 |            93 |
|                           1 |             3 |
|                           2 |             6 |
|                           3 |            46 |

## Interpretation

- `primary_strong`: source evidence supports a concrete value, or tier/field rules strongly support it.
- `primary_partial`: original source exists, but the source only partially supports the precise field value.
- `artifact_only`: local artifact or inferred mapping exists, but original source sentence-level evidence is not attached.
- `missing`: no usable evidence in the field.

## P1 Remediation Status

The earlier P1 gap set has been remediated to at least source-backed coverage for all 8 names. Two late gaps, 航天长峰 and 格林达, were supplemented through annual report sources. Their customer and supplier fields remain `primary_partial`, which is acceptable for v0.1 audit but should not be over-read as strong certification/order evidence.

## Data Boundaries

- The pool is source-backed enough for strategy-level rolling review.
- It is not yet complete enough for fully automated thesis writing on every candidate.
- Do not continue broad field-by-field completion before reviewing trading behavior; the next bottleneck is outcome attribution, not raw coverage.

## Key Files

- `outputs/research/serenity_source_collection_plan_20260608/p1_remaining_other_sources_annual_report_fill_alias_merged/serenity_source_backed_evidence_detail.csv`
- `outputs/research/serenity_source_collection_plan_20260608/p1_remaining_other_sources_annual_report_fill_alias_merged/serenity_source_backed_gap_summary.csv`
- `outputs/research/serenity_bottleneck_baseline_st_only_financial_state_20250101_20260605/strict_153_st_only_financial_state_candidates.csv`
