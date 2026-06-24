# Mid Trend Round 2 Optimization Protocol

## Objective

Design the second-round optimization protocol for `current_mid_trend_strategy_v1` without drifting into sample-fitting.

This protocol is not a direct rule change proposal. It defines:

- what optimization is allowed to target
- how in-sample and out-of-sample evidence must be separated
- which failure modes are eligible for intervention
- how candidate rules are screened, retained, or rejected
- what artifacts must be produced before any optimized version can be treated as credible

## Strategy Context

The current `Mid Trend` diagnosis already shows that the main weakness is not discovery quality alone.

The strategy can identify future winners, but it mainly holds only a narrow subset of them:

- smooth path
- stable rank
- stable layer membership
- low short-term disruption

The dominant failure is not "cannot find good stocks". It is "cannot hold good stocks when the path becomes noisy".

That means Round 2 must optimize the holding expression of the strategy, not just seek a better historical return curve.

## Optimization Goal Hierarchy

Round 2 must use the following objective hierarchy:

### Primary Goal

`Hold winners longer`

This must be measured through:

- reduction in clearly identifiable winner-loss events
- reduction in post-exit continuation among false exits
- longer holding duration for genuine winners
- later separation between successful-winner paths and sold-winner paths

### Secondary Goal

`Reduce low-value turnover`

This must be measured through:

- lower turnover caused by mild rank noise
- lower same-industry low-value rotation
- fewer cases where a stock is sold and quickly re-enters candidate or holding state
- lower replacement activity that does not improve outcome quality

### Hard Constraint

`Do not materially worsen out-of-sample drawdown or stability`

This must be checked through:

- max drawdown
- monthly win rate
- return/drawdown quality
- evidence that improvements are not merely caused by much lower exposure or much lower participation

## Data Split

The protocol must use this fixed split:

- In-sample optimization window: `2025-01-01` to `2026-02-01`
- Out-of-sample validation window: `2026-02-01` to current effective end date

This split is fixed for the entire Round 2 process.

No candidate rule is allowed to use out-of-sample behavior to shape its design.

## What This Round Is Not Allowed To Do

Round 2 explicitly forbids the following:

- optimizing directly for highest in-sample total return
- large blind parameter sweeps without first defining failure-mode intent
- stacking multiple rules before single-rule marginal value is known
- treating lower exposure as equivalent to better rule quality
- changing the audit definition mid-process
- keeping a rule only because it "looks better historically"

The protocol is about rule quality improvement, not historical cosmetology.

## Fixed Failure-Mode Taxonomy

Candidate interventions must map to one or more of these failure modes.

### 1. Stable -> Lower Layer Rank Collapse

Definition:

- the stock starts in `stable_trend_watch`
- later downgrades into a lower trend layer
- then loses rank and is sold or displaced

Interpretation:

- the winner may still be valid
- the strategy is intolerant to a dirtier path

### 2. Stable -> Risk Exclusion Cliff

Definition:

- the stock starts in `stable_trend_watch`
- then is pushed into `risk_exclusion_watch`
- rank and holdability collapse together

Interpretation:

- the strategy may be over-interpreting temporary instability as full invalidation

### 3. Allocation Trim While Still Top Rank

Definition:

- the stock is still front-ranked on the decision date
- but is reduced or removed because of exposure scaling or rebalance budget logic

Interpretation:

- the individual stock thesis is not the main issue
- the portfolio layer cuts strength mechanically

### 4. Top Rank Fallout Other

Definition:

- a front-ranked stock drops out and is sold
- but the path does not cleanly belong to the first three structured classes

Interpretation:

- residual bucket kept for discipline
- may later be subdivided if enough evidence accumulates

### 5. Successful Winner Hold

Definition:

- genuine winner paths that the strategy actually holds successfully

Interpretation:

- not a failure bucket
- the required control sample for all interventions

No candidate rule may be evaluated without reference to how it affects this control class.

## Allowed Candidate Rule Families

Round 2 should only explore a small set of theory-backed rule families.

### Rule Family A: Stable-Layer Downgrade Buffer

Target failure mode:

- `Stable -> Lower Layer Rank Collapse`

Intent:

- avoid immediate loss of holdability when a stock leaves `stable_trend_watch`
- allow a short observation buffer before replacement

Required test:

- does this reduce winner-loss events without preserving genuinely deteriorating names too long?

### Rule Family B: Risk-Exclusion Reconfirmation

Target failure mode:

- `Stable -> Risk Exclusion Cliff`

Intent:

- require stronger reconfirmation before full exclusion
- distinguish temporary stress from true invalidation

Required test:

- does this improve winner retention without simply weakening risk control?

