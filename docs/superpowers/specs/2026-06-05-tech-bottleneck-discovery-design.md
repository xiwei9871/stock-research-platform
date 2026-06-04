# tech-bottleneck-discovery Design

## Purpose

`tech-bottleneck-discovery` is a Serenity-inspired research enhancement layer for finding low-position hard-technology bottleneck opportunities. It is not a standalone trading system at launch. It sits on top of existing candidate pools and helps identify companies that may be underpriced because the market has not yet recognized their role in a critical technology supply-chain chokepoint.

The working thesis is:

> High-certainty technology trend + upstream chokepoint + hard-to-expand supply + market under-recognition + evidence-backed catalyst = candidate for deeper research.

The layer should improve research prioritization, not issue automatic buy or sell instructions.

## Source Interpretation

The method is derived from Serenity's public research pattern around AI and semiconductor supply-chain bottlenecks, cross-checked against public domestic and international summaries. The useful abstraction is not to copy Serenity's holdings, but to reuse the research sequence:

1. Start from a high-certainty technology demand.
2. Reverse-map the supply chain.
3. Identify physical, technical, capacity, qualification, or material bottlenecks.
4. Find listed companies with real exposure to those bottlenecks.
5. Check whether the market still prices the company as an old business, cyclical business, or ordinary component supplier.
6. Build a graded evidence matrix.
7. Define catalysts and invalidation conditions before promotion.

Reference material reviewed:

- Serenity / aleabitoreddit X profile and public posts: https://x.com/aleabitoreddit
- Reddit AXTI thesis: https://www.reddit.com/r/wallstreetbets/comments/1pyghud/the_entire_ai_buildout_google_nvda_msft_is/
- Serenity SIVE thread mirror: https://twiscan.com/en/x/aleabitoreddit/2054868760629272850
- TradingKey summary: https://www.tradingkey.com/zh-hans/analysis/stocks/us-stock/261935617-adam-xie
- Tiger Brokers summary: https://www.itiger.com/hans/news/2639068856
- Douyin Simon Lin public page discovered during research: https://www.douyin.com/shipin/7645880239406549030

## Scope

### In Scope

- Define a reusable research template for hard-technology chokepoint opportunities.
- Add a second-stage scoring lens over existing candidates.
- Produce a shadow research list and evidence packet for manual review.
- Track outcomes for 5, 10, 20, and 60 trading days.
- Preserve explicit thesis, evidence, catalyst, and invalidation fields for later review.

### Out of Scope

- No broker integration.
- No automatic production promotion.
- No automatic position sizing for real portfolios.
- No assumption that Serenity's historical holdings are valid current opportunities.
- No social-media-only stock promotion signal.

## Position In The Existing Platform

Initial placement should be an alpha lens, not a primary strategy.

```text
Existing candidate pools
-> liquidity / tradability / universe filters
-> trend, quality, industry, and risk scores
-> tech-bottleneck-discovery lens
-> shadow research candidates
-> human / LLM evidence packet
-> outcome tracking
```

This keeps the existing platform responsible for candidate generation, tradability, backtesting, and risk controls. `tech-bottleneck-discovery` focuses on identifying under-recognized hard-technology bottleneck exposure.

## Candidate Definition

A candidate is eligible when it plausibly satisfies all of the following:

1. It belongs to a high-certainty technology trend, such as AI infrastructure, semiconductors, photonics, advanced packaging, robotics, aerospace, precision equipment, industrial software, new materials, or localized substitution.
2. It is connected to an upstream or enabling supply-chain layer, not only to a popular downstream theme.
3. The relevant product, material, equipment, process, or qualification could become a chokepoint.
4. The company has enough direct exposure for the chokepoint to matter to revenue, margin, valuation, or strategic scarcity.
5. The market may still underprice the exposure because coverage, liquidity, narrative, or financial recognition is incomplete.
6. There is at least one credible evidence item beyond social media discussion.

## Core Modules

### 1. trend_map

Purpose: identify the high-certainty terminal demand.

Fields:

- `trend_name`
- `terminal_demand`
- `demand_driver`
- `evidence_strength`
- `demand_time_horizon`
- `key_downstream_players`
- `trend_uncertainty`

