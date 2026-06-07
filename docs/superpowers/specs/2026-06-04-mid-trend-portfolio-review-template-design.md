# Mid Trend Portfolio Review Template Design

## 1. Objective

Define a reusable portfolio-review reporting template for the mid-trend strategy workflow.

The template is designed for:

- daily holding review;
- rebalance-day review;
- top-10 discussion support;
- manual decision support for a simulated portfolio.

The template is not a trading signal engine. It does not generate automatic execution instructions and does not override the strategy state by itself.

## 2. Core Requirements

The report must satisfy all of the following:

- use a single unified template family for both holding review and rebalance review;
- produce one portfolio-level report with per-stock subsections;
- cover `Top5` execution names with full analysis;
- cover `Top6-10` discussion names with short analysis;
- output `Markdown + CSV`;
- use only:
  - project-internal data;
  - project-generated public research-report summaries;
- exclude temporary external news and ad hoc web search results;
- ensure every judgment is traceable to explicit evidence.

## 3. Evidence Policy

### Allowed evidence

1. Strategy and watchlist state
- `mid_trend_watch_funnel_detail`
- `mid_trend_shadow_weekly_control_*`
- current holdings / rebalance diary / trades

2. Factor and technical evidence
- `mid_trend_funnel_score`
- score components
- trend / volatility / drawdown / return features already stored in project outputs

3. Regime and mainline evidence
- `market_regime_diagnostics.csv`
- `industry_mainline_regime_diagnostics.csv`
- enriched watch-funnel context fields

4. Research evidence
- `research.stock_report_feature_daily`
- PDF-extracted PIT fields
- project-generated public report metadata / summaries

5. Fundamental evidence
- PIT fundamental context already loaded into the project

### Disallowed evidence

- temporary one-off web search results;
- manual judgment without data reference;
- paid full-text report content;
- ex post reasoning that cannot be tied back to stored evidence.

## 4. Evidence Model

Every reportable conclusion must be derived from three layers.

### Layer 1: Raw evidence

Direct data fields or generated summaries.

Examples:

- `mid_trend_funnel_score = 84.73`
- `market_regime = mainline`
- `broker_report_count_90d = 3`
- `pdf_profit_forecast_count_90d = 2`
- `latest_pdf_risk_summary = "..."`

### Layer 2: Rule judgments

Structured interpretations derived from explicit rules.

Examples:

- `trend_structure = stable_trend_watch`
- `research_support_strength = moderate`
- `evidence_gap = report_coverage_missing`
- `holding_priority = high`

### Layer 3: Final conclusion

A short conclusion that must cite or be explainable by Layer 1 and Layer 2.

Examples:

- `high_priority_hold`
- `candidate_add`
- `candidate_remove`
- `discussion_only`

No Layer 3 conclusion may be written without supporting Layer 1 / Layer 2 evidence.

## 5. Output Artifacts

### Markdown

Suggested file:

- `outputs/research/mid_trend_portfolio_review_<trade_date>.md`

### CSV

Suggested file:

- `outputs/research/mid_trend_portfolio_review_<trade_date>.csv`

The CSV is the machine-readable audit table for all covered names.

## 6. Report Structure

The standard report contains one portfolio-level section followed by per-stock subsections.

### Section 1: Portfolio Summary

Required fields:

- `trade_date`
- `strategy_variant`
- `review_mode`
  - `holding_review`
  - `rebalance_review`
- `current_position_count`
- `top5_count`
- `top10_count`
- `rebalance_triggered`
- `buy_count`
- `sell_count`
- `turnover`
- `transaction_cost`

Required content:

- current holdings list;
- current top-10 candidate list;
- rebalance summary, if any;
- current regime and mainline summary;
- portfolio-level research coverage summary;
- portfolio-level risk summary;
- action conclusion.

### Section 2: Top5 Execution Pool

Five full subsections, one per stock.

### Section 3: Top6-10 Discussion Pool

Five short subsections, one per stock.

## 7. Final Label Set

All names must be assigned exactly one final label:

- `高优先级持有`
- `低优先级持有`
- `候选调入`
- `候选调出`
- `仅讨论`

The label is mandatory in both Markdown and CSV.

## 8. Top5 Full Template

Top5 full sections must use the following structure.

### 8.1 Identity

- `candidate_rank`
- `ts_code`
- `stock_name`
- `industry_name`
- `portfolio_role`
- `is_current_holding`
- `target_weight`

### 8.2 Strategy Evidence

- `mid_trend_funnel_score`
- `score_rank`
- `mid_trend_layer`
- `market_regime`
- `mainline_context`
- `mainline_status`
- `industry_mainline_score_v1`
- `ret_20_score`
- `ret_60_score`
- `trend_r2_20_score`
- `max_drawdown_20_score`
- `volatility_20_score`

### 8.3 Research Evidence

- `broker_report_count_90d`
- `research_support_score_pit`
- `target_price_median_pit`
- `target_upside_median_pit`
- `broker_coverage_count_pit`
- `pdf_target_price_count_90d`
- `pdf_target_price_high_confidence_count_90d`
- `pdf_profit_forecast_count_90d`
- `pdf_risk_section_count_90d`
- `latest_pdf_risk_summary`

### 8.4 Fundamental Evidence

