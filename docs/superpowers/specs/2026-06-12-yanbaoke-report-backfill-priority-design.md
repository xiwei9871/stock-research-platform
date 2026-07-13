# Yanbaoke Report Backfill Priority Design

## Goal

Use the remaining Yanbaoke monthly quota to backfill high-value research reports from `2025-01-01` through `2026-06-12`, prioritizing core coverage before long-tail reports. The first objective is not indiscriminate full capture; it is to make the internal research database substantially complete for core companies, core industries, top brokers, and key market windows.

## Context

The existing project already has a Hibor A-tier report backfill design and broker whitelist configuration. This Yanbaoke plan should reuse the same downstream concepts:

- report source metadata
- report event metadata
- broker normalization
- duplicate detection
- PDF extraction status
- coverage reporting

Yanbaoke differs from the Hibor A-tier pass because the monthly quota is explicit and scarce. The backfill must therefore choose reports by priority score and coverage gaps, rather than downloading every matching result in date order.

## Scope

In scope:

- Candidate discovery for reports dated from `2025-01-01` through `2026-06-12`.
- A quota-aware priority queue for report download/import.
- Core coverage analysis by company, industry, broker, report type, and date window.
- Batch execution with checkpoints every 1,000 reports.
- Pilot batch of about 3,000 reports before larger historical backfill.
- Reuse of existing Hibor institution normalization where possible, extended only when Yanbaoke names differ.

Out of scope:

- Automatic trading decisions.
- Treating report text as redistributable content.
- Exhaustive download of every Yanbaoke report before core coverage has been validated.
- Changing existing factor, watchlist, or trading research logic unless report metadata becomes an approved input in a separate approved scope.

## Time Window

The initial historical window is fixed:

- `start_date = 2025-01-01`
- `end_date = 2026-06-12`

Future runs should continue as rolling monthly maintenance:

- current-month high-priority reports first
- 2026 gap backfill second
- 2025 historical gap backfill third

## Priority Model

Each candidate report receives a score from five dimensions.

| Dimension | Weight | High-priority examples |
| --- | ---: | --- |
| Report type | 30% | company deep dive, initiation, annual strategy, mid-year strategy, industry deep dive |
| Target importance | 25% | core A-share, index constituents, sector leaders, portfolio/watchlist names |
| Institution quality | 20% | A-tier brokers and trusted foreign/HK institutions |
| Time value | 15% | earnings season, policy windows, major market regime changes |
| Scarcity | 10% | missing in current database, rare broker coverage, uncovered industry |

The first implementation can use deterministic rules rather than machine learning. The priority score must be explainable in the coverage report so low-quality quota consumption is visible.

## Sector Priority

The candidate inventory must be organized by both stock and sector. A report should not enter the first pilot batch only because it is recent or because its asset has many available reports. The priority queue must include:

- `industry_lv1`
- `industry_lv2`
- `theme_bucket`
- `sector_priority`
- `sector_quota_bucket`
- `asset_priority`
- `coverage_gap_reason`

Default sector priority:

| Priority | Sector bucket | First-pass policy |
| --- | --- | --- |
| P0 | AI compute, semiconductor, advanced packaging, domestic substitution, robotics, low-altitude economy, autonomous driving, innovative drugs, medical devices, CXO | Fill deep reports, initiations, sector frameworks, and material earnings reviews first. |
| P1 | power equipment, new energy, storage, grid, defense, satellite chain, export chain, cross-border commerce, machinery, appliances, consumer recovery, food and beverage, tourism, aesthetic medicine | Fill core leaders and sector framework reports after P0 gaps. |
| P2 | banks, insurance, brokers, real estate chain, coal, non-ferrous metals, chemicals, steel, broad macro and strategy | Prefer strategy, supply-demand frameworks, and important policy-window reports. |
| P3 | ordinary short-comment-heavy sectors or reports without a clear asset/sector gap | Use only after core gaps are explained or when attached to a high-priority asset/window. |

The first 3,000-report pilot should use sector quotas rather than a single global top-N cut:

| Bucket | Pilot quota |
| --- | ---: |
| P0 growth and technology / healthcare mainlines | 1,200 |
| P1 policy, prosperity, export, and consumption mainlines | 900 |
| P2 financial, real estate, cycle, macro, and strategy | 500 |
| Cross-sector macro / allocation / thematic reports | 300 |
| Manual correction reserve | 100 |

Within each bucket, sort by the full priority score and coverage gap. If a bucket lacks enough valid Priority 1 or Priority 2 reports, unused quota flows to the highest-scoring uncovered bucket, not to low-value duplicates.

## Report Type Buckets

Priority 1:

- company deep dive
- initiation / first coverage
- industry deep dive
- annual strategy
- mid-year strategy
- major thematic strategy

Priority 2:

- earnings review
- result preview
- sector monthly or quarterly update
- policy impact analysis
- important target price or rating change

Priority 3:

- short comments
- daily strategy notes
- morning meetings
- duplicated event comments
- low-information market summaries

Priority 3 reports are downloaded only after core coverage gaps are resolved or when they cover a high-priority target during an important window.

## Batch Plan

### Phase 0: Inventory And Gap Scan

Build the candidate and existing-coverage inventory before spending large quota.

Outputs:

