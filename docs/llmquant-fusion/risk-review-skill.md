# Risk Review Internal Skill

## Purpose

Review daily and shadow risk evidence, separate verified risk facts from interpretation, and produce a review-only Agent observation for human follow-up.

## Existing stock_research inputs

Use only local artifacts from:

- `src/stock_research/reports/risk_alert_report.py`
- daily market state reports under `reports/daily_research/market_state/`
- risk alert reports under `reports/daily_research/risk_alerts/`
- watchlist diagnostics from `src/stock_research/watchlist/diagnostics.py`
- watchlist risk split outputs from `src/stock_research/watchlist/risk_split.py`
- shadow outcome and follow-up artifacts from `src/stock_research/operator_decision/`
- run-card artifacts from the same research date, when available

External macro or market context can be used only if it already exists as a local artifact and is labelled `external_context`.

## Required evidence

Each risk finding must cite one or more:

- risk alert Markdown or JSON artifact
- market state Markdown or JSON artifact
- watchlist diagnostics artifact
- shadow review artifact
- run-card or evidence bundle artifact

If a risk claim lacks evidence, move it to `unverified_hypotheses`.

## Allowed outputs

Use `agent_role="risk"` and `mode="watchlist"` or `mode="topn"` depending on the reviewed artifact.

Recommended labels:

- `谨慎` for elevated verified risk requiring operator attention
- `剔除` for evidence-backed hard exclusion candidates
- `观察` for weak or incomplete risk evidence
- `候选` only when risk review finds no blocking concern and other evidence supports continued review

Output fields:

- `data_facts`: market state, risk alert, watchlist diagnostics, and shadow outcome facts
- `factor_results`: risk factor, exposure, drawdown, turnover, or concentration facts
- `backtest_findings`: historical outcome or shadow follow-up facts
- `agent_reasoning`: concise interpretation of the cited facts
- `unverified_hypotheses`: missing risk checks or follow-up questions
- `evidence`: local evidence references

## Forbidden outputs

Do not output:

- `必须买入`, `立即买入`, `直接买入`, `必须卖出`, `立即卖出`, `sell now`, `buy now`, `must buy`, `all in`
- order, account, cash, broker, position, or execution instructions
- automatic watchlist removal or promotion
- dashboard state changes
- risk claims without cited local evidence

## AgentObservation mapping

Risk facts from reports go into `data_facts`. Quantified risk scores, drawdowns, and exposures go into `factor_results`. Historical outcomes and shadow review outcomes go into `backtest_findings`. Analyst interpretation goes into `agent_reasoning`. Follow-up questions go into `unverified_hypotheses`.

## ReviewAgent checks

The final `AgentReport` must pass:

- `ReviewAgent().review(report).status == "passed"`
- no `missing_evidence` blocker
- no `missing_data_facts` blocker
- no `banned_trading_instruction` blocker
