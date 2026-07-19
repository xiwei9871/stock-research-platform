# Strategy Compute And Publish Contract Design

## Goal

Guarantee that every official strategy result shown by the product was computed with the currently approved strategy identity, passed strategy-specific acceptance checks, and was published as an immutable artifact version. An older branch or process must not be able to replace the current official result with a legacy calculation path.

## Scope

The first rollout covers all currently runnable official strategies:

- `lhb_shortline`
- `mid_trend`
- `tech_bottleneck`

Future strategies inherit the same controls by registering a publication contract. The design covers calculation identity, strategy validation, EOD publication, `ops.data_run_manifest`, immutable artifacts, dashboard reads, frozen replay acceptance, and rollout to the current `research` database.

The design does not change ranking, entry, exit, position sizing, or protection logic inside any strategy.

## Problem Statement

The existing contract validates important parameters such as engine, variant, TopN, transaction cost, frequency, adjustment type, universe, and protection name. It does not provide one canonical, database-enforced publication identity shared by calculation, artifacts, manifest rows, and product reads.

Consequently, a branch that lacks a later strategy change can still produce internally consistent metrics and publish them under the same broad engine and variant. LHB exposed this gap when a legacy market-regime account returned 175.29% and replaced the approved Stable Safe Top5 result. The same class of failure could affect any strategy.

## Publication Contract

Each official strategy has one active publication contract per selected profile. The generic contract contains:

```text
strategy_id
contract_id
engine_version
variant
normalized_run_config
config_fingerprint
publication_policy
identity_schema_version
acceptance_profile
```

`normalized_run_config` contains the strategy parameters that define official computation, including TopN, frequency, transaction cost, maximum position weight, adjustment type, and strategy-specific parameters.

`config_fingerprint` is the SHA-256 digest of the canonical JSON representation of `normalized_run_config`. Key ordering and serialization are fixed so all components calculate the same digest.

`publication_policy` is a strategy-owned mapping for identity fields not represented by the common configuration. For example, the LHB policy includes:

```text
strategy_version = lhb_v1_stable_safe_top5
selection_policy = phase18c_top5_then_eligibility_no_refill
market_regime_policy = disabled_for_stable_strategy
```

Mid Trend and Tech Bottleneck register their own official policy fields without adding strategy-specific branches to the publication framework.

## Calculation Identity

Every official calculation result must contain a `publication_identity` object derived from the active publication contract:

```json
{
  "identity_schema_version": "strategy_publication_identity_v1",
  "strategy_id": "...",
  "contract_id": "...",
  "engine_version": "...",
  "variant": "...",
  "config_fingerprint": "...",
  "publication_policy": {}
}
```

The identity is attached to the strategy summary, result payload, versioned artifact metadata, and data-run manifest metadata. Consumers compare the complete object, not individual display labels or return values.

Calculation helpers remain strategy-owned. The common framework receives a result and contract, derives the expected identity, and verifies that the strategy result declares the same engine, variant, configuration, and policy.

## Application Validation

The existing `StrategyContract` model will be extended or wrapped by a `StrategyPublicationContract` with generic identity and acceptance fields.

Validation occurs at three boundaries:

1. Immediately after calculation, before the result is returned as an official run.
2. At EOD publication, before any official artifact or compatibility mirror is written.
3. At dashboard read time, before metrics are marked ready.

Any mismatch returns a structured result with the mismatching field, expected value, and actual value. Official publication fails closed. The dashboard reports `contract_mismatch` and does not expose the invalid performance values as current official metrics.

No strategy can opt out of validation while remaining registered as runnable and official.

## Versioned Artifact Publication

Each validated strategy publication writes its primary files beneath:

```text
strategy_daily_eod/<trade-date>/strategy_runs/<strategy-id>/<publish-id>/
```

The publish ID combines the orchestration run ID with a unique publication timestamp or digest. A retry therefore creates a new directory and never mutates a previously referenced version.

The directory contains equity, positions, trades, review rows, summary metadata, and a publication manifest. File hashes are recorded in the publication manifest.

`ops.data_run_manifest.artifact_path` and every path in its metadata point to the versioned directory. Root-level strategy files remain compatibility mirrors for legacy offline consumers. They are written only after application validation and are never the source of truth for a newly published product result.

An incomplete version directory is never referenced by a successful database manifest. A failed retry leaves the previous successful manifest and its immutable files intact.

## Database Enforcement

The migration adds `ops.strategy_publication_contract`, containing the active publication contract for each official strategy and profile. Required fields include:

```text
strategy_id
profile
contract_id
identity_schema_version
expected_identity jsonb
acceptance_profile jsonb
active
created_at
updated_at
```

Only one active contract is allowed per strategy and profile.

An idempotent PostgreSQL trigger on `ops.data_run_manifest` applies to every successful official strategy module. It resolves the strategy and profile, loads the active contract, and requires the manifest `metadata.publication_identity` to equal the active `expected_identity`.

The trigger rejects:

- an unregistered official strategy;
- a missing publication identity;
- an unknown identity schema version;
- a stale contract ID;
- a different engine, variant, configuration fingerprint, or publication policy.

The trigger contains no LHB-specific values. Contracts for LHB, Mid Trend, and Tech Bottleneck are seeded by the migration from the repository registry. Future official strategies must be registered before their manifests can be written with `status = success`.

