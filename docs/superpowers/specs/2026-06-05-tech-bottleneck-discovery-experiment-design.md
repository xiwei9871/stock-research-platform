# tech-bottleneck-discovery Experiment Design

## Purpose

This spec defines how to use `tech-bottleneck-discovery` in the research workflow and how to test whether it improves existing candidate pools. The first experiments should not scan the full market. The lens should run after existing strategies have already produced candidates, then generate automated research packets for human review.

The core assumption is that Serenity-style technology bottleneck ideas are slow-variable theses. A 20 or 60 trading day result is useful for entry-quality diagnostics, but it is too short to judge whether the bottleneck thesis worked.

## Placement In Workflow

Use `tech-bottleneck-discovery` after candidate generation and before shadow review:

```text
existing candidate pool
-> liquidity / tradability / base risk filters
-> original strategy score
-> tech-bottleneck-discovery score
-> automated evidence packet
-> human review: approve / reject / needs-more-evidence
-> shadow tracking
-> outcome review
```

The lens answers:

> Which existing candidates are plausible hard-technology chokepoint opportunities with market under-recognition and evidence-backed catalysts?

It should not answer:

- What should we buy automatically?
- What should enter production watchlists automatically?
- Which stocks in the full market match a keyword theme?

## Candidate Pools For Phase 1

Start with existing, narrower pools where the base strategy has already found some signal:

1. `industry-focus` candidates
   - Best first pool because bottleneck research starts from a high-certainty trend and industry chain.
2. `mid-trend shadow top30`
   - Tests whether the lens can separate trend candidates with real industrial logic from price-only moves.
3. `strong-winner discovery pool`
   - Tests whether strong winners have durable chokepoint support or only short-term sentiment.

Do not start with all listed stocks. Full-market scanning should wait until the lens proves incremental value on existing candidates.

## Horizon Model

The evaluation must separate short-term diagnostics from thesis validation:

| Horizon | Role | Interpretation |
| --- | --- | --- |
| 20 trading days | Entry-quality diagnostic | Checks overheat, pullback risk, and immediate crowding. Not a success/failure horizon. |
| 60 trading days | Early recognition diagnostic | Checks whether market attention or relative strength begins to appear. Still not enough to judge the thesis. |
| 120 trading days | First main validation | Tests whether evidence-backed bottleneck names start outperforming base candidates. |
| 250 trading days | Core validation | Best primary horizon for a 6-12 month industrial re-rating thesis. |
| 500 trading days | Long-cycle validation | Tracks supercycle or capacity-ramp theses that need 1-2 years. |

The first experimental reports should lead with 120D and 250D. The 20D and 60D numbers should appear as diagnostics only.

## Experiment A: Historical Candidate Re-Scoring

### Goal

Test whether `tech-bottleneck-discovery` improves the quality of historical candidates produced by existing strategies.

### Input

Use historical candidate snapshots from:

- `industry-focus`
- `mid-trend shadow top30`
- `strong-winner discovery pool`

The first pass should use a bounded historical window with enough forward data for 250D results where available. For recent candidates without enough forward data, record them as partial-horizon observations instead of forcing conclusions.

### Method

For each historical candidate:

1. Preserve original strategy score and rank.
2. Generate or reconstruct `tech_bottleneck_score`.
3. Split candidates into high, medium, and low `tech_bottleneck_score` buckets.
4. Compare each bucket against the original candidate pool.
5. Track 20D, 60D, 120D, 250D, and 500D forward outcomes.

### Metrics

Primary:

- 120D excess return versus original candidate pool average.
- 250D excess return versus original candidate pool average.
- 120D and 250D max drawdown.
- 250D thesis retention rate.

Secondary:

- 20D and 60D overheat / early drawdown diagnostics.
- 500D long-cycle return where available.
- Win rate by horizon.
- Median return by horizon.
- False-positive rate for high-score names.

### Decision Rule

The lens is useful if high-score candidates show better 120D or 250D behavior than low-score candidates and the original candidate pool, without simply selecting high-volatility names.

## Experiment B: Forward Shadow A/B

### Goal

Test whether the lens improves forward review quality and candidate tracking in live research.

### Setup

Run weekly or twice weekly:

```text
base candidate pool top20 or top30
-> tech-bottleneck-discovery
-> top5 or top10 automated packets
-> human review
-> shadow tracking
```

Control group:

```text
base strategy top5 or top10 without the bottleneck lens
```

Experiment group:

```text
base strategy top20/top30 filtered to top5/top10 by tech_bottleneck_score
```

### Review Labels

Human review records only one of:

- `approve`
- `reject`
- `needs-more-evidence`

The system must preserve the generated evidence packet and reviewer reason.

### Metrics

Primary:

- Review reject rate.
- Needs-more-evidence rate.
- 120D and 250D return of approved names.
- 120D and 250D max drawdown of approved names.
- Thesis invalidation rate.

Secondary:

- 20D and 60D early crowding diagnostics.
- Time spent per review.
- Evidence sufficiency rate.
- Catalyst hit rate.

### Decision Rule

The lens is useful if it reduces low-quality review load, improves evidence clarity, and produces approved candidates with better 120D/250D outcomes than the control group.

## Experiment C: Component Ablation

### Goal

Identify which part of the score actually adds value.

### Components

Compare:

- `chokepoint_score`
- `underpricing_score`
- `evidence_score`
- `catalyst_score`
- `risk_penalty`
- full `tech_bottleneck_score`

### Questions

1. Does high `chokepoint_score` work without strong evidence?
2. Does `underpricing_score` select real opportunities or just weak small caps?
3. Does `evidence_score` reduce false positives?
4. Does `catalyst_score` improve 120D outcomes?
5. Does `risk_penalty` reduce drawdown without removing the best winners?

### Decision Rule

Keep the composite score only if the combined signal outperforms individual noisy components. If one component dominates, simplify the score.

## Reporting Format

Each experiment run should produce:

- run id
- candidate source
- trade date or snapshot date
- base strategy rank and score
- tech bottleneck component scores
- final `tech_bottleneck_score`
- generated research packet path
- review decision
- invalidation rules
- outcome rows by horizon
- summary by bucket

The report should explicitly separate:

- short-term diagnostics: 20D, 60D
- primary validation: 120D, 250D
- long-cycle observation: 500D

## Success Criteria

The first phase succeeds if:

1. The lens can run on existing candidate pools without full-market scanning.
2. Automated packets are clear enough that human review only needs approve, reject, or needs-more-evidence.
3. High-score candidates show better 120D or 250D behavior than low-score candidates.
4. The lens does not merely select high-beta concept stocks.
5. Failed candidates can be explained by predefined invalidation rules.

## Non-Goals

- No full-market scan in phase 1.
- No production watchlist promotion.
- No broker or trading action.
- No claim that 20D or 60D performance validates the strategy.
- No reliance on social-media-only evidence.

## Next Step

After approval, create an implementation plan for a historical re-scoring experiment runner that can load existing candidate snapshots, join future returns, bucket candidates by `tech_bottleneck_score`, and report 20D/60D diagnostics plus 120D/250D/500D validation.
