# Rolling Sector 302-Concept Target Gap Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the 110 missing active memberships in the frozen 302-concept `ths` target, verify newly exposed stock-data coverage, and publish a clean sector-first replay without treating optional 1,379-board gaps as target backfill work.

**Architecture:** Freeze the 302 concept-code allowlist first and keep the strategy database-only. Run membership acquisition only inside an explicit backfill task, filter PIT assets to active non-BJ names, then audit market/status/finance/valuation coverage for the newly exposed assets. Re-run the same v2 batch and walk-forward evaluator; leave non-target `em`, `em_core_conception`, and `csrc` gaps in a separate deferred queue.

**Tech Stack:** Python 3.14, pandas, PostgreSQL/psycopg, existing `stock_research` CLI, existing AkShare/THS adapter only inside the backfill task, pytest, immutable rolling snapshot artifacts.

---

## Current evidence and scope gate

The authoritative read-only audit is
`docs/superpowers/verification/2026-08-03-rolling-sector-target-gap-audit.md`.

At the 2026-07-31 anchor the replay emits 1,053 `sector_features` gap rows,
which reduce to:

| Bucket | Count | Target action |
| --- | ---: | --- |
| `em`/`em_core_conception` history only 17 sessions | 911 | Defer; not part of the 302 target |
| `em_core_conception` missing volume | 9 | Defer; not part of the 302 target |
| Target `ths` concepts with no active membership | 110 | **P0 backfill** |
| Extra `ths`/`csrc` concepts with no active membership | 23 | Defer unless scope expands |

All 302 target concept bars exist through the anchor with valid close/volume;
the target blocker is membership coverage.  `ths:300238` / `核电` is one of
the 110 and must be present after the repair.

The plan deliberately does not reopen the historical 3,750-row audit as a
blanket download.  Its in-scope active non-BJ market/status gaps were already
closed; only newly exposed assets after membership repair are eligible for a
fresh targeted audit.

## Task 1: Freeze the target-code audit and make the gap report reproducible

**Files:**
- Modify: `src/stock_research/rolling_oversold/gap_backfill.py`
- Create: `tests/test_rolling_oversold_target_gap_audit.py`
- Keep current evidence: `docs/superpowers/verification/2026-08-03-rolling-sector-target-gap-audit.md`

- [ ] **Step 1: Add a failing target-audit test.**

```python
def test_target_sector_gap_audit_separates_membership_from_non_target_history():
    result = audit_sector_target_gaps(
        target_codes={"300238", "309268"},
        sector_rows=pd.DataFrame([
            {"sector_system": "ths", "sector_code": "300238",
             "membership_count": 0, "history_observations": 280,
             "sector_feature_data_status": "ok"},
            {"sector_system": "ths", "sector_code": "309268",
             "membership_count": 49, "history_observations": 22,
             "sector_feature_data_status": "ok"},
            {"sector_system": "em", "sector_code": "BK0425",
             "membership_count": 66, "history_observations": 17,
             "sector_feature_data_status": "insufficient_history"},
        ]),
    )
    assert result["target_membership_gap_codes"] == ["300238"]
    assert result["target_history_gap_codes"] == []
    assert result["deferred_non_target_gap_rows"] == 1
```

- [ ] **Step 2: Run the test and verify the expected failure.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_gap_audit.py::test_target_sector_gap_audit_separates_membership_from_non_target_history
```

Expected: failure because the target audit interface does not yet exist.

- [ ] **Step 3: Implement a read-only target audit.**

Add this interface to `gap_backfill.py`:

```python
def audit_sector_target_gaps(
    *, target_codes: set[str], sector_rows: pd.DataFrame
) -> dict[str, object]:
    """Classify published sector rows without writing a database."""
