# Operator Decision Write API v1 Implementation Plan

## Objective

Add a small direct dashboard POST API for writing local operator decisions while reusing the existing journal import storage model and Batch E snapshot linkage resolver.

## Constraints

- no automatic trading
- no broker integration
- no new strategy/factor/data-source work
- no large frontend or HomeCockpit changes
- no schema migration unless audit proves it is required
- no Strategy Command Center, Backtest Lab, or HomeCockpit conflict handling

## Audit Summary

- `ops.operator_decision_event` already has all storage columns needed for v1.
- `source_context` is text and already supports JSON payloads with snapshot linkage.
- `import_decision_journal` writes through `_upsert_session` and `_upsert_event`.
- `dashboard/decisions.py` already exposes snapshot linkage from `source_context`.
- Batch E resolver accepts explicit snapshot IDs, `run_id + digest_key`, and `run_id + asset_id`.
- No schema migration is needed.

## Steps

1. Add focused tests for the write service.
2. Implement `operator_decision/write_service.py`.
3. Add dashboard route `POST /api/operator-decisions`.
4. Add dashboard route tests for success and validation errors.
5. Add frontend request/response types and client method.
6. Add frontend client test.
7. Update `docs/dashboard-local-runbook.md` with POST/read-back smoke.
8. Run focused backend tests.
9. Run frontend client test.
10. Run dashboard build because frontend API files are touched.

## Verification Commands

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_operator_decision_write_service.py \
  tests/test_operator_decision_snapshot_linkage.py \
  tests/test_operator_decision_read_model.py \
  tests/test_dashboard_decisions.py \
  tests/test_dashboard_app.py \
  tests/test_review_evidence_snapshots.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py -q

cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
cd dashboard && pnpm build
```
