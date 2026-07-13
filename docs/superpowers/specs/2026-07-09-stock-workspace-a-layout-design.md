# Stock Workspace A Layout Design

Date: 2026-07-09

## Goal

Rebuild the stock workspace around normal stock-reading flow first, then layer tech-bottleneck review signals on top.

This page must serve two use cases at once:

1. Normal stock review: users first want to see quote, market cap, turnover, valuation, and chart behavior.
2. Tech-bottleneck review: users then want to understand thesis conclusion, confidence, evidence gap, and next action.

The current page overweights research plumbing, raw intermediate fields, and tall cards. The redesign should make the chosen frontend feel like the only canonical stock workspace in the product.

## Product Decisions

### 1. Primary reading order

The stock workspace will follow this order:

1. Stock identity and lightweight status
2. Quote + valuation + liquidity summary
3. Price chart
4. Tomorrow decision summary
5. Tech-bottleneck thesis summary
6. Company basics and business overview
7. Business composition and operating quality
8. Evidence and market context
9. Secondary tools and replay controls

Rationale:

- This matches common Chinese stock software mental models.
- Users can make a first-pass judgment before reading research overlays.
- Tech-bottleneck content becomes an enhancement layer rather than the visual owner of the page.

### 2. Desktop vs mobile behavior

Desktop 16:9:

- Quote summary and tomorrow decision share the first screen.
- Chart remains a full-width primary block immediately below.
- Thesis summary is compressed into a short metrics band.
- Research tools and replay settings are visually downgraded.

Mobile portrait:

- Quote summary comes first as a condensed metric card.
- Tomorrow decision follows immediately.
- Chart appears before thesis details.
- Thesis summary becomes an accordion-style compact card.
- Secondary tools remain collapsed by default.

### 3. Remove or demote non-user-facing content

These items should not occupy primary page space:

- Raw source workspace strings such as `Tech Bottleneck Candidate Review tech_bottleneck_review_universe_frontend_dataset_v1`
- Replay/change controls in expanded state
- Raw evidence intermediate fields
- Long report excerpts
- Machine summary strings such as `evidence=48; page_citations=18; sources=3`
- English operator phrases in the main reading path

These items may still exist as hidden metadata, tooling, or debug context, but not as default primary UI.

## Layout Structure

### Header

Keep:

- Stock name
- Canonical code
- Minimal status chips if they help explain current review state

Remove:

- Verbose source workspace banner
- Duplicate source dataset chip

Tooling:

- Move replay/change settings into a collapsed utility section or right-side utility trigger
- Keep it available for operator use, but hidden from default reading flow

### First screen

First screen should contain:

1. Quote/valuation/liquidity summary
2. Tomorrow decision summary
3. Price chart

Quote/valuation/liquidity summary should include:

- Last price
- Day change
- Open / high / low / previous close
- Volume / amount
- Turnover rate
- Amount ratio or volume ratio
- Total market cap
- Float market cap
- PE
- PB

If some values are unavailable, show `-` without inventing derived values.

Tomorrow decision summary should stay concise:

- Recommended next-day action
- One-sentence conclusion
- Confidence level

It should not repeat thesis internals or raw evidence detail.

### Thesis summary

The tech-bottleneck thesis section remains on page, but becomes a compact interpretation card.

Visible fields:

- Thesis conclusion
- Bottleneck confidence score
- Evidence quality score
- Evidence strength
- Current gap
- Suggested action
- Research priority

Default rules:

- No raw report excerpts
- No machine diagnostic strings
- No long English research text
- No duplicated explanation lines under gap/action

The section should visually read as a compressed summary strip, not a large standalone research page.

### Company and business blocks

Company basics and business overview come before evidence.

Business overview should show:

- Industry
- Exchange
- Board
- List date
- Region
- Status
- Clean business summary
- Core products

Raw report paragraphs should be filtered out unless a human-readable summary is unavailable and a later design explicitly chooses a “view source text” interaction.

### Business composition and operating quality

Business composition and operating quality should remain grouped together, but compressed.

Desktop:

- 60/40 split
- Left: composition list
- Right: operating quality metrics

Mobile:

- Stacked layout
- Composition first
- Quality metrics second

Composition behavior:

- Show top 4 items by default
- Support “expand more”
- Use compact rows instead of tall individual cards

Operating quality behavior:

- Use 2-column compact metric grid
- Reduce whitespace and panel height

### Evidence and market context

Evidence block and market context should move below company/business blocks.

Evidence summary must not conflict with thesis summary. If thesis says `充分`, evidence block must not independently label the stock as `Thin evidence` without an explicit scoped reason.

Required rule:

- The page must distinguish “strategy evidence digest bucket” from “tech-bottleneck evidence strength”

Presentation fix:

- Rename or scope evidence digest language so users understand it belongs to a different subsystem
- Example: `策略证据摘要` instead of generic `证据摘要`

Market context should remain as supplementary context, not compete with price and thesis.

## Data Semantics

The redesign requires explicit semantic separation between three concepts:

1. Tech-bottleneck thesis evidence strength
2. Strategy evidence digest bucket
3. Market-context evidence hit/miss

Current confusion comes from presenting all three as if they describe the same “evidence quality”.

Required UI rule:

- Every evidence-related block must state which subsystem it belongs to

Required product rule:

- If labels disagree, the page must make the disagreement understandable instead of hiding it behind one generic word like “evidence”

## Interaction Rules

### Keep available but collapsed

- Replay/change settings
- Secondary diagnostics
- Deep evidence links
- Operator-only utility content

### Keep always visible

- Quote summary
- Chart
- Tomorrow decision summary
- Compact thesis summary

### Expand on demand

- Full business composition
- Deep evidence details
- Tooling and replay controls

## Error Handling

- Missing data should render as `-` or clear Chinese fallback copy.
- No raw backend field names should leak into the page.
- No untranslated operator English should appear in primary user-facing blocks.
- Duplicate-key and duplicate-row scenarios must be deduplicated before rendering.
- If a human-readable summary is unavailable, prefer omission plus fallback copy over raw report paragraphs.

## Testing Requirements

Add or maintain tests for:

1. Replay/source utility content is demoted or collapsed by default
2. Thesis summary uses Chinese labels and no raw evidence strings
3. Company overview filters raw report excerpts
4. Business composition defaults to top 4 rows with expand/collapse
5. Duplicate search and peer rows do not emit React duplicate-key warnings
6. Quote section remains before thesis section in DOM order
7. Mobile layout stacks correctly at the chosen breakpoint
8. Evidence subsystem labels are scoped clearly enough to avoid thesis/evidence ambiguity

## Implementation Scope

In scope:

- Stock workspace information hierarchy
- Desktop/mobile layout changes
- Thesis summary compression
- Company/business block compression
- Replay/source demotion
- Evidence wording clarification

Out of scope for this design:

- Backend score recalculation logic
- Rebuilding research pipelines
- Replacing all tech-bottleneck review list column names across other pages
- Full visual redesign of the entire app shell

## Recommendation

Implement `A` as the canonical stock workspace pattern for the chosen frontend.

This should become the default stock page pattern for both ordinary stock review and tech-bottleneck stock review, with research-specific content layered in as a compact overlay rather than a competing page structure.