```

The implementation must classify only `ths` rows whose codes are in
`target_codes` as target rows.  It must return sorted code lists for
`target_membership_gap_codes`, `target_history_gap_codes`,
`target_volume_gap_codes`, and a count/list for deferred non-target rows.
`history_observations >= 6` and `sector_feature_data_status == "ok"` are the
existing publishability rules; do not invent a 20-session failure for the
three valid short-history target concepts.

- [ ] **Step 4: Run the audit tests and write the deterministic report.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_gap_audit.py \
  tests/test_rolling_oversold_gap_backfill.py
```

The report must reproduce 302 target codes, 110 target membership gaps, and
the 911/9/23 deferred buckets from the current audit.

- [ ] **Step 5: Commit the read-only audit.**

```text
rtk git add src/stock_research/rolling_oversold/gap_backfill.py \
  tests/test_rolling_oversold_target_gap_audit.py \
  docs/superpowers/verification/2026-08-03-rolling-sector-target-gap-audit.md
rtk git commit -m "feat: audit 302-sector target gaps"
```

## Task 2: Add an explicit 302-`ths` scope gate to v2 runs

**Files:**
- Modify: `src/stock_research/rolling_oversold/contracts.py`
- Modify: `src/stock_research/rolling_oversold/loaders.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_rolling_oversold_target_scope.py`

- [ ] **Step 1: Add failing scope tests.**

```python
def test_target_scope_loads_only_ths_allowlist():
    config = RollingOversoldConfig(
        anchor_start_date=date(2026, 7, 31),
        concept_systems=("ths",),
        concept_codes=("300238", "309268"),
    )
    assert config.concept_codes == ("300238", "309268")

def test_v2_target_batch_publishes_302_rows_not_the_optional_1379_board():
    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=target_config,
        inputs=_fixture_inputs(),
        service="research-test",
    )
    assert set(result["sector_states"]["sector_system"]) == {"ths"}
    assert len(result["sector_states"]) == 302
```

- [ ] **Step 2: Run the tests and verify they fail.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_scope.py
```

- [ ] **Step 3: Implement the scope gate.**

Append a validated `concept_codes` field to `RollingOversoldConfig` so old
positional construction remains compatible.  Extend the concept membership and
bar SQL builders with an optional `concept_code = ANY(%s)` predicate.  Add
`--concept-codes-file` to `rolling-sector-oversold-batch` and
`rolling-sector-oversold-replay`; accept either a CSV with a `concept_code`
column (the current target file) or one six-character code per line, and
reject duplicates, blank lines, and non-`ths` execution.  The target command
must construct:

```python
RollingOversoldConfig(
    anchor_start_date=anchor,
    anchor_end_date=anchor,
    concept_systems=("ths",),
    concept_codes=tuple(target_codes),
    sector_output_top_n=10,
)
```

When `concept_codes` is provided, the batch contract must require exactly one
row per `(ths, code)` and fail closed if any target code is absent.

- [ ] **Step 4: Run scope and regression tests.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_scope.py \
  tests/test_rolling_oversold_full_sector_batch.py \
  tests/test_rolling_oversold_pipeline.py
```

- [ ] **Step 5: Commit the scope gate.**

```text
rtk git add src/stock_research/rolling_oversold/contracts.py \
  src/stock_research/rolling_oversold/loaders.py \
  src/stock_research/cli.py \
  tests/test_rolling_oversold_target_scope.py
rtk git commit -m "feat: freeze the 302 concept target scope"
```

## Task 3: Preview and backfill the 110 target memberships

**Files:**
- Create: `src/stock_research/rolling_oversold/target_membership_backfill.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_rolling_oversold_target_membership_backfill.py`
- Modify: `docs/daily-close-pipeline-runbook.md`

- [ ] **Step 1: Add failing dry-run and idempotency tests.**

