# Tech Bottleneck Discovery v0.1 Strategy Spec

## Definition

`tech-bottleneck-discovery` is the Serenity-inspired stock selection layer. It looks for low-position A-share companies mapped to hard technology bottleneck nodes, especially where domestic substitution, supply scarcity, customer validation, capacity expansion, or product revenue exposure can be supported by source evidence.

This is not a standalone trading system. In v0.1 it is used as the candidate pool / ranking layer, then combined with market-state exposure and single-stock protection.

## Baseline Composition

- Stock selection: `tech bottleneck discovery strict pool`, ST-only risk exclusion.
- Portfolio construction: weekly Top5 by bottleneck rank.
- Market exposure: `tight3b_bt100` market-state position sizing.
- Single-stock protection: `rank_exit_top10_1d`.
- Backtest window: `2025-01-01` to `2026-06-05`.
- Transaction cost: 20 bps.

## Candidate Field Template

Each candidate is audited on these method fields:

- `exact_bottleneck_node`: concrete product/process node where the company may be constrained or scarce.
- `revenue_exposure_bucket`: core revenue, meaningful segment, early ramp, or concept mapping.
- `customer_certification_stage`: certification, design-in, mass production, order/delivery, or not identified.
- `supplier_concentration_type`: import dependency, domestic substitution scarcity, market share, limited supplier count, or not established.
- `capacity_constraint_type`: capacity, yield, raw material, equipment, delivery cycle, or price signal.
- `substitution_difficulty_type`: process know-how, customer verification, reliability, yield curve, patent/technical barrier.
- `invalidation_category`: demand miss, customer validation failure, capacity oversupply, price erosion, technology route change, governance/financial risk.
- `financial_state_for_bottleneck`: financial context for review, not a hard exclusion in v0.1.
- `evidence_source_provenance`: every strong field should trace to a report, announcement, annual report, investor QA, or original source.

## Usage Rules

1. Use this layer before ranking/trading, not after trading signals.
2. Do not force every source-backed field to be `primary_strong`; weak or partial evidence stays as audit metadata.
3. ST exclusion is risk management. Financial pressure is review context, because bottleneck stocks may look weak before business inflection.
4. Do not use one-off famous winners to tune fields directly. Improvements should be chain-level or evidence-level.
5. The strategy is usable as v0.1 only with weekly Top5 and `rank_exit_top10_1d`; other top-N or rebalance settings are robustness variants, not the baseline.

## Current Baseline Metrics

- Total return: 214.36%
- Annualized return: 132.55%
- Max drawdown: -17.85%
- Sharpe: 3.11
- Average exposure: 75.58%
- Average holdings: 4.70
- Average turnover/day: 8.48%