Historical rows remain readable. The trigger applies to new inserts and updates. After migration, all three current strategies are republished so their current manifests point to immutable version directories and carry the new identity.

## Strategy Acceptance Profiles

Each publication contract names an acceptance profile. The common replay validator loads the profile and performs common plus strategy-specific checks.

Common checks include:

- exact publication identity;
- requested and actual date consistency;
- finite total return and drawdown values;
- non-negative trade and position counts;
- artifact existence and recorded file-hash parity;
- account equity and reported summary consistency.

The initial strategy-specific checks are:

### LHB Shortline

- approved frozen summary through its baseline end date;
- Stable Safe Top5 publication policy;
- final Phase18C ranks at most five;
- no ineligible row in account trades;
- no research-only row in selected trades;
- no rank-six refill;
- approved filled-trade and cash-slot counts.

### Mid Trend

- approved benchmark variant;
- weekly rebalance identity;
- maximum replacement and holding-protection policy parity;
- account curve and holding-count consistency;
- approved frozen summary for the selected profile.

### Tech Bottleneck

- approved universe, frequency, and protection policy;
- candidate snapshot date not later than the calculation date;
- account curve and position-count consistency;
- approved frozen summary for the selected profile.

Approved replay values live in reviewed, source-controlled fixtures. Daily calculation never updates them automatically. Updating a fixture is a strategy promotion and requires an explicit code review.

## Replay And Verification Command

A common command validates one strategy or all registered official strategies. It:

1. loads the active repository contracts;
2. runs the approved fixed-date replay;
3. validates publication identity and acceptance profile;
4. audits generated artifact hashes and invariants;
5. exits non-zero on any mismatch;
6. emits a compact machine-readable report.

The command is used before deployment, after a contract change, and during controlled production verification. Full database replays are not required for every frontend-only test run, but the required release check runs all official strategies.

## Dashboard And API Behaviour

The dashboard selects only successful manifest rows whose publication identity matches the active contract. It exposes:

```text
contract_status
contract_id
identity_schema_version
artifact_version
performance_as_of_date
```

Invalid or unregistered results are shown as `contract_mismatch`. Their return, drawdown, and latest-period values are not promoted as current official performance.

The post-publication smoke test requests `/api/backtests/strategies`, iterates over all runnable official strategies, and requires:

- `contract_status = success`;
- identity equal to the active publication contract;
- performance date equal to the manifest performance date;
- artifact path beneath the strategy's immutable version directory.

## Operational Drift Detection

Identity validation is the blocking control. Numeric drift detection is secondary because a legitimate new market day can change returns.

The publisher compares the new result with the previous successful version and records warnings for unusually large changes in cumulative return, drawdown, trade count, or position count. Warning thresholds are strategy acceptance-profile settings. A warning is visible in operational reports but does not replace identity validation or automatically redefine an approved replay baseline.

## Failure Behaviour

- Calculation identity mismatch: result is not eligible for official publication.
- Publication validation failure: no versioned artifact or compatibility mirror is promoted.
- Database contract mismatch: insert or update is rejected; previous successful manifest remains current.
- Artifact write failure: incomplete directory remains unreferenced and can be cleaned later.
- Compatibility mirror failure: immutable product version remains valid; publication records a partial operational failure.
- Replay mismatch: release check exits non-zero; approved fixtures remain unchanged.
- Dashboard mismatch: invalid metrics are suppressed and a contract-mismatch state is shown.

## Migration And Rollout

1. Add the repository publication-contract registry and contracts for all three current strategies.
2. Add calculation identity and generic validation without changing trading logic.
3. Add versioned artifact publication and retain root compatibility mirrors.
4. Add the database contract table and generic trigger with unit and PostgreSQL integration tests.
5. Add common and strategy-specific replay acceptance profiles.
6. Run affected backend tests, dashboard tests, and production build.
7. Run fixed-date replays for LHB, Mid Trend, and Tech Bottleneck against the authoritative database.
8. Apply the idempotent migration to the current `research` database.
9. Verify invalid manifests for each registered strategy are rejected inside rolled-back transactions.
10. Republish all three strategies into immutable version directories.
11. Verify the database manifests and the 5174 API report valid identities and current performance.

## Testing

The implementation must demonstrate red-green coverage for:

1. Canonical configuration serialization and fingerprint stability.
2. Publication identity construction for each registered strategy.
3. Rejection of every common identity-field mismatch.
4. Rejection of strategy-specific publication-policy mismatches.
5. No official artifact writes before validation succeeds.
6. Unique immutable artifact directories and file-hash manifests.
7. Generic database trigger enforcement for all registered strategies.
8. Rejection of unregistered strategies and stale contract IDs.
9. Frozen replay acceptance and rejection paths for each strategy.
10. Dashboard suppression of invalid metrics.
11. Successful all-strategy API smoke validation.

Before completion, the affected Python suite, PostgreSQL migration tests, dashboard suite, dashboard production build, all-strategy replay command, database negative-write checks, and 5174 API smoke test must pass.

## Non-Goals

- Changing strategy trading logic.
- Removing research or experimental variants.
- Using a cumulative-return threshold as strategy identity.
- Replacing the existing data-run manifest with a separate orchestration platform.
- Automatically promoting a new strategy contract or replay baseline.
