# Hibor A-Tier Report Backfill Design

## Goal

Backfill A-share brokerage research reports from Hibor for the window `2024-10-01` through the current run date, using only trusted sell-side institutions. The pipeline must automatically discover and download PDFs while the user keeps Hibor open and logged in, then reuse the existing stock report source/event, PDF extraction, and feature pipelines.

## Scope

In scope:

- Full active A-share universe from `core.asset_master`.
- Report discovery through Hibor search pages using the authenticated Hibor client cache.
- PDF downloads for trusted A-tier institutions only.
- Local PDF import into `research.stock_report_source` and `research.stock_report_event`.
- PDF field extraction and daily report feature generation.
- Durable batch status, resume behavior, and coverage reports.

Out of scope:

- Reverse engineering unsupported Hibor APIs beyond authenticated pages already available to the logged-in client.
- Downloading reports from non-A-tier institutions in the first run.
- Storing PDF text. The system stores metadata and extracted structured fields only.
- Automatic trading decisions.

## A-Tier Institution Policy

A-tier institutions include two groups.

A1 domestic top-tier brokers:

- 中信证券
- 中金公司
- 华泰证券
- 国泰君安
- 招商证券
- 海通证券
- 广发证券
- 中信建投
- 申万宏源
- 兴业证券
- 国信证券
- 光大证券
- 东吴证券

A2 foreign, joint-venture, and Hong Kong/international brokers:

- 高盛 / Goldman Sachs
- 摩根士丹利 / Morgan Stanley / 大摩
- 摩根大通 / JPMorgan / JP Morgan / 小摩
- 花旗 / Citi / Citigroup
- 瑞银 / UBS / 瑞银证券
- 瑞信 / Credit Suisse
- 美银证券 / BofA / Bank of America
- 汇丰 / HSBC
- 德意志银行 / Deutsche Bank
- 野村 / Nomura
- 麦格理 / Macquarie
- 杰富瑞 / Jefferies / 富瑞
- 里昂证券 / CLSA
- Bernstein
- 招银国际 / CMB International
- 建银国际 / CCB International
- 海通国际
- 中金国际
- 华兴证券 / China Renaissance
- 交银国际

The whitelist and aliases must live in a config file, not hard-coded business logic. Each normalized institution carries:

- `institution_name`
- `aliases`
- `tier`: `A`
- `group`: `A1_domestic` or `A2_foreign_hk_international`
- `region`: `domestic`, `foreign`, or `hk_international`

## Discovery Flow

The pipeline builds tasks from active assets:

- `asset_id`
- `ts_code`
- `symbol`
- `stock_name`
- `start_date`
- `end_date`
- `status`

For each asset, the downloader:

1. Loads Hibor auth parameters from the running Hibor client cache.
2. Searches Hibor by stock code.
3. Parses result rows for title, detail URL, visible metadata, and operation links.
4. Normalizes broker names using the whitelist config.
5. Keeps only reports whose normalized institution is A-tier.
6. Keeps only reports dated from `2024-10-01` through run date.
7. Deduplicates by normalized title, institution, stock code, and report date.
8. Downloads all retained A-tier PDFs.

There is no fixed per-stock report cap. A safety threshold pauses a stock when retained A-tier matches exceed 50 reports, marking it `needs_review` to prevent runaway parsing errors.

## Batch Execution

The backfill runs in batches:

- Default batch size: 50 stocks.
- Default request sleep: 1.5 seconds.
- Default PDF download sleep: 2.0 seconds.
- Stop condition: pause after 10 consecutive search/download failures.
- Resume: status files skip completed downloads and retry transient failures.

Each run writes:

- `hibor_a_tier_backfill_tasks.csv`
- `hibor_a_tier_discovered_reports.csv`
- `hibor_a_tier_downloaded_reports.csv`
- `hibor_report_source_candidates.csv`
- `hibor_report_event_candidates.csv`
- `stock_report_pdf_field_backfill.csv`
- `stock_report_feature_daily.csv`
- Markdown coverage report

## Storage

Downloaded reports use existing schemas:

- `research.stock_report_source`
- `research.stock_report_event`
- `research.stock_report_feature_daily`

Source rows use:

- `source_type = 'hibor_a_tier'`
- `source_name = '慧博智能策略终端'`
- `public_access = false`
- `copyright_note = 'Downloaded from Hibor terminal for internal research use only.'`

Metadata includes:

- raw Hibor title
- normalized broker
- broker tier/group/region
- detail URL
- download URL hash
- local PDF path
- downloader version

## Quality Gates

Each batch report must include:

- searched stock count
- stocks with A1 coverage
- stocks with A2 coverage
- downloaded PDF count
- duplicate report count
- skipped non-A-tier count
- paused `needs_review` count
- search failure count
- download failure count
- PDF parse success rate
- target price hit rate
- rating hit rate
- risk section hit rate

Completion target for the first full pass:

- All active A-share stocks have a terminal status.
- Every downloaded PDF has a source row and event row.
- Every parsed PDF has structured extraction status.
- Coverage gaps are explainable as no A-tier report, search failure, download failure, or needs review.

## Operating Runbook

1. Open Hibor and keep it logged in.
2. Open any Hibor search or report detail page if auth cache is stale.
3. Generate the full active-universe task file.
4. Run a 50-stock pilot batch.
5. Review coverage and failure reasons.
6. Run the full backfill in 50-stock batches.
7. Import to DB only after the pilot validates output quality.
8. Build daily report features after each successful batch or after the full run.

## Risks

- Hibor search HTML may change. Mitigation: parser tests with captured HTML fixtures.
- Hibor auth cache can expire. Mitigation: explicit auth probe before each batch.
- Excessive request rate may trigger throttling. Mitigation: conservative sleeps and failure pause.
- Broker aliases can miss matches. Mitigation: coverage report lists unknown brokers for review.
- PDF filenames vary. Mitigation: source rows use parsed Hibor metadata, not only filename parsing.
