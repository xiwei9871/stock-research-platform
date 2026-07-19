# Strategy Compute And Publish Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic, database-enforced publication protocol so every official strategy result is identity-validated, versioned, replay-accepted, and safely exposed by the dashboard.

**Architecture:** A repository registry defines one `StrategyPublicationContract` for each official strategy/profile. Calculation adapters attach a canonical `publication_identity`; the EOD publisher validates it before writing versioned artifacts; `ops.strategy_publication_contract` plus a generic trigger rejects invalid successful manifests; the dashboard and a replay/API verifier consume the same identity. LHB, Mid Trend, Tech Bottleneck, and future registered strategies use the same framework, with strategy-specific acceptance profiles kept as data and validator callbacks.

**Tech Stack:** Python 3.14, pandas, pytest, PostgreSQL/psycopg, FastAPI, React/TypeScript/Vitest, JSON fixtures, SHA-256 canonical JSON fingerprints.

---

## File Map

- Create `src/stock_research/strategy_publication_contracts.py`: immutable contract dataclass, official registry, canonical config serialization, identity construction, and validation.
- Create `src/stock_research/strategy_publication_artifacts.py`: immutable version-directory creation, CSV/JSON writes, compatibility mirrors, and SHA-256 publication manifests shared by every strategy writer.
- Create `src/stock_research/strategy_publication_store.py`: PostgreSQL table/trigger DDL, contract seeding, and manifest identity lookup helpers.
- Create `scripts/validate_official_strategy_publications.py`: fixed-date replay and all-strategy publication acceptance CLI.
- Create `scripts/verify_strategy_publication_api.py`: 5174/8765 API smoke verifier for every runnable official strategy.
- Create `tests/test_strategy_publication_contracts.py`: registry, fingerprint, identity, and mismatch tests.
- Create `tests/test_strategy_publication_artifacts.py`: version uniqueness, file hashing, compatibility-mirror, and incomplete-write tests.
- Create `tests/test_strategy_publication_store.py`: DDL and contract-seeding tests.
- Create `tests/integration/test_strategy_publication_store_postgres.py`: real PostgreSQL trigger acceptance and rejection tests inside rolled-back transactions.
- Create `tests/test_validate_official_strategy_publications.py`: replay acceptance/rejection tests.
- Create `tests/test_verify_strategy_publication_api.py`: API verifier tests with a fake HTTP client.
- Create `tests/fixtures/official_strategy_publication_baselines.json`: reviewed baseline summary tolerances and structural checks for all three official strategies.
- Modify `src/stock_research/strategy_contracts.py`: expose the selected profile contract as a publication contract input and preserve existing parameter validation.
- Modify `src/stock_research/dashboard/backtests.py`: attach identity after fresh/replay calculation, validate manifest identity, and expose generic publication fields.
- Modify `src/stock_research/strategy_eod_publish.py`: validate before writes, write versioned artifacts plus hash manifest, and attach identity to all three strategy results.
- Modify `src/stock_research/tech_bottleneck_eod.py`: route the Tech Bottleneck strategy entry and files through the common versioned artifact writer while retaining its candidate-source entry.
- Modify `src/stock_research/data_run_manifest.py`: apply the publication schema with the manifest schema and preserve idempotent initialization.
- Modify `src/stock_research/dashboard/review_queue.py`: reject invalid publication identities before loading review rows.
- Modify `tests/test_strategy_contracts.py`, `tests/test_dashboard_backtests.py`, `tests/test_strategy_eod_publish.py`, `tests/test_dashboard_review_queue.py`, and `tests/test_data_run_manifest.py`: cover the generic gates and preserve existing strategy behavior.
- Create `tests/test_tech_bottleneck_eod.py`: Tech Bottleneck publication identity, versioned path, and manifest-entry tests.
- Modify `dashboard/src/api/types.ts`, `dashboard/src/components/HomeCockpit.tsx`, and `dashboard/src/components/ReviewQueueWorkspace.tsx`: expose identity, contract, and artifact-version state without LHB-specific branches.
- Modify `dashboard/tests/home-cockpit.test.tsx` and `dashboard/tests/review-queue-workspace.test.tsx`: assert generic strategy identity rendering and mismatch suppression.

## Task 1: Define The Generic Publication Contract Registry

