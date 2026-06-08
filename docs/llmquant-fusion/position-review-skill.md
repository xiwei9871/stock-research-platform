# Position Review Internal Skill

## Purpose

Summarize position and virtual-portfolio review evidence for human review, with explicit risk, exposure, and market-regime context.

## Existing stock_research inputs

Use only local artifacts from:

- position review reports from `src/stock_research/reports/position_review_report.py`
- virtual portfolio outputs from `src/stock_research/simulation/virtual_portfolio.py`
- portfolio simulations from `src/stock_research/simulation/portfolio.py`
- sector strength reports from `src/stock_research/reports/sector_strength_report.py`
- market state reports from `src/stock_research/reports/market_state_report.py`
- risk alert reports from `src/stock_research/reports/risk_alert_report.py`
- market regime artifacts from `market_regime_confirmation_v1` and `market_style_switch_v1`
- run-card artifacts for the reviewed date

## Required evidence

Each position review must cite:

- a position review or virtual portfolio artifact
- at least one risk, sector, or market regime artifact
- run-card or evidence bundle when available

If position details are missing, the output must label this as incomplete position evidence.

## Allowed outputs

Use `agent_role="risk"` for risk-first position review or `agent_role="review"` for general review. Use `mode="watchlist"` unless the source artifact is a TopN-only review.

Recommended labels:

- `谨慎` for concentration, drawdown, exposure, or regime risks
- `观察` for incomplete or neutral review evidence
- `候选` for positions or virtual positions that remain review-worthy after risk checks
- `剔除` only when local evidence supports exclusion from further review

Output fields:

- `data_facts`: position, virtual portfolio, sector, market state, and risk alert facts
- `factor_results`: exposure, sector strength, risk score, or regime factor facts
- `backtest_findings`: portfolio simulation, retention, or outcome review facts
- `agent_reasoning`: interpretation of cited risk and exposure facts
- `unverified_hypotheses`: unresolved position, regime, or exposure questions
- `evidence`: local artifact references

## Forbidden outputs

Do not output:

- `必须买入`, `立即买入`, `直接买入`, `必须卖出`, `立即卖出`, `sell now`, `buy now`, `must buy`, `all in`
- order sizing, broker action, cash mutation, account mutation, or execution instruction
- automatic position mutation
- dashboard state changes
- unverified assumptions about current holdings

## AgentObservation mapping

Position and market facts go into `data_facts`. Exposure and regime facts go into `factor_results`. Simulation and outcome facts go into `backtest_findings`. Review interpretation goes into `agent_reasoning`. Missing position details and follow-up questions go into `unverified_hypotheses`.

## ReviewAgent checks

The final `AgentReport` must pass:

- valid `risk` or `review` role
- valid decision label
- at least one evidence reference
- data facts separated from reasoning
- no banned trading instruction