```python
def test_target_membership_dry_run_does_not_write(monkeypatch):
    result = run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238"},
        service="research-test",
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["database_writes"] == 0

def test_target_membership_backfill_rejects_bj_members(monkeypatch):
    rows = [{"asset_id": "CN:BJ:920001", "concept_code": "300238"}]
    with pytest.raises(ValueError, match="out_of_scope_bse"):
        validate_target_membership_rows(rows, target_codes={"300238"})
```

- [ ] **Step 2: Run the tests and verify they fail.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_membership_backfill.py
```

- [ ] **Step 3: Implement the explicit backfill boundary.**

The task must:

1. read the 302-code file and compare it to the source board list;
2. fetch constituents only for target `ths` concepts;
3. normalize codes with `_asset_id_from_cn_stock_code`;
4. reject `900xxx`, `CN:BJ:*`, non-master, delisted, or post-cutoff assets;
5. write board/membership rows only in a database transaction when
   `dry_run=False`; and
6. close an old active membership only when that concept fetched successfully,
   preserving history and recording failures.

Publish JSON/CSV counts for `target_codes`, `source_missing_codes`,
`failed_concepts`, `valid_non_bj_memberships`, `out_of_scope_bse`, and
`database_writes`.  The strategy loader must not call this module.

- [ ] **Step 4: Add the CLI and run preview first.**

```text
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-target-membership-backfill \
  --trade-date 2026-07-31 \
  --concept-codes-file /Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --service stock_research \
  --output-dir /tmp/rolling_sector_target_membership_20260731_preview \
  --dry-run
```

Do not proceed to writes unless the preview reports all 302 source codes and
the only excluded assets are BSE/invalid rows.

- [ ] **Step 5: Execute in one auditable write, then rerun idempotently.**

```text
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-target-membership-backfill \
  --trade-date 2026-07-31 \
  --concept-codes-file /Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --service stock_research \
  --output-dir /tmp/rolling_sector_target_membership_20260731 
```

Run the identical command a second time and require zero new logical rows.

- [ ] **Step 6: Commit the backfill executor and runbook.**

```text
rtk git add src/stock_research/rolling_oversold/target_membership_backfill.py \
  src/stock_research/cli.py \
  tests/test_rolling_oversold_target_membership_backfill.py \
  docs/daily-close-pipeline-runbook.md
rtk git commit -m "feat: backfill target concept memberships"
```

## Task 4: Audit newly exposed stock and PIT fundamental coverage

**Files:**
- Modify: `src/stock_research/rolling_oversold/gap_backfill.py`
- Modify: `src/stock_research/rolling_oversold/market_backfill.py`
- Modify: `src/stock_research/rolling_oversold/fundamental_backfill.py`
- Create: `tests/test_rolling_oversold_target_coverage.py`

- [ ] **Step 1: Add coverage tests for the post-membership asset union.**

```python
def test_target_coverage_reports_only_confirmed_missing_rows():
    result = audit_target_asset_coverage(
        asset_ids={"CN:SZ:000001"},
        market_rows=one_complete_qfq_history(),
        status_rows=one_complete_status_history(),
        finance_rows=pd.DataFrame(),
        valuation_rows=pd.DataFrame(),
        start_date=date(2025, 6, 10),
        end_date=date(2026, 7, 31),
    )
    assert result["market_missing_assets"] == []
    assert result["status_missing_assets"] == []
    assert result["finance_missing_assets"] == ["CN:SZ:000001"]
    assert result["valuation_missing_assets"] == ["CN:SZ:000001"]
```

- [ ] **Step 2: Run the test and verify it fails.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_coverage.py
```

- [ ] **Step 3: Implement the read-only coverage audit.**

Use the exact target member union after PIT asset filtering.  Require the
252-session qfq market-bar window and matching `core.asset_status_daily` rows;
do not count BSE, inactive, or invalid assets.  For finance/valuation, report
missing PIT support separately and preserve the existing no-fabrication rule:
no EV/EBITDA value may be synthesized when the source field is absent.

- [ ] **Step 4: Route confirmed gaps to existing explicit backfill jobs.**

