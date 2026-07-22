# Stock Workspace Latest-Date Contract

## Problem

The stock workspace currently reuses a handoff's `tradeDate` for two unrelated purposes:

1. selecting the review snapshot; and
2. setting the end date for daily, weekly, monthly, and intraday market data.

An ordinary navigation from an older review, news, report, or market-monitor item can therefore make every chart stop on the source item's historical date. It can also make the stock review appear historical without the operator explicitly entering replay mode.

## Product Contract

The platform has two independent date concepts.

### Market-data date

- The stock workspace always loads the latest platform-approved market-data date.
- Daily, weekly, monthly, and intraday charts all use that latest date.
- Source-workspace dates and historical review dates must never roll market data backward.
- The chart header and time-window metadata must expose the actual latest date returned by the API.

### Review date

- The stock workspace defaults to the latest platform-approved review date.
- A source item's date is provenance only; ordinary navigation must not activate historical review mode.
- Historical review data is loaded only after the operator explicitly selects and submits a past replay date.
- Leaving replay mode or opening another stock through ordinary navigation restores the latest review date.
- Historical review mode does not change the market-data date; charts remain current.

## Date Resolution

`AppShell` remains the authority for the platform display date. It passes that date to the stock workspace as the default for both current review data and current market data.

The stock handoff may still carry a source date for attribution and navigation context, but `StockWorkspace` must not use it as its active review or chart date. A separate explicit replay action may provide a historical review date after the workspace is mounted.

The workspace therefore maintains separate state:

- `marketDataEndDate`: initialized from the platform display date and used by all bar requests;
- `reviewTradeDate`: initialized from the platform display date and used by scores, signals, decisions, and review evidence;
- `sourceTradeDate`: optional provenance shown only where useful and never used as a data-query default.

## API and UI Behavior

- Profile requests use the latest review date and the latest market-data window by default.
- Resolution changes reuse the same latest `marketDataEndDate`.
- Explicit historical replay refreshes review-scoped data only.
- Loading and error states must not leave bars from the previous asset or previous date presented as current.
- Direct URLs containing a source `trade_date` retain the value as handoff provenance. They do not silently enter replay mode.
- If a future URL contract needs explicit replay, it must use an unambiguous replay parameter or user action rather than overloading source provenance.

## Verification

Unit and functional coverage must prove:

1. an old handoff date does not alter the default review date;
2. an old handoff date does not alter daily, weekly, monthly, or intraday request end dates;
3. changing resolutions preserves the latest market-data date;
4. explicit historical review replay changes review requests but not chart requests;
5. switching assets cannot let an older request overwrite the current asset;
6. Playwright checks the rendered chart cutoff and review date against the latest platform date during ordinary navigation;
7. Playwright checks that explicit historical replay changes only the review date.

## Non-goals

- Adding historical market-chart replay.
- Changing the platform display-date gate.
- Changing the strategy publication or review-queue publication contracts.
- Removing source-date provenance from navigation or evidence records.
