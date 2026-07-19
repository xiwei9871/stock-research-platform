# LHB Stable Publish Guardrails Design

## Goal

Prevent a legacy LHB execution path from replacing the official Stable Safe Top5 result, even when an older branch or process is run. An invalid result must fail closed, leave the last known-good product state intact, and produce an actionable failure record.

## Scope

This design covers the official `lhb_shortline` EOD publication path, its strategy contract, `ops.data_run_manifest`, the dashboard read path, and a frozen replay acceptance check. It does not remove experimental market-regime code or change the Stable Safe Top5 trading rules.

## Official Identity

The official LHB summary identity is immutable unless a separately reviewed strategy promotion changes it:

```text
strategy_version = lhb_v1_stable_safe_top5
selection_policy = phase18c_top5_then_eligibility_no_refill
market_regime_policy = disabled_for_stable_strategy
```

The repository will expose this identity from one shared module. Application validation, database migration SQL, tests, and replay checks must derive their expected values from that definition rather than maintaining unrelated copies.

## Architecture

### 1. Application contract gate

`StrategyContract` will include required summary identity fields. `validate_strategy_summary_against_contract` will compare every required identity field in addition to engine, variant, TopN, cost, frequency, and adjustment type.

The EOD publisher will validate a strategy result before creating or replacing any official artifact. An invalid LHB summary raises a contract error, creates a failed manifest entry where the existing orchestration already records failures, and does not write official LHB files.

The dashboard remains fail closed. A manifest with an invalid identity is exposed as `contract_mismatch`; its performance values are not used as official metrics.

### 2. Versioned publication

Each successful strategy publication writes its primary artifacts to a unique directory beneath the trade-date output directory:

```text
strategy_daily_eod/<trade-date>/strategy_runs/<module>/<publish-id>/
```

The publish ID combines the run ID and publication timestamp so a retry never mutates a previously published directory. The manifest `artifact_path` and metadata paths point only to this versioned directory.

Existing root-level files remain compatibility mirrors. They are written only after contract validation. They are not the product source of truth and are never referenced by a newly published manifest. Therefore an old process that overwrites a compatibility file cannot alter the dashboard result selected by the current manifest.

### 3. Database enforcement

`apply_data_run_manifest_schema` will install an idempotent PostgreSQL trigger on `ops.data_run_manifest`. For a row where:

```text
module = strategy_lhb_shortline
status = success
```

the trigger requires the three official identity values under `metadata.summary`. Missing or different values raise an exception and reject the insert or update.

The trigger applies only to new inserts and updates. Historical rows remain readable. The current correct 2026-07-17 manifest will be republished after migration so its artifact paths point to a versioned directory.

The migration will first be covered by SQL-generation tests and a PostgreSQL integration test. It will then be applied to the current `research` service, followed by a direct negative-write check inside a transaction that is rolled back.

### 4. Frozen replay acceptance

A dedicated validation command will run the official LHB configuration for 2026-01-01 through the frozen baseline end date and compare the summary with the approved reference:

```text
total_return = 0.918648063982811
max_drawdown = -0.042355025316131334
filled_trade_count = 186
cash_slot_count = 45
```

It also requires the official identity and the existing safety invariants: Phase18C ranks do not exceed five, no ineligible row enters the account, research-only rows do not appear in selected trades, and rank six is never promoted.

The command exits non-zero on any mismatch. Updating the approved reference requires an explicit code and fixture change; daily publishing never updates it automatically.

### 5. Runtime verification and alerting

The EOD summary records contract validation status and versioned artifact paths. The existing dashboard contract-mismatch state remains the user-visible fallback for invalid manifests.

Post-publication verification requests the same `/api/backtests/strategies` endpoint used by the 5174 application and requires:

- `contract_status = success`
- the three official identity fields
- performance date equal to the requested trade date

Return values are not used as the primary identity gate. A large day-over-day cumulative-return change can be reported as an operational warning, but cannot substitute for contract validation.

## Failure Behaviour

- Invalid application summary: no official artifact write; publication fails.
- Invalid database manifest: PostgreSQL rejects the write; previous successful manifest remains current.
- Artifact write failure: no manifest points to the incomplete versioned directory.
- Compatibility mirror failure after a valid version is written: product reads the versioned artifact; the publisher reports a partial operational failure.
- Frozen replay mismatch: deployment or manual promotion check exits non-zero; approved reference remains unchanged.

## Testing

The implementation must demonstrate red-green coverage for:

1. Strategy contract rejection when any official LHB identity field is absent or different.
2. EOD publication performing no official writes for an invalid summary.
3. Versioned artifact paths being unique and manifest-owned.
4. Database trigger SQL being idempotent and rejecting an invalid successful LHB manifest.
5. Frozen replay validation accepting the approved summary and rejecting return, drawdown, trade-count, cash-slot, identity, and safety-invariant drift.
6. Dashboard API refusing invalid identity metrics and returning the current correct stable identity.

The affected backend suite, dashboard tests, dashboard production build, schema migration check, frozen replay, and 5174 API smoke test must all pass before completion.

## Rollout

1. Merge application, tests, and migration code.
2. Run all affected tests and the frozen replay against the current authoritative database.
3. Apply the idempotent manifest trigger to the `research` database.
4. Verify a deliberately invalid successful LHB manifest is rejected inside a rolled-back transaction.
5. Republish the correct 2026-07-17 LHB result into a versioned directory.
6. Verify the database manifest and the 5174 API point to that version and report 84.46% with the official identity.

## Non-Goals

- Removing market-regime experiment functions.
- Changing LHB ranking, eligibility, position sizing, or exit behaviour.
- Treating a specific cumulative-return percentage as the permanent strategy identity.
- Reworking Mid Trend or Tech Bottleneck strategy logic.