- `fundamental_hard_risk`
- `fundamental_quality_note`

### 8.5 Rule Judgments

Required derived fields:

- `trend_signal_judgment`
- `mainline_judgment`
- `research_support_judgment`
- `risk_judgment`
- `evidence_completeness_judgment`

### 8.6 Human-Readable Conclusion

Required narrative lines:

- `why_in_portfolio`
- `why_hold_or_change`
- `main_positive_evidence`
- `main_risk_evidence`
- `missing_evidence`
- `next_checkpoints`
- `final_label`

This subsection is the only narrative part. All claims must be traceable to the prior structured fields.

## 9. Top6-10 Short Template

Top6-10 short sections must be narrower.

Required fields:

- `candidate_rank`
- `ts_code`
- `stock_name`
- `industry_name`
- `mid_trend_funnel_score`
- `mid_trend_layer`
- `market_regime`
- `mainline_status`
- `broker_report_count_90d`
- `research_support_score_pit`
- `pdf_target_price_count_90d`
- `pdf_profit_forecast_count_90d`
- `pdf_risk_section_count_90d`
- `fundamental_hard_risk`
- `discussion_reason`
- `final_label = 仅讨论`

The short section answers:

- why the stock is in Top10;
- why it did not enter Top5;
- why it still deserves discussion.

## 10. Portfolio-Level Summary Logic

The portfolio summary must include:

### Current holdings

- current `Top5` holdings by weight;
- whether each holding is unchanged / newly added / at risk.

### Rebalance summary

- buy names;
- sell names;
- direct reason for each buy and sell;
- whether the rebalance is a normal weekly rebalance or a discussion-worthy edge case.

### Research coverage summary

Minimum aggregate metrics:

- count of names with `broker_report_count_90d > 0`
- count of names with `pdf_target_price_count_90d > 0`
- count of names with `pdf_profit_forecast_count_90d > 0`
- count of names with `pdf_risk_section_count_90d > 0`
- names with the weakest research coverage

### Risk summary

Must identify:

- weakest holding by evidence quality;
- highest-risk holding by rule judgment;
- most discussion-worthy Top6-10 name.

## 11. CSV Schema

The CSV must be one row per stock, shared by Top5 and Top6-10.

Required identity fields:

- `report_id`
- `trade_date`
- `strategy_variant`
- `section`
  - `top5`
  - `top6_10`
- `candidate_rank`
- `asset_id`
- `ts_code`
- `stock_name`
- `industry_name`

Required portfolio-state fields:

- `portfolio_role`
- `is_current_holding`
- `is_new_buy`
- `is_candidate_sell`
- `target_weight`

Required evidence fields:

- all Top5 evidence fields listed above, with blanks allowed for non-applicable names.

Required judgment fields:

- `trend_signal_judgment`
- `mainline_judgment`
- `research_support_judgment`
- `risk_judgment`
- `evidence_completeness_judgment`
- `discussion_reason`
- `why_in_portfolio`
- `why_hold_or_change`
- `main_positive_evidence`
- `main_risk_evidence`
- `missing_evidence`
- `next_checkpoints`
- `final_label`

## 12. Label Rules

The initial label assignment should be rule-based.

### `高优先级持有`

Typical conditions:

- currently in Top5;
- no hard fundamental risk;
- trend and regime fields remain supportive;
- research coverage is at least non-zero or evidence gap is acceptable.

### `低优先级持有`

Typical conditions:

- currently held;
- strategy still keeps it;
- but evidence quality is weaker, or risk is rising, or research support is thin.

### `候选调入`

Typical conditions:

- not currently held;
- enters Top5 on this review date;
- has stronger strategy evidence than at least one current holding.

### `候选调出`

Typical conditions:

- currently held but exits Top5;
- or remains held only because of scheduling rules while evidence deteriorates.

### `仅讨论`

Typical conditions:

- in Top6-10 but not in Top5;
- or evidence is mixed and not ready for execution-pool status.

## 13. Generation Strategy

The intended generation flow is:

1. load current strategy state;
2. load current Top10 candidate state;
3. load PIT report features;
4. attach stored public-report summary evidence;
5. compute rule judgments;
6. assign final labels;
7. render Markdown;
8. write CSV.

The report generator must not fetch external web pages during report generation.

## 14. Non-Goals

The template does not:

- execute trades;
- update holdings automatically;
- use external one-off news searches;
- introduce new ranking logic;
- change strategy weights;
- override strategy ranking with human prose.

## 15. Recommended Implementation Boundary

Recommended new module:

- `src/stock_research/mid_trend_portfolio_review.py`

Responsibilities:

- consume strategy replay / current holdings / research artifacts;
- build review rows;
- render Markdown and CSV.

Existing modules should remain separate:

- `mid_trend_research_packet`: candidate research enrichment
- `stock_report_research`: report workpack construction
- `mid_trend_shadow_weekly_control`: strategy replay and holdings state

## 16. Validation Requirements

The implementation should be considered complete only if:

- the report renders for a holding-only day;
- the report renders for a rebalance day;
- Top5 rows use the full template;
- Top6-10 rows use the short template;
- every final label is populated;
- every narrative judgment can be traced to structured fields;
- CSV and Markdown remain consistent for the same report date.