### Rule Family C: Strong-Name Trim Protection

Target failure mode:

- `Allocation Trim While Still Top Rank`

Intent:

- when total exposure must shrink, avoid mechanically trimming the strongest names first

Required test:

- does this reduce needless cuts to front-ranked holdings without violating exposure discipline?

### Rule Family D: Same-Industry Rotation Suppression

Target failure mode:

- low-value turnover

Intent:

- reduce switches where the strategy sells one name and buys another nearby name in the same industry/mainline without clear value improvement

Required test:

- does this reduce churn without suppressing legitimate within-theme upgrading?

### Rule Family E: Hold-Incumbent Priority Over Mild Rank Noise

Target failure mode:

- front-ranked incumbents displaced by small rank perturbations

Intent:

- require stronger evidence before replacing a strong incumbent
- raise the replacement bar relative to new entrants

Required test:

- does this reduce noisy turnover without making the book inert?

No other rule families should be added in Round 2 unless a new failure mode is explicitly documented first.

## In-Sample Screening Workflow

Round 2 must use the following sequence.

### Stage 1: Freeze Baseline

Before testing any candidate rule:

- freeze the current base strategy definition
- freeze the replay-audit logic
- freeze the winner / false-exit / turnover diagnostics
- freeze the in-sample and out-of-sample windows

Every candidate rule must be compared against this same baseline.

### Stage 2: Single-Family In-Sample Screening

Each candidate rule must be tested alone first.

In-sample evaluation must be organized into three buckets:

#### A. Primary-goal improvement

- fewer sold winners
- smaller post-exit continuation among false exits
- longer genuine-winner holding spans

#### B. Secondary-goal improvement

- lower turnover
- lower same-industry low-value rotation
- fewer fast re-entry cases

#### C. Side effects

- drawdown worsening
- monthly win-rate worsening
- fake stability caused by sharply lower exposure

Each candidate receives only one of three in-sample outcomes:

- `promote to out-of-sample`
- `reject: insufficient value`
- `reject: harmful side effects`

### Stage 3: Out-of-Sample Validation

Only candidates that pass Stage 2 may enter out-of-sample validation.

Out-of-sample evaluation does not seek the highest return.
It asks:

- does the same failure-mode improvement persist?
- does low-value turnover improvement persist?
- does drawdown/stability remain acceptable?
- is the improvement visible across multiple months, not just one cluster?

The only valid out-of-sample outcomes are:

- `pass`
- `fail`

There is no "borderline pass" category.

### Stage 4: Limited Combination Test

Only after single-rule candidates pass out-of-sample may limited combinations be tested.

Combination rules:

- combine primary-goal families first
- add at most one secondary-goal family at a time
- never evaluate a large stacked bundle first

Purpose:

- preserve interpretability
- preserve marginal attribution
- avoid accidental overfitting through complexity

## Final Deliverables

Round 2 must output the following artifacts.

### 1. Baseline Diagnostic Pack

- frozen baseline metrics
- baseline sold-winner set
- baseline successful-winner set
- baseline low-value turnover set

### 2. Candidate Rule Audit Table

For every candidate:

- rule family
- targeted failure mode
- in-sample changes
- out-of-sample changes
- side effects
- final keep/reject decision

### 3. Out-of-Sample Validation Table

At minimum:

- sold-winner count delta
- post-exit continuation delta
- low-value turnover delta
- turnover delta
- max drawdown delta
- monthly win-rate delta
- return/drawdown quality delta
- final decision

### 4. Final Retained Rule Set

For each retained rule:

- why it was kept
- what failure mode it improves
- what side effects remain acceptable

### 5. Unresolved Questions List

Round 2 must also explicitly list:

- which problems improved
- which problems remain
- which problems should not be attacked with another small rule tweak

## Rejection Rules

A candidate rule must be rejected if any of the following hold:

- it improves in-sample but does not replicate out-of-sample
- it reduces sold winners but does not reduce low-value turnover, or worsens it
- it improves winner retention only by materially worsening out-of-sample drawdown
- it looks better only because exposure or participation collapses
- it has no defensible mechanism beyond historical fit
- it only looks useful when hidden inside a larger stacked bundle

## Retention Rules

A candidate rule may proceed only if:

- it improves the intended failure mode in-sample
- it preserves same-direction improvement out-of-sample
- it does not clearly violate the drawdown/stability hard constraint
- it has an understandable mechanism
- its marginal contribution can be explained in isolation

## Final Research Question

Round 2 is not trying to answer:

- "How do we maximize historical return?"

It is trying to answer:

- "How do we keep the strategy from giving up valid winners too early, while reducing low-value turnover and preserving out-of-sample stability?"