**Files:**
- Create: `src/stock_research/strategy_publication_contracts.py`
- Create: `tests/test_strategy_publication_contracts.py`
- Modify: `src/stock_research/strategy_contracts.py`
- Modify: `tests/test_strategy_contracts.py`

- [ ] **Step 1: Write failing registry and fingerprint tests**

Add tests that require all current official strategies to resolve to a contract and that canonical JSON ordering produces the same digest:

```python
from stock_research.strategy_publication_contracts import (
    OFFICIAL_STRATEGY_IDS,
    canonical_config_fingerprint,
    get_publication_contract,
)


def test_registry_contains_all_current_official_strategies():
    assert OFFICIAL_STRATEGY_IDS == {
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
    }
    for strategy_id in OFFICIAL_STRATEGY_IDS:
        contract = get_publication_contract(strategy_id, profile="balanced")
        assert contract.strategy_id == strategy_id
        assert contract.identity_schema_version == "strategy_publication_identity_v1"
        assert contract.contract_id
        assert contract.engine_version
        assert contract.variant


def test_canonical_config_fingerprint_is_key_order_independent():
    left = {"top_n": 5, "adjust_type": "hfq", "risk_profile": "balanced"}
    right = {"risk_profile": "balanced", "adjust_type": "hfq", "top_n": 5}
    assert canonical_config_fingerprint(left) == canonical_config_fingerprint(right)


def test_lhb_policy_is_data_not_a_validator_branch():
    contract = get_publication_contract("lhb_shortline", profile="balanced")
    assert contract.publication_policy == {
        "strategy_version": "lhb_v1_stable_safe_top5",
        "selection_policy": "phase18c_top5_then_eligibility_no_refill",
        "market_regime_policy": "disabled_for_stable_strategy",
    }
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_contracts.py tests/test_strategy_contracts.py -q
```

Expected: FAIL because the generic registry, identity schema, and fingerprint functions do not exist.

- [ ] **Step 3: Implement the registry and fingerprint**

Implement an immutable dataclass:

```python
@dataclass(frozen=True)
class StrategyPublicationContract:
    strategy_id: str
    profile: str
    contract_id: str
    engine_version: str
    variant: str
    normalized_run_config: Mapping[str, Any]
    publication_policy: Mapping[str, Any]
    identity_schema_version: str = "strategy_publication_identity_v1"
    acceptance_profile: str = "default"
```

Populate the balanced contracts with these current official variants:

```text
lhb_shortline = auction_enhanced_rerank:balanced
mid_trend = top5_weekly_max2_selective_trend_holding_protection_v1
tech_bottleneck = strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d
```

Use these initial policy mappings:

```python
{
    "lhb_shortline": {
        "strategy_version": "lhb_v1_stable_safe_top5",
        "selection_policy": "phase18c_top5_then_eligibility_no_refill",
        "market_regime_policy": "disabled_for_stable_strategy",
    },
    "mid_trend": {
        "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1",
    },
    "tech_bottleneck": {
        "universe": "strict_153_st_only_financial_state",
        "frequency": "biweekly",
        "protection_name": "rank_exit_top10_1d",
    },
}
```

`canonical_config_fingerprint` must serialize with `sort_keys=True`, compact separators, UTF-8, and SHA-256. Add `build_publication_identity(contract)` and `validate_publication_identity(actual, expected)` returning a structured mismatch list.

Extend `StrategyContract` only as needed to expose `contract_id`, `engine`, `variant`, and normalized run configuration; do not change existing `validate_strategy_summary_against_contract` semantics yet.

- [ ] **Step 4: Run registry and existing contract tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_contracts.py tests/test_strategy_contracts.py -q
```

Expected: PASS with existing contract-path tests unchanged.

- [ ] **Step 5: Commit the registry**

```bash
rtk git add src/stock_research/strategy_publication_contracts.py src/stock_research/strategy_contracts.py tests/test_strategy_publication_contracts.py tests/test_strategy_contracts.py
rtk git commit -m "feat: add generic strategy publication contracts"
```

## Task 2: Attach And Validate Identity At Calculation Boundaries

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/strategy_contracts.py`
- Modify: `tests/test_dashboard_backtests.py`
- Modify: `tests/test_strategy_publication_contracts.py`

- [ ] **Step 1: Write failing calculation-identity tests**

Add tests for all three strategies and a mismatch:

