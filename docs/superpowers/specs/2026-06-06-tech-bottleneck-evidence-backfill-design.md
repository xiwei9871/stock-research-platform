# tech-bottleneck Evidence Backfill Design

## Purpose

`tech-bottleneck-evidence-backfill` fills the data gaps found by `tech-bottleneck-data-readiness-audit`.

The immediate goal is not full-market discovery. The goal is to make the existing topN candidate pool testable under point-in-time rules:

```text
weekly top50 candidates from 2025-01-01
-> evidence backfill for candidate assets and candidate dates
-> readiness audit rerun
-> 20D / 60D / 120D / 250D comparison only after readiness improves
```

The first target pool is the current pilot:

- Candidate window: 2025-01-01 onward.
- Candidate source: weekly `manual_v1` top50.
- Candidate rows: 1100.
- Candidate assets: 647.
- Current blocker: `ready_for_scoring = 0`, mainly because `has_product_revenue_exposure = 8/1100`.

## Scope

The backfill is candidate-driven. It only pulls and normalizes evidence for assets that appear in an input candidate CSV.

Version 1 covers four evidence families:

1. Product and revenue exposure.
2. Bottleneck/chokepoint thesis evidence.
3. Capacity, customer certification, and technical barrier evidence.
4. Invalidation evidence.

It does not:

- Run a full-market scan.
- Generate buy or sell signals.
- Change return testing logic.
- Mark weak text evidence as equivalent to audited financial table evidence.
- Use evidence dated after a candidate's `as_of_date`.

## Position In Workflow

```text
Candidate CSV
-> tech-bottleneck-evidence-backfill
-> normalized evidence artifacts
-> tech-bottleneck-data-readiness-audit
-> tech-bottleneck-discovery scoring or packet generation for ready candidates
-> human review
```

The backfill is an upstream data step. Readiness remains the gatekeeper.

## Inputs

Required candidate CSV columns:

- `asset_id`

Recommended columns:

- `stock_name`
- `trade_date`
- `candidate_source`
- `rank`

CLI options:

- `--candidates-csv`: input candidate pool.
- `--start-date`: first candidate date to consider. Default: minimum `trade_date` in the CSV.
- `--end-date`: last candidate date to consider. Default: maximum `trade_date` in the CSV.
- `--lookback-days`: evidence lookback window before each candidate date. Default: 365.
- `--source`: data source selector. Initial values: `existing-db`, `cninfo-docs`, `text-proxy`.
- `--output-dir`: artifact directory.
- `--run-id`: stable identifier.
- `--service`: database service name. Default: `stock_research`.

## Evidence Contract

Every normalized evidence row uses this shape:

```text
run_id
asset_id
stock_name
candidate_trade_date
as_of_date
evidence_date
source_type
source_id
source_title
source_url
evidence_type
matched_keyword
evidence_snippet
source_confidence
is_proxy
as_of_safe
metadata_json
```

### Evidence Types

- `product_revenue_exposure`
- `product_exposure_proxy`
- `bottleneck_keyword`
- `capacity`
- `customer_certification`
- `technical_barrier`
- `patent_proxy`
- `news_or_announcement_catalyst`
- `invalidation`

### Source Confidence

- `strong`: structured financial table or official announcement/report table.
- `medium`: company announcement text, annual report chapter, investor relations activity record, or broker report text with source date.
- `weak`: keyword-only news or report snippet without product/revenue specificity.

`has_product_revenue_exposure` should require `strong` product evidence. Proxy product evidence is saved but should not satisfy that flag unless the readiness design is explicitly changed later.

## Point-in-Time Rules

Each evidence row must be usable only when:

```text
evidence_date <= candidate as_of_date
and evidence_date >= as_of_date - lookback_days
```

For financial statements:

```text
report_period <= candidate as_of_date
and publish_date <= candidate as_of_date
```

If `publish_date` is unavailable, the row is not `as_of_safe` unless the source is already present in an existing point-in-time database table whose ingestion semantics are trusted.

Backfilled artifacts keep unsafe rows for audit, but readiness must ignore `as_of_safe = false`.

## Source Paths

### Path A: Existing Database Backfill

Use current tables first because they are already integrated:

- `finance.main_business_composition`
- `research.stock_report_event`
- `research.stock_report_source`
- `event.institution_survey`
- `event.earnings_forecast`
- `event.earnings_express`
- `research.news_event_source`
- `research.news_event_mention`

This path should produce an evidence artifact even if coverage remains low. It establishes the baseline and prevents double-counting when external data is added.

### Path B: Official Disclosure Document Backfill

Use official disclosure documents to recover product/revenue exposure and management discussion text.

Primary document classes:

- Annual reports.
- Semiannual reports.
- Investor relations activity records.
- Product, capacity, customer, or project announcements.

Extraction targets:

