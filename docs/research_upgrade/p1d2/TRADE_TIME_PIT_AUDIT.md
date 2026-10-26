# P1d.2 A3 — Trade-Time Point-in-Time Audit

## Information tiers

| Tier | Contents | May drive decisions at |
|---|---|---|
| `open` | preclose, prior-day data, calendar, rules, status known before the session | open-time orders |
| `intraday` | prices/volume already printed before the order | intraday orders (needs minute data) |
| `close` | full-day OHLC, close, high, low | close-time orders / next-day decisions |
| `ex_post` | anything derived from the completed day | reporting/conservative fill models only — never claimed as PIT |

## Fix applied (`tradeability.py`)

- `order_time="open"` no longer reads high/low/close to establish a
  one-way-lock classification. The full-day `ONE_WAY_LOCKED` verdict is only
  produced for close/intraday contexts.
- Result details now carry:
  - `information_tier` — which tier the decision used;
  - `ex_post_execution_assumption` — explicit True/False so a "full-day
    locked => no fill" model is labeled as an after-the-fact assumption,
    not PIT knowledge.
- `TOUCHED_INTRADAY_ONLY` / `CLOSE_AT_LIMIT` remain close-tier
  classifications; open-time callers get `NOT_LIMIT_UNVERIFIED` /
  `PCT_NEAR_LIMIT_UNVERIFIED` style uncertainty instead of certainty.

## Consumer timing audit

| Path | signal_time | order_time | PIT verdict |
|---|---|---|---|
| `vectorized_topn_backtest` | selection date close (scores of day T) | next session open | OK — open orders may use day-T scores; limit flags now gate with PIT flags |
| `retention_backtest` | selection date | next tradable open (`sell_bar_for_holding` rolls forward) | OK after flag join; `use_status_flags=True` adds limit-down roll-forward |
| `backtest.py` `apply_buy_filter` | selection date | next open | static `open >= preclose*1.095` heuristic kept as default; corrected `use_status_flags` path uses real PIT flags and fails closed on `limit_state_missing` |

## Tests

- `test_tradeability_p1d2.py::test_*open*` — open-order fixtures prove
  high/low/close values do not leak into open-tier decisions, and the
  ex-post label is set.
- Focused suite: 18/18 P1d.2 tests pass.