Examples of trend categories:

- AI compute and data-center infrastructure
- Semiconductor equipment and materials
- Photonics and optical interconnect
- Advanced packaging
- Industrial robotics
- Aerospace and defense materials
- High-end manufacturing equipment
- Domestic substitution of restricted technology

### 2. bottleneck_chain

Purpose: reverse-map the supply chain from terminal demand to upstream chokepoints.

Required chain:

```text
terminal demand
-> system / end product
-> module
-> component
-> material / equipment / process
-> bottleneck point
-> listed company exposure
```

Each chain item should record:

- `chain_level`
- `supply_chain_node`
- `why_it_matters`
- `key_suppliers`
- `substitution_options`
- `expansion_constraint`
- `candidate_companies`

### 3. chokepoint_score

Purpose: score whether the supply-chain node is truly a chokepoint.

Dimensions, each scored 0 to 5:

- `terminal_demand_certainty`
- `single_point_importance`
- `supply_concentration`
- `capacity_expansion_difficulty`
- `technical_barrier`
- `qualification_or_customer_switching_cost`
- `substitution_difficulty`
- `value_capture_power`

Interpretation:

- 0-15: weak chokepoint; reject unless other evidence is exceptional.
- 16-25: watch candidate.
- 26-32: deep research candidate.
- 33-40: high-priority bottleneck candidate.

### 4. underpricing_score

Purpose: identify low-position or under-recognized opportunities.

Dimensions, each scored 0 to 5:

- `market_cap_room`
- `low_sell_side_coverage`
- `low_institutional_attention`
- `old_business_mispricing`
- `new_business_not_in_numbers`
- `valuation_vs_peers`
- `price_not_overheated`
- `narrative_early_stage`

This score should penalize stocks that already have extreme short-term gains, crowded narratives, or valuation that assumes full success.

### 5. evidence_matrix

Purpose: prevent the strategy from becoming concept speculation.

Evidence tiers:

- Tier 1: company filings, annual reports, announcements, earnings calls, customer certifications, signed orders, capacity expansion, audited financial changes.
- Tier 2: hiring, patents, supplier/customer disclosures, government projects, industry conference materials, peer disclosures.
- Tier 3: social media, KOL summaries, unsourced channel checks, AI-generated inference.

Each evidence item should store:

- `evidence_tier`
- `source_type`
- `source_url_or_path`
- `source_date`
- `claim`
- `supports`
- `contradicts`
- `confidence`
- `freshness`

Minimum promotion rule:

- `watch`: one Tier 2 or better item.
- `research`: at least one Tier 1 item or two independent Tier 2 items.
- `probe`: at least two Tier 1 items, plus no unresolved fatal contradiction.
- `conviction_candidate`: multiple Tier 1 items, clear catalyst, defined invalidation, and acceptable valuation risk.

### 6. catalyst_calendar

Purpose: define what can force market recognition.

Catalyst types:

- earnings report
- order announcement
- customer certification
- capacity ramp
- new product release
- industry conference
- policy or export-control event
- index inclusion
- sell-side initiation
- peer read-through

Each catalyst should record:

- `catalyst_name`
- `expected_date_or_window`
- `expected_observable`
- `positive_confirmation`
- `negative_confirmation`
- `impact_level`

### 7. invalidation_rules

Purpose: make the thesis falsifiable before outcome tracking.

Common invalidation categories:

- terminal demand delayed or reduced
- technical route changes away from the candidate's product
- substitute supply emerges
- company fails qualification
- capacity ramp fails
- revenue exposure remains immaterial
- margin fails to improve
- dilution or balance-sheet risk dominates upside
- valuation fully prices the bull case
- liquidity or tradability becomes unacceptable

Each candidate must have at least three explicit invalidation conditions.

## Composite Research Score

The initial composite score should be transparent and manually auditable:

```text
tech_bottleneck_score =
  0.25 * trend_score
+ 0.25 * chokepoint_score
+ 0.20 * evidence_score
+ 0.15 * underpricing_score
+ 0.10 * catalyst_score
- 0.15 * risk_penalty
```

