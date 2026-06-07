# Tech Bottleneck Core Tech Top100 Design

## Goal

Build a second-generation tech-bottleneck discovery experiment that tests whether the current six-stock strict promotion result is caused by a narrow top50 input pool, insufficient evidence coverage, or overly broad non-technology noise in the starting universe.

The experiment keeps the current strict evidence-chain idea, but changes the entry point from `top50 all sectors` to `top100 core technology sectors`, then adds targeted evidence backfill for the most promising incomplete names.

## Current Baseline

The existing run covers `2025-01-01` through the latest available trading day, currently `2026-06-05`.

Current strict output:

- Input: weekly `manual_v1` top50 candidate pool.
- Candidate rows: 3700.
- Candidate assets: 1867.
- Final `quality_promotion_pool`: 12 rows, 6 assets.
- Main bottleneck: most rows fail because product exposure and semantic bottleneck/technical evidence are not linked to the same product family.

The current six strict promotion assets are valid as a conservative P1 observation pool, but the result is too sparse to conclude that the method itself only finds six opportunities.

## Experiment Questions

This experiment should answer four questions:

1. Does increasing the entry pool from top50 to top100 surface additional valid tech-bottleneck candidates?
2. Does a core-technology sector gate reduce consumer, financial, cyclical, and generic growth noise?
3. Are rejected core-technology names rejected because of missing evidence, missing product-family mapping, or genuine lack of bottleneck/technical evidence?
4. Does targeted evidence backfill convert meaningful P2 names into P1 promotions without loosening the strict final rule?

## Scope

In scope:

- Generate a top100 candidate pool for the same date window.
- Add a reusable core-technology sector gate.
- Re-run the existing evidence readiness and quality review flow on the top100 core-tech subset.
- Produce P1/P2/P3 output queues.
- Produce a comparison report against the existing top50 strict run.
- Add targeted evidence-gap outputs for core-tech P2 candidates.

Out of scope for this design:

- Full-market scanning.
- Live trading or automatic buy/sell decisions.
- Changing the portfolio execution system.
- Treating absolute or excess return as the first validation target.
- Manually approving borderline names inside the automated P1 pool.

## Candidate Pool

The new candidate source should be named:

`tech_bottleneck_core_tech_top100`

Candidate generation rules:

- Source score table: `factor.stock_score_daily`.
- Score version: `manual_v1`.
- Dates: `2025-01-01` through latest available trading day.
- Selection frequency: weekly, matching the current top50 experiment cadence.
- Ranking depth: top100 per selected date.
- Output should retain the original rank and score fields so top50 versus ranks 51-100 can be compared.

The top100 pool should not replace the current top50 pool. It should be a separate experiment artifact.

## Core Technology Gate

The core-tech gate should classify each candidate before quality review.

Pass categories:

- Semiconductor equipment.
- Semiconductor materials and components.
- Semiconductor testing and metrology.
- Display materials and equipment.
- Optical communication components and modules.
- Advanced electronic components, including MLCC, magnetic materials, sensors, PCB materials, and high-frequency substrates.
- Advanced industrial equipment and robotics components.
- High-end medical devices and imaging equipment.
- Advanced chemical and polymer materials with clear semiconductor, electronics, new-energy, aerospace, or medical use.
- Cloud, AI infrastructure, industrial software, and data infrastructure when the business has product exposure rather than pure application marketing.

Reject categories:

- Banks, insurers, brokers, and other financials.
- Consumer food, beverage, apparel, pet, household, and restaurant names.
- Highways, utilities, ports, coal, generic shipping, and non-technology infrastructure.
- Generic auto parts without material, sensor, control, or high-end equipment evidence.
- Generic pharma, APIs, and diagnostics unless the evidence supports a platform technology bottleneck.
- Low-technology industrial products where the evidence is mainly order growth or export growth.

Implementation should classify with conservative deterministic rules first:

- Industry name and existing candidate metadata if available.
- Product-family classification from official product evidence.
- Evidence keywords from the existing evidence table.

If the gate cannot classify a row as pass, it should not enter strict P1 review, but it should be counted in diagnostics.

## Evidence Backfill Strategy

Evidence backfill should be targeted, not full-universe brute force.

Priority order:

