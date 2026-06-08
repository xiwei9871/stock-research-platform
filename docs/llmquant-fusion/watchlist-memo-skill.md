# Watchlist Memo Internal Skill

## Purpose

Convert TopN, watchlist, factor, news, and stock report artifacts into a review-only watchlist memo that supports human candidate review without changing scores or promotions.

## Existing stock_research inputs

Use only local artifacts from:

- daily TopN reports under `reports/daily_research/topn/`
- daily report bundles under `reports/daily_research/daily/`
- factor reports and factor evaluation outputs from `src/stock_research/factor_eval/`
- watchlist workflow outputs from `src/stock_research/watchlist/workflow.py`
- watchlist signals from `src/stock_research/watchlist/signals.py`
- news enrichment from `src/stock_research/topn_news_enrichment.py`
- public news features from `src/stock_research/news_features.py`
- stock report research artifacts from `src/stock_research/stock_report_research.py`
- research narrative artifacts from `src/stock_research/research_narrative.py`
- run-card artifacts for the reviewed date

## Required evidence

Each memo must cite at least one local artifact. Stronger memos should cite:

- TopN or watchlist source artifact
- factor score or factor evaluation artifact
- news or stock report artifact, if available
- run-card or evidence bundle artifact

Missing news or missing stock report coverage must be labelled as missing coverage, not negative evidence.

## Allowed outputs

Use `agent_role="watchlist"` and `mode="watchlist"`.

Recommended labels:

- `候选` for evidence-backed candidates that deserve human review
- `观察` for incomplete but non-blocking evidence
- `谨慎` for candidates with verified risk concerns
- `剔除` for evidence-backed hard exclusions

Output fields:

- `data_facts`: TopN rank, watchlist membership, report coverage, news coverage, and asset identifiers
- `factor_results`: factor scores, ranks, exposures, or factor-card summaries
- `backtest_findings`: retention, TopN, shadow outcome, or historical review facts
- `agent_reasoning`: thesis-quality interpretation of cited facts
- `unverified_hypotheses`: follow-up research questions
- `evidence`: local artifact references

## Forbidden outputs

Do not output:

- `必须买入`, `立即买入`, `直接买入`, `必须卖出`, `立即卖出`, `sell now`, `buy now`, `must buy`, `all in`
- automatic production watchlist promotion
- replacement of factor score, TopN rank, or watchlist rule output
- order, broker, account, cash, position, fill, or execution mutation
- uncited claims about catalysts, fundamentals, risks, or market regime

## AgentObservation mapping

TopN and watchlist facts go into `data_facts`. Factor and exposure facts go into `factor_results`. Historical validation and outcome facts go into `backtest_findings`. Memo interpretation goes into `agent_reasoning`. Research questions and missing-source notes go into `unverified_hypotheses`.

## ReviewAgent checks

The final `AgentReport` must pass:

- valid `watchlist` role
- valid decision label
- at least one evidence reference
- data facts separated from reasoning
- no banned trading instruction
