# LHB Shortline Strategy Development Summary

Date: 2026-06-09

## Objective

The LHB shortline work is scoped to two decision aids:

- Build an observable stock pool after a daily LHB signal.
- Provide tradable retreat signals after entry.

The system does not automate order placement. Backtests are used to validate whether the signal logic is useful under A-share T+1 constraints.

## Strategy View

The current design treats LHB as an emotion and capital-flow event, not as a low-risk value signal. Risk filtering is therefore not meant to remove every volatile candidate. For shortline LHB, a high opening gap is not automatically bad: many successful LHB trades are high-chase trades that rely on follow-on limit-up behavior or short trend continuation.

The core question is:

- Can the stock still be followed after the LHB signal?
- If followed, is capital still strengthening or has the emotion cycle faded?

## Data Layers

The strategy now uses four layers of data:

- Daily LHB features as the primary pool source.
- Daily K-line and limit-up lifecycle features for candidate structure and event context.
- 5-minute intraday bars for tradable dynamic entry and exit replay.
- Tushare auction bars for opening and closing call auction behavior.

The latest auction work stores downloaded auction data in database tables to avoid repeated vendor calls. Early experiments intentionally focused on the already selected LHB candidate set instead of full-market auction ingestion.

## Entry Logic

The tested entry path is dynamic rather than fixed close/open buying:

- T day: LHB daily signal forms the candidate pool.
- T+1: opening auction and 5-minute bars confirm whether the candidate is followable.
- Candidate ranking can be enhanced with auction behavior, but high gap alone is not a rejection rule.

Phase18C showed that auction-enhanced reranking improved capital efficiency for smaller TopN selections, especially Top3 and Top5.

## Exit Logic

The strategy no longer treats fixed holding windows as the target exit model. Earlier fixed 2d/3d/5d exits were useful only as diagnostics. The current model emphasizes dynamic retreat:

- Limit-up lifecycle failure.
- Weak opening confirmation.
- Closing auction weakness combined with weak open context.
- 5-minute tradable replay under T+1 rules.

Phase18F converts Phase18E daily/auction diagnostics into tradable 5-minute exits. It does not allow same-day sell after entry, and it only allows an earlier same-day replacement when the replacement 5-minute exit is earlier than the original exit on a legally sellable date.

## Phase Map

- Phase6-9: Built the initial LHB shortline design, pool construction, follow/exit framing, and early daily-feature evaluation.
- Phase10-12: Switched from overly sparse signal rules to full-market LHB daily features as the pool source, then added multi-context decision logic.
- Phase12A: Added pre-signal and signal-day context review so T/T-1/T-2 behavior can influence followability.
- Phase13-15: Built real-entry and cash-account style backtests, including TopN portfolio comparisons and limit-lock constraints.
- Phase16: Diagnosed quality issues. A key finding was that some forced lifecycle exits sold too early, especially around failed limit-break cases that still had strong 5d follow-through.
- Phase16D: Shifted from fixed holding windows toward exit indicators.
- Phase18: Added opening call auction data and tested it jointly with existing LHB features.
- Phase18C: Tested auction-enhanced TopN reranking in a cash-account replay.
- Phase18D: Added closing call auction lifecycle diagnostics.
- Phase18E: Tested joint open/close auction exit diagnostics. Closing auction was useful only when combined with other context.
- Phase18F: Converted joint diagnostics into tradable T+1 5-minute exit replay.

## Empirical Notes

Phase18B future 5d TopN comparison:

- Top3 baseline: win rate 42.08%, average return +1.94%.
- Top3 auction enhanced: win rate 61.32%, average return +8.94%.
- Top5 baseline: win rate 43.73%, average return +2.10%.
- Top5 auction enhanced: win rate 54.99%, average return +6.84%.

Phase18C cash-account replay:

- Top3 baseline final equity 1.7428; enhanced final equity 4.0689.
- Top5 baseline final equity 2.2906; enhanced final equity 4.8697.
- Top10 was mostly unchanged because the candidate set itself already covered the daily Top10 bucket.

Phase18D close auction diagnostics:

- Persistent positive close auction remained constructive.
- Mixed close auction was weaker.
- A close-auction smash was not automatically bearish; it needed joint interpretation.

Phase18E joint exit diagnostics:

- Weak open plus non-strong close-auction lifecycle was more stable than any single close-auction factor.
- Strong-hold style filters had better quality but filtered out too many trades, so they are diagnostic upper bounds rather than direct production rules.

Phase18F tradable replay:

- Priority next-open 5-minute exits gave small but stable improvements across Top3/Top5/Top10.
- Next 30-minute VWAP exits were not clearly better.
- The current replay adjusts realized exits but does not yet reallocate freed cash into new same-period opportunities.

## Current Conclusion

The most useful current direction is not to reject high-gap LHB stocks. The better path is:

- Keep LHB daily features as the pool source.
- Use opening auction and early 5-minute bars to decide whether a high-emotion candidate is still followable.
- Use closing auction plus weak-open context to detect retreat.
- Keep exit replay under T+1 and 5-minute tradability constraints.

The next improvement should focus on reducing low-quality entries and avoiding wrong early exits, but without turning the strategy into a low-volatility filter that removes the emotional stocks the strategy is designed to capture.