```python
def test_attach_publication_identity_adds_summary_and_result_identity():
    result = {
        "strategy_id": "mid_trend",
        "config": {"top_n": 5, "rebalance_frequency": "weekly", "adjust_type": "hfq"},
        "summary": {"engine_version": "mid_trend_v1", "variant": "top5_weekly_max2_selective_trend_holding_protection_v1"},
    }
    attached = backtests.attach_publication_identity(result, profile="balanced")
    assert attached["publication_identity"]["strategy_id"] == "mid_trend"
    assert attached["summary"]["publication_identity"] == attached["publication_identity"]


def test_validate_publication_identity_reports_policy_mismatch():
    result = make_valid_lhb_result()
    result["summary"]["publication_identity"]["publication_policy"]["market_regime_policy"] = "legacy_overlay"
    with pytest.raises(ValueError, match="publication identity mismatch"):
        backtests.validate_official_strategy_result(result, profile="balanced")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py tests/test_strategy_publication_contracts.py -q
```

Expected: FAIL because result identity attachment and generic result validation do not exist.

- [ ] **Step 3: Implement identity attachment and validation**

Add two public helpers in `dashboard/backtests.py`:

```python
def attach_publication_identity(result: dict[str, Any], *, profile: str) -> dict[str, Any]: ...

def validate_official_strategy_result(result: dict[str, Any], *, profile: str) -> dict[str, Any]: ...
```

`attach_publication_identity` resolves the contract by `strategy_id`, takes `result["config"]` plus contract defaults, computes the fingerprint, builds the identity, and copies it into both result and summary. It must not overwrite a declared identity silently; a declared-but-different identity is a validation error.

Call this helper from `run_fresh_backtest` and `run_replay_backtest` after each adapter returns. For the Tech Bottleneck EOD path used by `publish_strategy_eod`, call it before the result enters score-audit or artifact writing.

Update `_metrics_from_eod_summary` to expose generic fields: `contract_id`, `identity_schema_version`, `config_fingerprint`, `publication_policy`, and `artifact_version`. Keep existing LHB display fields as projections of the generic policy for backward compatibility.