The first version should avoid overfitting. The score is a ranking and triage tool, not a trading signal.

## Candidate States

| State | Meaning |
| --- | --- |
| `reject` | Thesis is weak, evidence is poor, or risk dominates. |
| `watch` | Interesting chokepoint idea, evidence incomplete. |
| `research` | Chokepoint is plausible and evidence justifies deeper review. |
| `probe` | Evidence, valuation, and catalyst are strong enough for shadow tracking. |
| `conviction_candidate` | High-confidence research candidate for manual review, not automatic production approval. |
| `invalidated` | Thesis failed one or more predefined invalidation rules. |

## Research Packet Output

Each promoted candidate should output a markdown or structured JSON packet with:

- one-sentence thesis
- trend map
- supply-chain reverse map
- chokepoint score
- underpricing score
- evidence matrix
- market misconception statement
- catalyst calendar
- bear case
- invalidation rules
- valuation scenarios
- technical and liquidity context
- current candidate state
- next evidence to collect

The key summary sentence should follow:

```text
Market appears to price this company as ___, but the evidence suggests it may be ___ because ___.
```

## Outcome Tracking

The shadow lifecycle should track:

- `entry_research_date`
- `candidate_state`
- `score_snapshot`
- `price_snapshot`
- `market_cap_snapshot`
- 5 trading day return
- 10 trading day return
- 20 trading day return
- 60 trading day return
- max drawdown after entry
- catalyst hit or miss
- thesis upgraded, unchanged, downgraded, or invalidated
- reason for outcome classification

Outcome review should answer:

1. Did the score identify a real chokepoint?
2. Did the evidence matrix overstate weak evidence?
3. Was the candidate too early, timely, or already crowded?
4. Did technical confirmation improve or worsen results?
5. Which invalidation rule should have fired earlier?

## Manual Research Template

Use this short checklist before promoting any candidate:

1. What is the terminal demand?
2. What exact supply-chain node can become a bottleneck?
3. Why can supply not expand quickly?
4. Why is substitution difficult?
5. How directly does the company benefit?
6. What does the market currently misunderstand?
7. What Tier 1 or Tier 2 evidence supports the thesis?
8. What catalyst can make the market care?
9. What would prove the thesis wrong?
10. Is the stock still low-position enough for the risk?

## Automation Roadmap

### Phase 1: Research Layer

- Build a static scoring rubric and markdown research packet.
- Apply manually to selected existing candidates.
- Store packet outputs under research outputs.
- Track outcomes without affecting production watchlists.

### Phase 2: Candidate Scoring

- Add structured fields for trend, chokepoint, evidence, underpricing, catalyst, and invalidation.
- Compute `tech_bottleneck_score` for existing candidate pools.
- Generate top-ranked shadow candidates.
- Add tests around score construction and state transitions.

### Phase 3: Evidence Retrieval

- Connect filings, announcements, news, research reports, patents, hiring, and peer disclosures.
- Use LLM summarization only after source retrieval.
- Preserve citations and evidence tiers.
- Add contradiction detection and stale-evidence warnings.

### Phase 4: Review And Backtest

- Run historical and forward shadow analysis.
- Compare existing strategy candidates with and without the lens.
- Evaluate hit rate, drawdown, catalyst conversion, and false-positive rate.
- Decide whether the layer should remain a lens or become a standalone strategy.

## Risks

- The method can degrade into concept-stock chasing if evidence tiers are ignored.
- Low-position small-cap candidates can have liquidity and dilution risks.
- Social media summaries can overstate Serenity's process or success.
- Chokepoint logic can be correct while the listed company captures little value.
- The strategy may identify opportunities too early, causing long drawdowns before validation.
- Historical backtests may underrepresent unstructured evidence availability.

## Acceptance Criteria For The Design

- The layer is explicitly non-execution and non-production-promotion.
- It integrates with existing candidates before becoming standalone.
- Every promoted candidate has a trend map, chokepoint rationale, evidence matrix, catalyst, and invalidation rules.
- Weak evidence is clearly separated from primary evidence.
- Outcome tracking can later show whether the lens improves research quality.
