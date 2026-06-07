# Stock Daily Data Pipeline Design

Date: 2026-06-05

## Goal

Build an OpenClaw-scheduled daily A-share data pipeline that keeps high-frequency and daily-decision data fresh, produces Feishu progress reports, and leaves low-frequency structure data to monthly or quarterly jobs.

## Scope

The daily pipeline covers data that affects same-day or next-day research decisions:

- Daily market bars, index bars, industry bars, trading status, and trading calendar checks.
- Recent minute bars for the latest 1-5 trading days.
- High-timeliness events: LHB, announcements, earnings forecast, earnings express, repurchase, news, and lightweight broker report metadata refresh.
- Daily derived layers: technical features, news features, factor daily rows, stock scores, watchlist signals, and daily research reports.
- Feishu start, completion, and failure messages through OpenClaw.

The daily pipeline does not run full-market low-frequency structure jobs:

- Shareholder count full-market deep scan.
- Top 10 holder and top 10 float holder full-market deep scan.
- Main business composition full-market deep scan.
- Full-market research PDF download and PDF field extraction.

Those remain in monthly or quarterly schedules, with small topN/watchlist refreshes allowed when daily candidates need context.

## Frequency Policy

### Trading-Day Daily

Run after market close on trading days:

- Market daily refresh.
- Minute incremental refresh for recent trading days.
- LHB refresh.
- Announcement and major-event refresh.
- Earnings forecast and express refresh.
- Repurchase light refresh.
- Public news and news feature refresh.
- Lightweight research metadata refresh for topN/watchlist candidates.
- Technical features, factor daily, scores, watchlist signals, and daily reports.

### Weekly

Run during the weekend:

- Institution survey.
- Repurchase wider-window refresh.
- Shareholder trade / increase-decrease refresh.
- Weekly data quality and gap report.

### Monthly

Run on the first Saturday of each month:

- Shareholder count light sweep.
- Main business composition light sweep over recent reporting periods.
- Holder gap retry for known missing symbols and periods.

### Quarterly

Run after reporting seasons, around May, September, November, and late January:

- Top 10 holder.
- Top 10 float holder.
- Main business composition full recent-quarter sweep.
- Holder gap retry with full detail logging.

## Daily Job Order

The daily OpenClaw job should run these steps in order:

1. `market_daily_refresh`
   - Update daily market, index, industry, and trading-status data.
   - Verify latest common trade date.

2. `minute_incremental_refresh`
   - Update minute bars for the latest 1-5 trading days.
   - Use the existing minute watchdog for larger catch-up work.

3. `daily_event_refresh`
   - Run LHB over a recent rolling window.
   - Run announcements and major events once those ingestion paths are wired.
   - Run earnings forecast and express over a recent rolling window.
   - Run repurchase over a recent rolling window.
   - Run news and lightweight research metadata paths.

4. `daily_feature_build`
   - Build technical features.
   - Build news features.
   - Build factor daily rows.
   - Build stock scores.
   - Build watchlist daily signals.

5. `daily_report_delivery`
   - Generate daily research reports.
   - Send a concise Feishu completion report.

## Rolling Windows

Use rolling windows rather than full history in the daily job:

- Market daily: latest missing trade dates, with a 5-trading-day correction window.
- Minute bars: latest 1-5 trading days.
- LHB: latest 10 calendar days.
- Announcements and major events: latest 14 calendar days.
- Earnings forecast and express: latest 45 calendar days, extended to 90 calendar days in reporting seasons.
- Repurchase: latest 90 calendar days.
- News: latest 7 calendar days for daily features, with topN/watchlist source refresh as needed.
- Broker report metadata: topN/watchlist candidates only, latest 90 calendar days.

## Feishu Reporting Contract

Each daily run writes a local JSON summary and sends a Feishu message.

Start message:

- Job name.
- Trade date.
- Rolling windows.
- Enabled steps.
- Output directory.

Completion message:

- Step status table.
- Rows fetched, normalized, upserted, empty, and failed where available.
- Latest data date for minute and market layers.
- Factor rows and score rows.
- TopN and watchlist refresh status.
- Failure detail paths.
- One-line action recommendation.

Failure message:

- Failed step.
- Error summary.
- Log path.
- Retry command.

Feishu messages should be short enough to read on mobile. Detailed evidence remains in local output directories.

## OpenClaw Cron Contract

OpenClaw should schedule wrapper scripts rather than embedding pipeline logic in agent prompts. The cron job should:

- Run in an isolated session.
- Call a host script under `/Users/xiwei/stock_research/scripts`.
- Use `delivery.mode = "none"` for the job itself.
- Let the script send Feishu messages through `openclaw message send`.
- Keep `failureAlert` enabled for crashes before the script can send a report.

Recommended jobs:

- `stock-daily-data-pipeline`: trading days at 21:10 Asia/Shanghai.
- `stock-weekly-enrichment-refresh`: Sunday at 21:30 Asia/Shanghai.
- `stock-monthly-structure-refresh`: first Saturday at 22:00 Asia/Shanghai.
- `stock-quarterly-structure-refresh`: reporting-season Saturday at 22:30 Asia/Shanghai.

## Data Quality Gates

The daily pipeline is considered healthy when:

- Latest market daily date is current or the latest valid trading day.
- Minute refresh advanced or already covers the configured recent window.
- Event refreshes wrote summaries even when no new rows exist.
- Technical features and factor scores were generated for the target trade date.
- Watchlist/report steps produced artifacts.
- Feishu report was sent or a local send-failure log exists.

Partial failures are allowed for external data sources, but the report must show the failed source and retry path.

## Initial Implementation Boundary

The first implementation should build the orchestration/reporting shell and use existing CLI commands where available. Missing data-specific adapters should be represented as explicit skipped steps with a reason, not hidden inside a successful run.

Initial included steps:

- Market/daily incremental step through the existing daily incremental command when enabled.
- Minute incremental step through the existing minute backfill/watchdog command.
- Free enrichment daily events through existing `free-enrichment-backfill` datasets.
- Technical features and factor pipeline through existing CLI commands.
- Feishu start/completion/failure reporting through existing OpenClaw message sending.

Announcement ingestion and advanced capital-flow adapters can be added as separate steps once their storage paths are stable.