1. Core-tech candidates that already have product exposure and either bottleneck or technical evidence, but miss one or two support fields.
2. `needs_product_family_mapping` rows with strong core evidence.
3. `needs_more_evidence` rows from quality review.
4. Top100 rank 51-100 additions that pass the core-tech gate but are data blocked.

Evidence types to backfill:

- Official product revenue exposure from annual and semiannual reports.
- Research-report snippets for bottleneck, technical barrier, localization, client validation, capacity, and catalyst evidence.
- Company announcements for capacity, customer certification, orders, product qualification, and invalidation evidence.
- News only when it contains date-stamped product, client, capacity, or catalyst evidence.

Evidence must remain point-in-time safe:

- Evidence used for a candidate date must be published on or before that date, unless the output explicitly labels it as post-date research and excludes it from P1.
- The report must separate PIT-safe evidence from post-date explanatory evidence.

## Quality Review

The strict P1 auto-promotion rule should remain conservative:

- Same-product-family linkage is required.
- Bottleneck evidence is required.
- Technical barrier evidence is required.
- At least one commercialization support signal is required from customer certification, capacity, or catalyst evidence.
- Excluded categories cannot auto-promote.

The new flow should produce three output queues:

- `P1_auto_promotion`: strict evidence chain closes automatically.
- `P2_research_queue`: core-tech candidate with credible direction but incomplete mapping or evidence.
- `P3_reject_or_noise`: non-core-tech, unsupported, generic growth, or excluded category.

P2 should include a machine-readable next evidence need:

- `needs_product_family_mapping`
- `needs_bottleneck_evidence`
- `needs_technical_barrier_evidence`
- `needs_customer_or_certification_evidence`
- `needs_capacity_evidence`
- `needs_catalyst_evidence`
- `needs_pit_safe_source`

## Outputs

The run directory should be:

`outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/`

Required files:

- `candidates_top100.csv`: all weekly top100 candidates.
- `core_tech_gate.csv`: every candidate with pass/reject category and reason.
- `core_tech_candidates.csv`: rows that pass the gate.
- `evidence_coverage.csv`: coverage flags and evidence counts by candidate row.
- `quality_review.csv`: P1/P2/P3 row-level decisions.
- `promotion_assets.csv`: asset-level P1 promotions.
- `research_queue_assets.csv`: asset-level P2 queue.
- `rejected_assets.csv`: asset-level P3 rejects.
- `top50_vs_top100_diff.csv`: names added by ranks 51-100 and their downstream status.
- `baseline_comparison.md`: comparison with the current top50 strict result.
- `manifest.json`: inputs, date range, row counts, asset counts, gate counts, decision counts, and generated files.

## Comparison Metrics

The comparison report should include:

- Top50 baseline P1 asset count.
- Top100 core-tech P1 asset count.
- Top100 core-tech P2 asset count.
- Count of new P1 names from ranks 51-100.
- Count of new P2 names from ranks 51-100.
- Most common P2 evidence gaps.
- Most common P3 rejection reasons.
- List of top50 names that fail the core-tech gate.
- List of current six P1 names and whether they still pass in the new flow.

No return-based conclusion should be required for this experiment. Outcome tracking can be added after the data-readiness and selection-difference audit stabilizes.

## Success Criteria

The experiment is successful if it produces an auditable answer to these questions:

- Whether top100 materially expands the core-tech candidate pool.
- Whether the core-tech gate reduces non-technology noise.
- Whether the strict P1 list remains small because evidence is missing, mapping is incomplete, or the rule is correctly strict.
- Which P2 names are the highest-value targets for additional automated evidence backfill.

The first implementation should not optimize for more P1 names. It should optimize for trustworthy classification and a clear P2 gap map.

## Risks

Primary risks:

- Sector gate could be too narrow and exclude legitimate bottleneck names in traditional industries.
- Sector gate could be too broad and reintroduce generic growth noise.
- Research-report evidence may be post-date if timestamps are not enforced.
- Product-family mapping may still under-link product names and technical evidence.

Mitigations:

- Keep gate rejects in diagnostics rather than deleting them.
- Preserve original top100 rank and score for every row.
- Emit explicit P2 evidence needs instead of auto-promoting incomplete names.
- Keep P1 rule unchanged until the P2 audit shows a clear reason to tune it.

## Approval

This design is approved for implementation planning once reviewed by the user.