- Main business by product table.
- Business overview and major product descriptions.
- Capacity expansion or project construction sections.
- Customer certification, supplier qualification, and order backlog language.
- Risk sections containing demand miss, price cut, oversupply, margin pressure, or customer-loss language.

This is the preferred first external path because it is closest to point-in-time public information.

### Path C: Text Proxy Backfill

Use existing broker reports, surveys, announcements, and news text to extract Serenity-style evidence.

Keyword groups are inherited from `tech_bottleneck_readiness.py`:

- Bottleneck: `卡脖子`, `瓶颈`, `稀缺`, `国产替代`, `自主可控`, `关键材料`, `关键设备`, `核心零部件`, `供应链安全`, `进口替代`.
- Capacity: `产能`, `扩产`, `爬坡`, `良率`, `交付周期`, `供给受限`, `供需缺口`, `满产`, `达产`.
- Customer certification: `客户认证`, `客户验证`, `导入`, `定点`, `合格供应商`, `供应商认证`, `批量供货`, `在手订单`.
- Technical barrier: `专利`, `技术壁垒`, `工艺壁垒`, `核心技术`, `自研`, `高精度`, `高可靠`, `高纯`, `先进制程`.
- Invalidation: `降价`, `需求不及预期`, `产能过剩`, `客户流失`, `毛利下滑`, `延期`, `减值`, `竞争加剧`, `路线变化`, `技术替代`.

Proxy evidence must store the matched snippet and source. It should improve thesis evidence coverage, but it should not replace structured product/revenue exposure.

### Path D: Patent Proxy Backfill

Patent data is phase 2. Version 1 may only create a proxy evidence row if a source text explicitly mentions patents or technical barriers.

Later patent integration should use company and subsidiary names as applicants, then store:

- Patent title.
- Abstract.
- Application date.
- Publication date.
- Applicant.
- IPC classification.
- Matched technical keywords.

Patent evidence should not block the first round of return testing.

## Outputs

Version 1 writes file artifacts, not database tables:

- `evidence.csv`: normalized row-level evidence.
- `evidence.json`: grouped evidence by candidate.
- `coverage_summary.md`: coverage by evidence type, source type, and as-of safety.
- `source_gap_report.csv`: candidate/flag combinations still missing after backfill.

Database persistence can be added after the artifact contract is stable.

## Readiness Integration

The existing readiness audit should gain an optional evidence-artifact input:

```text
tech-bottleneck-data-readiness-audit
  --candidates-csv ...
  --evidence-csv outputs/.../evidence.csv
```

When provided, readiness merges database context with evidence rows:

- `product_revenue_exposure` with `source_confidence = strong` sets `has_product_revenue_exposure`.
- `bottleneck_keyword` sets `has_bottleneck_keywords`.
- `capacity` sets `has_capacity_evidence`.
- `customer_certification` sets `has_customer_certification_evidence`.
- `technical_barrier` or `patent_proxy` sets `has_patent_or_technical_barrier`; proxy status is preserved.
- `news_or_announcement_catalyst` sets `has_news_or_announcement_catalyst`.
- `invalidation` sets `has_invalidation_evidence`.

Rows with `as_of_safe = false` are reported but ignored for flag computation.

## Success Criteria

The first backfill pass is successful when it meets all of these criteria on the current pilot pool:

- `has_product_revenue_exposure` improves from 0.7% to at least 50%.
- `has_capacity_evidence` improves from 9.7% to at least 20%.
- `has_bottleneck_keywords` improves from 1.4% to at least 10%.
- Every true flag has at least one source trace in the JSON detail payload.
- Readiness still excludes evidence dated after the candidate as-of date.
- The rerun creates a nonzero `ready_for_scoring` or a clearly smaller `data_blocked` group with explicit remaining gaps.

If those targets are not met, the correct next step is source expansion, not return testing.

## Testing Strategy

Unit tests should cover:

- Candidate date window expansion.
- Evidence normalization.
- As-of filtering.
- Strong vs proxy product exposure.
- Keyword classification by evidence type.
- Merging evidence artifacts into readiness flags.
- Unsafe evidence rows being ignored.

An integration smoke should run:

```text
candidate CSV
-> backfill artifacts
-> readiness audit with evidence CSV
-> coverage summary
```

The smoke does not need network access. It can use fixture documents and fixture evidence rows.

## Risks

### Look-ahead Bias

This is the highest risk. The design requires `publish_date` or trusted existing PIT semantics for any financial statement row. Unsafe rows are kept for debugging but ignored.

### False Positive Keyword Matches

Keywords like `订单` and `国产替代` can be too broad. Version 1 preserves snippets and source fields so false positives are reviewable. Later versions can add sentence-level classifiers.

### Product Table Extraction Quality

PDF and HTML tables can be messy. Version 1 accepts partial product rows if the source is official and the product item is clear. Numeric revenue fields are preferred but not mandatory for product exposure evidence.

### Overbuilding

The first version is file-based and candidate-scoped. It avoids a new permanent database schema until the evidence contract proves useful.
