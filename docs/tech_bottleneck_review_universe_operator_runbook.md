# Tech Bottleneck Review Universe Operator Runbook

## Scope

The review workspace is a research-only manual review surface for the 378-stock tech bottleneck review universe.

- Page: <http://127.0.0.1:5174/research/tech-bottleneck/review-universe>
- API base: <http://127.0.0.1:8765>
- Decision storage: `outputs/research/tech_bottleneck_review_universe_manual_decision_overlay_v1/`
- The page does not generate frozen v6/v7, trading signals, admission changes, scoring changes, or strategy writes.

## Write Token

Writes use the existing dashboard write guard.

Backend environment:

```bash
export STOCK_RESEARCH_DASHBOARD_WRITE_GUARD=true
export STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN="<shared token>"
```

Browser setup:

```js
localStorage.setItem("dashboardWriteToken", "<shared token>")
```

If no token is configured in the browser, the page remains usable for reading evidence, but decision writes are rejected by the API. Invalid tokens are also rejected.

## Review Flow

1. Open the workspace page.
2. Use the filters or search box to select a stock.
3. Click `View evidence <stock_code>`.
4. Review the detail panel, including strongest claim, weakest/risky claim, evidence summary, page-level evidence, and source rows.
5. Apply the 8-point rubric.
6. Enter a `review_comment`.
7. Check `evidence_checked` only after reviewing the evidence/source rows.
8. Record one decision: `keep`, `hold`, `need_more_evidence`, `downgrade`, or `reject`.

## Rubric

1. hard-tech: whether the company is in a hard-tech critical segment.
2. bottleneck / chokepoint: whether it is a key upstream, equipment, material, process, certification, capacity, yield, or validation bottleneck.
3. business relevance: whether the exposure is core or important to the business, not a marginal concept.
4. primary source evidence: annual reports, announcements, prospectuses, exchange replies, official materials, projects, capacity, certification, or customer evidence.
5. page-level evidence: evidence rows must be page-level and inspectable.
6. value capture: whether the company can economically capture value from the bottleneck.
7. route-around / substitution risk: whether customers or competitors can bypass the bottleneck.
8. disconfirmation / pollution risk: concept pollution, low revenue contribution, unverifiable customers, or contrary evidence.

## Decision Semantics

- `keep`: hard-tech, bottleneck role, business relevance, primary-source support, and acceptable value/route-around risk.
- `hold`: plausible thesis, but supply-chain role, customer, revenue, or competition needs more human review.
- `need_more_evidence`: thesis remains possible, but key primary evidence is missing.
- `downgrade`: technically adjacent or beneficiary-like, not enough for the core bottleneck layer.
- `reject`: evidence does not support the thesis, business is irrelevant, pollution risk is high, or disconfirmation is strong.

Scores are sorting and priority hints only. They never create a decision automatically.

## Ledger And Corrections

Decision storage is append-only:

- New decisions do not delete old decisions.
- History remains visible in the detail panel.
- Current overlay uses the latest ledger entry for each `stock_code`.
- To correct a decision, submit a new decision for the same stock.
- There is no physical delete and no bulk rollback in this workflow.
- Audit reports count superseded/correction history.

## Export And Audit

Dry-run smoke:

```bash
python scripts/run_tech_bottleneck_review_universe_operator_smoke.py \
  --dry-run \
  --output-dir outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1/dry_run
```

Optional explicit write test:

```bash
python scripts/run_tech_bottleneck_review_universe_operator_smoke.py \
  --write-test-decision \
  --stock-code 000777 \
  --decision need_more_evidence \
  --comment "测试写入：需要补充一手证据，后续可由人工改判。" \
  --evidence-checked \
  --write-token "$STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN" \
  --output-dir outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1/write_test
```

Audit:

```bash
python scripts/run_tech_bottleneck_review_universe_decision_audit.py \
  --output-dir outputs/research/tech_bottleneck_review_universe_operator_smoke_and_audit_v1/audit
```

Overlay export:

```bash
python scripts/run_tech_bottleneck_review_universe_manual_decision_overlay.py
```

## Common Errors

- `missing_dashboard_write_token`: browser token is not configured.
- `invalid_dashboard_write_token`: browser token does not match `STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN`.
- `review_comment_required`: decision write requires a comment.
- `evidence_checked_required`: decision write requires evidence to be checked.
- `stock_not_in_review_universe`: stock code is not in the 378-stock review universe.
- `invalid_reviewer_decision`: decision is not one of the five allowed values.

## Guardrail Checks

Before operator use, confirm:

- `frozen_v7_generated=false`
- `used_for_signal_count=0`
- `used_for_admission_count=0`
- strategy file diff is empty
- frontend dataset hash is unchanged after smoke writes
- reviewed + pending equals 378