- `yanbaoke_candidate_reports.csv`
- `existing_report_coverage.csv`
- `yanbaoke_gap_matrix.csv`
- `yanbaoke_priority_queue.csv`
- `yanbaoke_backfill_inventory_report.md`

The gap matrix must group by:

- month
- broker / normalized institution
- industry
- asset / target
- report type
- source status

### Phase 1: Pilot Download

Download and import the top 3,000 candidates.

Purpose:

- validate parsing quality
- estimate duplicate rate
- confirm broker normalization
- confirm PDF availability
- check whether priority scoring actually improves core coverage

The pilot stops if any of these thresholds are breached:

- duplicate rate above 10%
- PDF download failure rate above 8%
- metadata parse failure rate above 10%
- more than 20% of downloaded reports classified as Priority 3

### Phase 2: 2026 Core Backfill

Backfill `2026-01-01` through `2026-06-12` before ordinary 2025 reports.

Target allocation:

- 800 to 1,000 reports per full 2026 month until core coverage stabilizes
- 300 to 500 reports for partial June 2026 in the first pass

Focus:

- 2026 annual strategy
- 2026 spring and mid-year strategy
- 2025 annual result reviews
- 2026 Q1 result reviews
- AI, semiconductor, robotics, innovative drugs, export chain, low-altitude economy, new energy, power, defense, consumer recovery, and policy-sensitive sectors

### Phase 3: 2025 Core Backfill

Backfill `2025-01-01` through `2025-12-31` after 2026 high-value gaps are under control.

Default monthly allocation:

- 250 to 300 company deep dive / initiation reports
- 150 to 200 earnings reviews and material company comments
- 120 to 150 industry deep dive / industry strategy reports
- 50 to 80 macro, strategy, fixed income, and overseas allocation reports
- 50 to 80 thematic reports

Months with major market, policy, or earnings events can receive extra quota.

### Phase 4: Long-Tail Refill

Use remaining quota only for explainable gaps:

- core company without deep coverage
- industry without deep or strategy coverage
- missing top-broker reports
- uncovered event windows
- high-quality second-tier broker deep dives
- overseas or Hong Kong reports that improve target coverage

## Monthly Quota Policy

Assume Yanbaoke provides about 1,000 reports per month.

Recommended recurring allocation:

| Use | Monthly quota |
| --- | ---: |
| Current-month new core reports | 250-350 |
| 2026 gap backfill | 300-400 |
| 2025 historical core backfill | 200-300 |
| Retry, reparse, and special gaps | 50-100 |

If current-month high-priority volume is unusually high, current-month capture takes precedence over 2025 long-tail backfill.

## Deduplication

Deduplicate candidates before download and again before import.

Primary duplicate keys:

- normalized title
- normalized institution
- report date
- asset code or target name
- source detail URL hash

Secondary duplicate checks:

- PDF hash if downloaded
- fuzzy title similarity
- same broker, same date, same asset, highly similar title

The coverage report must separate:

- skipped existing duplicate
- skipped same-source duplicate
- skipped cross-source duplicate
- imported new report

## Coverage Targets

The backfill is considered effective when these targets are met:

| Coverage dimension | Target |
| --- | ---: |
| Core company coverage | at least 90% |
| Core industry coverage | at least 95% |
| Top broker deep-report coverage | at least 85% |
| Key time-window coverage | at least 90% |
| Duplicate rate after import | at most 3% |
| Invalid PDF / failed download rate | at most 2% after retries |

Core company coverage means each core target has at least one useful company deep dive, initiation, or material earnings review in the window. Core industry coverage means each important industry has at least one industry deep dive, strategy, or major thematic report in the window.

## Execution Checkpoints

Every 1,000 downloaded/imported reports, produce:

- quota consumed
- imported new reports
- duplicate reports skipped
- parse success rate
- top missing companies
- top missing industries
- top missing brokers
- Priority 1 / 2 / 3 distribution
- next recommended batch

The process should not proceed blindly after a checkpoint with poor quality. The next batch should be generated from remaining coverage gaps.

## First Operating Sequence

1. Generate candidate inventory for `2025-01-01` through `2026-06-12`.
2. Generate current database coverage inventory.
3. Build the first priority queue.
4. Review the top 3,000 candidates before download.
5. Run the pilot batch.
6. Generate pilot coverage report.
7. If pilot quality is acceptable, continue with 2026 core backfill.
8. Recompute gaps after every 1,000 reports.
9. Move to 2025 core backfill only after 2026 coverage is acceptable.
10. Use residual quota for long-tail refill.

## Risks

- Yanbaoke metadata may not classify report type consistently. Mitigation: infer report type from title keywords and broker metadata, then include unknown types in review output.
- Quota may be consumed by duplicates if candidate deduplication is weak. Mitigation: perform pre-download duplicate checks against existing metadata.
- Some important reports may have generic titles. Mitigation: scarcity and target-importance scores can lift otherwise generic reports.
- Broker aliases may differ from Hibor names. Mitigation: write unknown broker names to a normalization review CSV.
- Current-month reports may be displaced by historical backfill. Mitigation: reserve monthly quota for current-month high-priority reports.

## Acceptance

The first phase is accepted when the system can produce a reviewed priority queue and pilot recommendation without downloading more than the approved pilot batch.

The full backfill is accepted when coverage targets are reached or remaining gaps are explicitly explained as unavailable, duplicate, failed, or low-value.
