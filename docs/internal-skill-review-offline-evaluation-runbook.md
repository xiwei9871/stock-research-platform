# Internal Skill Review Offline Evaluation Runbook

## Purpose

Evaluate whether internal skill review artifacts improve human review quality after daily report generation and before delivery.

## Boundary

This is offline-only:

- no external LLM calls
- no LLMQuant Data / MCP
- no OpenClaw or Feishu send
- no score, TopN, watchlist, dashboard, P17, P18, database, broker, order, account, cash, position, fill, or execution mutation

## Command

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-internal-skill-review \
  --trade-date YYYY-MM-DD \
  --artifact-path reports/daily_research/topn/daily_topn_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/risk_alerts/risk_alerts_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/market_state/market_state_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/position_review/position_review_YYYY-MM-DD.md \
  --artifact-path reports/run_card/YYYY-MM-DD/run_card.json \
  --output-dir outputs/internal_skill_review/YYYY-MM-DD
```

## Five-Day Evaluation

Run the command for five recent report dates with existing artifacts.

Record:

- review status
- ReviewAgent rejection count
- missing evidence count
- artifacts cited per observation
- minutes spent reviewing the original bundle
- minutes spent reviewing the internal skill artifact
- operator usefulness label: `useful`, `mixed`, `not_useful`
- hallucination or uncited-claim notes

## Acceptance for Promotion

The offline review can move to the next design step only if:

- no accepted artifact contains direct trading instructions
- every accepted observation cites evidence
- rejected artifacts clearly explain why they failed
- at least three of five reviewed days are labelled `useful` or `mixed`
- no score, watchlist, dashboard, delivery, or database state is mutated