Use `market_backfill.py` only for the reported market assets/date ranges, then
rebuild status.  Use `fundamental_backfill.py` only for reported finance and
valuation assets.  The strategy command must never call an external source.

- [ ] **Step 5: Run coverage and idempotency tests.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_coverage.py \
  tests/test_rolling_oversold_market_backfill.py \
  tests/test_rolling_oversold_fundamental_backfill.py
```

- [ ] **Step 6: Commit the targeted coverage audit.**

```text
rtk git add src/stock_research/rolling_oversold/gap_backfill.py \
  src/stock_research/rolling_oversold/market_backfill.py \
  src/stock_research/rolling_oversold/fundamental_backfill.py \
  tests/test_rolling_oversold_target_coverage.py
rtk git commit -m "feat: audit target asset coverage after membership repair"
```

## Task 5: Re-run the target batch and walk-forward acceptance

**Files:**
- Modify: `tests/test_rolling_oversold_acceptance.py`
- Modify: `docs/superpowers/verification/2026-08-03-sector-first-302-oversold-repair-v2-validation.md`
- Create: `docs/superpowers/verification/2026-08-03-rolling-sector-target-gap-backfill-validation.md`

- [ ] **Step 1: Add the post-backfill acceptance assertions.**

```python
def test_target_replay_has_302_rows_and_nuclear_membership_after_backfill():
    result = pipeline.run_rolling_replay(
        config=target_config,
        output_dir=tmp_path,
        service="research-test",
    )
    board = pd.read_csv(result["anchors"][-1]["paths"]["sector_states"])
    assert len(board) == 302
    assert board["sector_system"].eq("ths").all()
    assert board["membership_count"].gt(0).all()
    assert board.loc[board["sector_code"].eq("300238"), "sector_name"].eq("核电").all()
```

- [ ] **Step 2: Run the focused acceptance suite.**

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_gap_audit.py \
  tests/test_rolling_oversold_target_scope.py \
  tests/test_rolling_oversold_target_membership_backfill.py \
  tests/test_rolling_oversold_target_coverage.py \
  tests/test_rolling_oversold_acceptance.py
```

- [ ] **Step 3: Run the frozen target replay.**

```text
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-27 \
  --anchor-end-date 2026-07-31 \
  --output-dir /tmp/rolling_sector_target_replay_20260727_20260731 \
  --score-version rolling_oversold_sector_v2 \
  --service stock_research \
  --concept-codes-file /Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv
```

- [ ] **Step 4: Verify the post-backfill gates.**

Require all five anchors to contain exactly 302 `ths` rows, zero target
membership gaps, `ths:300238` with a positive membership count, immutable
manifests, no target date leakage, and both `complete` and `pending` outcome
states.  Any remaining non-target gap must remain in the deferred queue and
must not block the target replay.

- [ ] **Step 5: Record counts, source failures, and runtime.**

Write the exact source response counts, database upsert counts, target gap
counts before/after, candidate rows, outcome states, and stage timings to the
validation document.  Do not claim the deferred 911/9 rows are repaired.

- [ ] **Step 6: Commit the acceptance record.**

```text
rtk git add tests/test_rolling_oversold_acceptance.py \
  docs/superpowers/verification/2026-08-03-sector-first-302-oversold-repair-v2-validation.md \
  docs/superpowers/verification/2026-08-03-rolling-sector-target-gap-backfill-validation.md
rtk git commit -m "test: accept 302-sector target gap backfill"
```

## Deferred optional phase: restore the entire 1,379-row board

Do not start this phase as part of the target repair.  If the user later
requires all configured board systems, create a separate plan for the 911
17-session histories, 9 missing-volume rows, 21 extra `ths` memberships, and
2 `csrc` memberships.  That plan must specify a 252-session history range,
source availability checks, and its own runtime budget; it must not dilute the
P0 target membership repair.