- [ ] **Step 4: Run calculation and dashboard tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_contracts.py tests/test_dashboard_backtests.py tests/test_strategy_contracts.py -q
```

Expected: PASS; a legacy identity cannot be returned as an official result.

- [ ] **Step 5: Commit calculation identity**

```bash
rtk git add src/stock_research/dashboard/backtests.py src/stock_research/strategy_contracts.py tests/test_dashboard_backtests.py tests/test_strategy_publication_contracts.py
rtk git commit -m "feat: attach publication identity to strategy results"
```

## Task 3: Validate Before Writing And Publish Immutable Artifact Versions

**Files:**
- Create: `src/stock_research/strategy_publication_artifacts.py`
- Create: `tests/test_strategy_publication_artifacts.py`
- Create: `tests/test_tech_bottleneck_eod.py`
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `src/stock_research/tech_bottleneck_eod.py`
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `tests/test_strategy_publication_contracts.py`

- [ ] **Step 1: Write failing pre-write and versioning tests**

Add tests that use a temporary output root:

```python
def test_invalid_identity_writes_no_official_artifact(tmp_path):
    result = make_valid_lhb_result()
    result["summary"]["publication_identity"]["publication_policy"]["market_regime_policy"] = "legacy_overlay"
    with pytest.raises(ValueError, match="publication identity mismatch"):
        strategy_eod_publish._write_strategy_artifacts(
            run_id="run-1",
            trade_date="2026-07-17",
            strategy_id="lhb_shortline",
            result=result,
            output_dir=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
    assert not list(tmp_path.rglob("strategy_lhb_shortline_review.csv"))


def test_valid_artifacts_use_unique_versioned_directory_and_hash_manifest(tmp_path):
    result = make_valid_lhb_result()
    entry, _ = strategy_eod_publish._write_strategy_artifacts(...)
    artifact_path = Path(entry["artifact_path"])
    assert "strategy_runs/lhb_shortline/" in str(artifact_path)
    assert artifact_path.exists()
    manifest = Path(entry["metadata"]["publication_manifest_path"])
    assert manifest.exists()
    assert entry["metadata"]["publication_identity"] == result["publication_identity"]


def test_tech_bottleneck_uses_same_versioned_writer(tmp_path):
    result = run_tech_bottleneck_eod(
        start_date="2026-01-01",
        end_date="2026-07-17",
        output_dir=tmp_path,
        frame_loader=fake_tech_frames,
        manifest_upsert=lambda entry: None,
    )
    assert "/strategy_runs/tech_bottleneck/" in str(result["review_path"])
    assert result["publication_identity"]["strategy_id"] == "tech_bottleneck"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_eod_publish.py::test_invalid_identity_writes_no_official_artifact tests/test_strategy_eod_publish.py::test_valid_artifacts_use_unique_versioned_directory_and_hash_manifest tests/test_tech_bottleneck_eod.py::test_tech_bottleneck_uses_same_versioned_writer -q
```

Expected: FAIL because the publisher currently writes root-level files before identity validation and does not create versioned hash manifests.

- [ ] **Step 3: Implement staged, versioned artifact publication**

In `_write_strategy_artifacts`:

1. Call `validate_official_strategy_result` before creating any official output.
2. Create `output_dir / "strategy_runs" / strategy_id / publish_id` where `publish_id` is derived from `run_id`, `started_at`, and the identity fingerprint.
3. Write equity, positions, trades, review, summary, and a JSON publication manifest inside that directory.
4. Compute SHA-256 hashes for every written file and store them in the publication manifest.
5. Set manifest `artifact_path` and metadata paths to versioned files.
6. Write root-level compatibility mirrors only after validation and versioned writes succeed.

Put the file-writing implementation in `strategy_publication_artifacts.py` so both `_write_strategy_artifacts` and `run_tech_bottleneck_eod` call the same helper. The helper accepts `strategy_id`, `run_id`, `started_at`, identity, named DataFrames, and compatibility destinations; it returns versioned paths, hashes, artifact version, and publication-manifest path.

`_write_strategy_artifacts` must return the same `(entry, review)` shape so existing orchestration remains compatible. Refactor `run_tech_bottleneck_eod` to keep its candidate-source manifest entry but construct its official strategy entry from the shared writer and attach the same identity fields. Add `publication_identity`, `artifact_version`, and `publication_manifest_path` to metadata. The review queue must read only the manifest artifact path and reject rows whose identity is absent or mismatched.

- [ ] **Step 4: Run publisher and review-queue tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_artifacts.py tests/test_strategy_eod_publish.py tests/test_tech_bottleneck_eod.py tests/test_dashboard_review_queue.py -q
```

Expected: PASS; invalid results leave no official artifact, valid retries create distinct directories, and the dashboard cannot read a stale root mirror as the current product version.

- [ ] **Step 5: Commit versioned publication**

```bash
rtk git add src/stock_research/strategy_publication_artifacts.py src/stock_research/strategy_eod_publish.py src/stock_research/tech_bottleneck_eod.py src/stock_research/dashboard/review_queue.py tests/test_strategy_publication_artifacts.py tests/test_strategy_eod_publish.py tests/test_tech_bottleneck_eod.py tests/test_dashboard_review_queue.py tests/test_strategy_publication_contracts.py
rtk git commit -m "feat: publish strategy artifacts as validated versions"
```

## Task 4: Add Generic Database Contract Table And Trigger

**Files:**
- Create: `src/stock_research/strategy_publication_store.py`
- Create: `tests/test_strategy_publication_store.py`
- Modify: `src/stock_research/data_run_manifest.py`
- Modify: `tests/test_data_run_manifest.py`

- [ ] **Step 1: Write failing SQL and trigger tests**

Add SQL-string assertions and mocked cursor tests:

```python
def test_publication_schema_sql_creates_contract_table_and_generic_trigger():
    assert "ops.strategy_publication_contract" in CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL
    assert "trg_validate_strategy_publication_manifest" in CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL
    assert "strategy_lhb_shortline" not in CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL
    assert "strategy_publication_identity_v1" not in CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL


def test_apply_publication_schema_seeds_all_registered_contracts_and_is_idempotent(monkeypatch):
    calls = []
    monkeypatch.setattr(store, "connect", fake_connection(calls))
    store.apply_strategy_publication_schema()
    assert any("CREATE TABLE" in sql for sql in calls)
    assert any("INSERT INTO ops.strategy_publication_contract" in sql for sql in calls)
```

The SQL assertions deliberately prohibit LHB-specific constants in the trigger definition; values must come from seeded contract rows.

Create `tests/integration/test_strategy_publication_store_postgres.py` with a dedicated-service guard and real trigger assertions:

```python
pytestmark = pytest.mark.skipif(
    os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST") != "1"
    or not os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE"),
    reason="set STRATEGY_PUBLICATION_POSTGRES_TEST=1 and a dedicated service",
)


@pytest.mark.parametrize(
    "strategy_id",
    ["lhb_shortline", "mid_trend", "tech_bottleneck"],
)
def test_trigger_accepts_valid_and_rejects_altered_identity(strategy_id):
    service = os.environ["STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE"]
    apply_data_run_manifest_schema(service=service)
    with psycopg.connect(f"service={service}") as conn:
        expected = get_publication_contract(strategy_id, profile="balanced")
        with conn.transaction(force_rollback=True):
            conn.execute(valid_manifest_insert_sql(), valid_manifest_params(expected))
        with pytest.raises(psycopg.errors.RaiseException):
            with conn.transaction(force_rollback=True):
                conn.execute(
                    valid_manifest_insert_sql(),
                    altered_manifest_params(expected, field="contract_id"),
                )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_store.py tests/test_data_run_manifest.py -q
```

Expected: FAIL because the publication table, seed function, and trigger do not exist.

- [ ] **Step 3: Implement idempotent generic schema**

Create `apply_strategy_publication_schema(service=SETTINGS.research_service)` with:

- `CREATE TABLE IF NOT EXISTS ops.strategy_publication_contract`;
- a partial unique index for one active contract per `(strategy_id, profile)`;
- `CREATE OR REPLACE FUNCTION ops.validate_strategy_publication_manifest()`;
- `DROP TRIGGER IF EXISTS ...; CREATE TRIGGER ... BEFORE INSERT OR UPDATE` on `ops.data_run_manifest`;
- upserts for every contract in the repository registry.

The trigger resolves `strategy_id` from the manifest module mapping, reads profile and `metadata.publication_identity`, compares it with the active contract row using JSONB equality, and raises a descriptive exception on mismatch. Unregistered official modules and missing identities are rejected; non-strategy data-run modules continue to work unchanged.

Call `apply_strategy_publication_schema` from `apply_data_run_manifest_schema` after the manifest table exists. Keep all DDL idempotent and transaction-safe.

Also add:

```python
def verify_strategy_publication_db_contracts(
    service: str = SETTINGS.research_service,
) -> dict[str, Any]: ...
```

This helper opens a transaction, tries one valid and one deliberately altered synthetic manifest for every registered strategy, records whether the trigger behaved correctly, rolls back unconditionally, and raises if any invalid write is accepted or valid write is rejected.

- [ ] **Step 4: Run schema unit tests and PostgreSQL integration tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_store.py tests/test_data_run_manifest.py -q
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/integration/test_strategy_publication_store_postgres.py -q
```

Expected: unit tests pass; `tests/integration/test_strategy_publication_store_postgres.py` proves valid LHB, Mid Trend, and Tech Bottleneck manifests insert, while missing, stale, and altered identities fail inside rolled-back transactions.

- [ ] **Step 5: Commit the database gate**

```bash
rtk git add src/stock_research/strategy_publication_store.py src/stock_research/data_run_manifest.py tests/test_strategy_publication_store.py tests/test_data_run_manifest.py tests/integration/test_strategy_publication_store_postgres.py
rtk git commit -m "feat: enforce generic strategy publication contracts in postgres"
```

## Task 5: Add Common Replay Acceptance Profiles And Validator

**Files:**
- Create: `tests/fixtures/official_strategy_publication_baselines.json`
- Create: `scripts/validate_official_strategy_publications.py`
- Create: `tests/test_validate_official_strategy_publications.py`
- Modify: `src/stock_research/strategy_publication_contracts.py`

- [ ] **Step 1: Write failing validator tests**

Use small fake result payloads and a temporary baseline file:

```python
def test_validator_accepts_identity_and_common_invariants(tmp_path):
    baseline = write_baseline(tmp_path, strategy_id="mid_trend", total_return=0.1)
    report = validate_result(valid_mid_trend_result(), baseline=baseline)
    assert report["status"] == "success"


@pytest.mark.parametrize("field", ["total_return", "max_drawdown", "filled_trade_count", "config_fingerprint"])
def test_validator_rejects_drift(field, tmp_path):
    result = valid_mid_trend_result()
    result["summary"][field] = drift_value(field)
    with pytest.raises(ValueError, match="acceptance mismatch"):
        validate_result(result, baseline=write_baseline(tmp_path, strategy_id="mid_trend"))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_validate_official_strategy_publications.py -q
```

Expected: FAIL because no common validator or baseline schema exists.

- [ ] **Step 3: Implement baseline schema and validator**

The JSON fixture must contain one approved profile per current strategy with:

```json
{
  "strategy_id": "...",
  "profile": "balanced",
  "baseline_end_date": "...",
  "summary": {
    "total_return": 0.0,
    "max_drawdown": 0.0,
    "filled_trade_count": 0,
    "cash_slot_count": 0
  },
  "tolerances": {"total_return": 1e-10, "max_drawdown": 1e-10},
  "acceptance_profile": "..."
}
```

Implement `validate_result(result, baseline)` in the script module. It must validate identity, dates, finite metrics, account safety, artifact hashes, and strategy-specific acceptance callbacks registered by strategy ID. The CLI accepts `--strategy-id`, `--profile`, `--baseline-path`, `--output`, and `--all`; `--all` runs every registered strategy with its fixed baseline date through `run_fresh_backtest`.

Do not invent baseline values. Generate each current strategy’s candidate report from the authoritative database, review it, and then commit the exact approved values to the fixture as a deliberate baseline approval step.

- [ ] **Step 4: Run validator tests and generate reviewed candidate baselines**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_validate_official_strategy_publications.py -q
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/validate_official_strategy_publications.py --all --emit-candidates /tmp/official-strategy-baselines-candidates.json
```

Review all three candidate summaries, copy only approved values into `tests/fixtures/official_strategy_publication_baselines.json`, then run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/validate_official_strategy_publications.py --all --baseline-path tests/fixtures/official_strategy_publication_baselines.json
```

Expected: non-zero before the fixture is approved; zero after the reviewed fixture is committed and all identity and safety checks pass.

- [ ] **Step 5: Commit replay acceptance**

```bash
rtk git add src/stock_research/strategy_publication_contracts.py scripts/validate_official_strategy_publications.py tests/test_validate_official_strategy_publications.py tests/fixtures/official_strategy_publication_baselines.json
rtk git commit -m "feat: add all-strategy publication replay acceptance"
```

## Task 6: Make Dashboard And API Reads Generic And Fail Closed

**Files:**
- Create: `scripts/verify_strategy_publication_api.py`
- Create: `tests/test_verify_strategy_publication_api.py`
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Modify: `tests/test_dashboard_backtests.py`
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`

- [ ] **Step 1: Write failing generic API and UI tests**

Add a backend test that feeds one invalid identity among three strategies and asserts only that strategy is `contract_mismatch`. Add a TypeScript fixture with generic fields and assert the UI labels the contract ID/version and does not show invalid returns as ready metrics.

Add a script test:

```python
def test_verify_api_requires_identity_and_versioned_artifact(monkeypatch):
    payload = {"items": [valid_lhb_item(), valid_mid_trend_item(), invalid_tech_item()]}
    result = verify_payload(payload)
    assert result["status"] == "failed"
    assert result["failures"] == ["tech_bottleneck: contract_mismatch"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py tests/test_verify_strategy_publication_api.py -q
rtk proxy pnpm --dir dashboard test -- --run dashboard/tests/home-cockpit.test.tsx dashboard/tests/review-queue-workspace.test.tsx
```

Expected: FAIL because the API model and UI expose only the existing strategy-specific fields and there is no all-strategy verifier.

- [ ] **Step 3: Implement generic read-model and API checks**

Extend the backend metrics read model with `contract_id`, `identity_schema_version`, `config_fingerprint`, `publication_policy`, `artifact_version`, and `publication_manifest_path`. Validate against the registry before returning performance metrics; preserve existing strategy-specific projections for compatibility.

Extend TypeScript strategy types with optional generic publication fields. Render a neutral “正式合同 / 产物版本 / 校验状态” block for all strategies. Keep LHB-specific explanatory copy only where the publication policy contains it.

Implement `verify_payload(payload)` and the command-line HTTP wrapper. It must iterate all runnable official strategy IDs, require `contract_status == "success"`, compare identity fields, require `performance_as_of_date`, and check that artifact paths include `/strategy_runs/<strategy-id>/`.

- [ ] **Step 4: Run backend, frontend, and API verifier tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py tests/test_verify_strategy_publication_api.py -q
rtk proxy pnpm --dir dashboard test -- --run dashboard/tests/home-cockpit.test.tsx dashboard/tests/review-queue-workspace.test.tsx
rtk proxy pnpm --dir dashboard build
```

Expected: all checks pass and invalid identities are suppressed uniformly for all three strategies.

- [ ] **Step 5: Commit generic dashboard enforcement**

```bash
rtk git add scripts/verify_strategy_publication_api.py tests/test_verify_strategy_publication_api.py src/stock_research/dashboard/backtests.py src/stock_research/dashboard/review_queue.py dashboard/src/api/types.ts dashboard/src/components/HomeCockpit.tsx dashboard/src/components/ReviewQueueWorkspace.tsx tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py dashboard/tests/home-cockpit.test.tsx dashboard/tests/review-queue-workspace.test.tsx
rtk git commit -m "feat: make strategy publication reads fail closed"
```

## Task 7: Apply Migration, Republish All Strategies, And Verify Production State

**Files:**
- Runtime only: current `research` PostgreSQL service and `outputs/research/strategy_daily_eod/`
- No source changes in this task.

- [ ] **Step 1: Run the complete affected test matrix**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_publication_contracts.py tests/test_strategy_contracts.py tests/test_strategy_publication_store.py tests/test_data_run_manifest.py tests/test_strategy_eod_publish.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py tests/test_validate_official_strategy_publications.py tests/test_verify_strategy_publication_api.py -q
rtk proxy pnpm --dir dashboard test -- --run dashboard/tests/home-cockpit.test.tsx dashboard/tests/review-queue-workspace.test.tsx
rtk proxy pnpm --dir dashboard build
```

Expected: zero test failures and a successful production build.

- [ ] **Step 2: Apply the idempotent publication schema**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -c 'from stock_research.data_run_manifest import apply_data_run_manifest_schema; apply_data_run_manifest_schema(); print("strategy publication schema applied")'
```

Expected: the table, seed rows, unique active-contract index, trigger function, and trigger exist without altering historical manifests.

- [ ] **Step 3: Run negative database writes in rolled-back transactions**

For each of `lhb_shortline`, `mid_trend`, and `tech_bottleneck`, insert a synthetic `success` manifest with one altered identity field inside a transaction, assert PostgreSQL raises the publication-contract exception, and roll back. Then insert a valid synthetic row inside a transaction and roll it back.

Run the existing PostgreSQL integration test plus:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -c 'import json; from stock_research.strategy_publication_store import verify_strategy_publication_db_contracts; print(json.dumps(verify_strategy_publication_db_contracts(), ensure_ascii=False, sort_keys=True))'
```

Expected: all invalid writes are rejected and no synthetic rows remain.

- [ ] **Step 4: Republish all current official strategies into versioned directories**

Run the publisher for the latest available trade date with the current official contracts. Verify the resulting manifests for `strategy_lhb_shortline`, `strategy_mid_trend`, and `strategy_tech_bottleneck` have:

- `status = success`;
- matching `publication_identity`;
- `artifact_path` beneath `strategy_runs/<strategy-id>/`;
- existing file hashes;
- current performance date.

Do not refresh unrelated research outputs. If one strategy fails validation, leave its previous successful version current and fix that strategy before retrying.

- [ ] **Step 5: Run replay and 5174 API acceptance**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/validate_official_strategy_publications.py --all --baseline-path tests/fixtures/official_strategy_publication_baselines.json
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python scripts/verify_strategy_publication_api.py --base-url http://127.0.0.1:5174
rtk git diff --check
rtk git status --short
```

Expected: all replay profiles pass, the API verifier reports all three strategies valid, and only unrelated pre-existing worktree changes remain. Runtime database and output files are not committed. Report the manifest IDs, artifact versions, replay summaries, and API verification report in the handoff.

## Plan Self-Review

- The plan covers every specification section: generic identity, configuration fingerprint, pre-write validation, versioned artifacts, database table/trigger, strategy-specific acceptance profiles, dashboard suppression, API smoke checks, migration, and all-strategy rollout.
- LHB policy values appear only in the registry fixture and LHB acceptance profile; the generic database trigger and publisher contain no LHB-specific branch.
- All production-code tasks begin with a failing test and have an explicit command and expected result.
- No task changes strategy trading logic or automatically updates an approved baseline.
- The database migration and runtime republish are separated from source commits and explicitly verified.
