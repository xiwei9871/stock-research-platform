# Internal Skill Fusion Template

This template defines how an LLMQuant-inspired workflow can become a local `stock_research` internal skill. It is not an external skill install format. It is a review artifact that keeps analyst workflows inside the existing data, evidence, and Agent boundaries.

## Purpose

State the review job in one sentence. The purpose must improve an existing `stock_research` workflow such as daily report review, watchlist review, risk review, position review, market regime review, or report delivery.

## Existing stock_research inputs

List concrete local inputs. Acceptable inputs include:

- Markdown, JSON, or CSV reports from `src/stock_research/reports/`.
- Run cards and evidence bundles from `run_card` outputs.
- Watchlist artifacts from `src/stock_research/watchlist/`.
- Operator/shadow review artifacts from `src/stock_research/operator_decision/`.
- Research, news, and stock report artifacts from `news_features`, `topn_news_enrichment`, `stock_report_research`, and `research_narrative`.
- Market regime and risk artifacts from `market_regime_confirmation_v1`, `market_style_switch_v1`, and `risk_alert_report`.

External context is allowed only when it has already been stored as a local artifact and labelled as `external_context`.

## Required evidence

Every conclusion must cite at least one local evidence reference with:

- `artifact_id`
- `evidence_type`
- `path`
- short summary

Missing evidence must be reported as a data gap, not filled with model inference.

## Allowed outputs

The output must be convertible into `AgentObservation`:

- `agent_role`
- `subject`
- `decision_label`
- `data_facts`
- `factor_results`
- `backtest_findings`
- `agent_reasoning`
- `unverified_hypotheses`
- `evidence`

Allowed `decision_label` values are the existing labels in `src/stock_research/agents/contracts.py`: `观察`, `候选`, `谨慎`, `剔除`.

## Forbidden outputs

The skill must not emit:

- direct trading instructions such as `必须买入`, `立即买入`, `直接买入`, `必须卖出`, `立即卖出`, `sell now`, `buy now`, `must buy`, or `all in`
- broker, order, account, cash, position, fill, or execution mutations
- production watchlist promotion
- dashboard state mutation
- claims that cannot be tied to local evidence
- external data conclusions that bypass local artifacts

## AgentObservation mapping

Map the skill result into the existing contract:

| Skill output | AgentObservation field |
| --- | --- |
| observed facts from local artifacts | `data_facts` |
| factor score, factor rank, exposure, or factor-card facts | `factor_results` |
| historical validation, backtest, retention, or outcome facts | `backtest_findings` |
| analyst interpretation over cited facts | `agent_reasoning` |
| ideas that need follow-up evidence | `unverified_hypotheses` |
| local file references | `evidence` |

Reasoning must not be mixed into `data_facts`.

## ReviewAgent checks

Before delivery, the output must pass `ReviewAgent`:

- valid mode
- valid agent role
- valid decision label
- at least one evidence reference
- data facts separated from reasoning
- no banned trading instruction

Rejected skill outputs are review artifacts only and must not enter report delivery.
