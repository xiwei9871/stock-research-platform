# Kronos Configurable Rolling Evaluation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one reusable Kronos rolling-evaluation engine whose experiment behavior is controlled by a validated JSON file, then use it to run the approved 2026-07 small-model experiment.

**Architecture:** Keep the existing frozen-snapshot runner as the execution core and add a higher-level configuration loader, deterministic universe selector, and single config-driven CLI. Extend snapshot truth semantics so h=1 can be scored while h=3/5/10 remains pending, and keep the latest forecast-only rows outside accuracy metrics. Preserve the existing three-stage CLI for backward compatibility; the new CLI orchestrates the same prepare/predict/report primitives from one JSON configuration.

**Tech Stack:** Python 3.11 standard-library JSON and dataclasses, pandas, psycopg, requests, PyArrow, pytest, PostgreSQL `asset_master`, `market_daily_bar`, and `market.trading_calendar`.

---

## File map

Create:

- `src/stock_research/kronos_experiment_config.py` — JSON schema, validation, normalization, config fingerprinting, and conversion to the existing low-level evaluation config.
- `src/stock_research/kronos_experiment_universe.py` — database-backed candidate-pool query, deterministic random selection, latest-date resolution, and frozen selection metadata.
- `scripts/run_kronos_experiment.py` — one config-driven entry point with resumable `prepare`, `predict`, `report`, and `run` stages.
- `configs/kronos_2026_07_small_rolling.json` — the first reusable configuration, containing the approved C experiment values.
- `tests/test_kronos_experiment_config.py` — JSON schema and normalization tests.
- `tests/test_kronos_experiment_universe.py` — candidate filtering, deterministic sampling, and metadata fingerprint tests.
- `tests/test_kronos_experiment_cli.py` — config-driven CLI parsing, stage dispatch, and no-code-change parameter substitution tests.

Modify:

- `src/stock_research/kronos_evaluation_types.py` — add the generic evaluation fields needed by the config-driven runner while preserving existing constructor defaults and old metadata compatibility.
- `src/stock_research/kronos_evaluation_data.py` — add partial-truth, forecast-only, pending-calendar, and future-calendar snapshot construction.
- `src/stock_research/kronos_evaluation_client.py` — permit prediction of eligible non-`ready` snapshots with a complete forecast timestamp list.
- `src/stock_research/kronos_evaluation_metrics.py` — classify pending truth as non-scored and keep aggregation limited to rows with realized metrics.
- `src/stock_research/kronos_evaluation_runner.py` — accept new snapshot statuses, score only available horizons, persist sidecar artifacts, and record high-level config provenance.
- `scripts/run_kronos_rolling_evaluation.py` — allow the new sidecar files during legacy staged prediction/report validation.
- `tests/test_kronos_evaluation_types.py` — cover the new low-level fields.
- `tests/test_kronos_evaluation_data.py` — cover partial truth and forecast-only snapshots without changing legacy default behavior.
- `tests/test_kronos_evaluation_client.py` — cover eligible snapshot statuses.
- `tests/test_kronos_evaluation_metrics.py` — cover h=1-only scoring and pending rows.
- `tests/test_kronos_evaluation_runner.py` — cover partial artifacts, latest forecast exclusion, and sidecar validation.
- `docs/quant_system/70_kronos_rolling_evaluation_runbook.md` — document the one-command config workflow and the resume/verification rules.

Do not modify the production dashboard, online Kronos prediction cache, stock workbench API, or the service deployment on 187.

## Task 1: Add validated JSON experiment configuration

**Files:**
- Create: `src/stock_research/kronos_experiment_config.py`
- Modify: `src/stock_research/kronos_evaluation_types.py`
- Create: `tests/test_kronos_experiment_config.py`
- Modify: `tests/test_kronos_evaluation_types.py`

- [ ] **Step 1: Write failing configuration tests.**

Add tests using a temporary valid JSON file with this exact payload:

```json
{
  "schema_version": 1,
  "experiment_id": "test-small",
  "model": {"name": "small", "fallback": false, "seed": 7, "sample_count": 20},
  "data": {
    "frequency": "1d",
    "adjust_type": "qfq",
    "input_window": 3,
    "start_date": "2025-01-02",
    "end_date": "2025-01-31"
  },
  "universe": {
    "mode": "explicit",
    "count": 2,
    "seed": null,
    "market": "CN_A",
    "asset_ids": ["sh.600418", "000001.SZ"]
  },
  "prediction": {
    "forecast_horizon": 2,
    "report_horizons": [1, 2],
    "include_latest_forecast": false
  },
  "evaluation": {"primary_horizon": 1, "baseline": "persistence"}
}
```

Assert that `load_experiment_spec(path)` normalizes the asset IDs, preserves the seed and experiment ID, computes a stable SHA-256 config fingerprint, and converts the resolved values to a `KronosEvaluationConfig` with `models == ("small",)`, `evaluation_horizons == (1, 2)`, `primary_horizon == 1`, and `include_latest_forecast is False`.

Add parametrized rejection tests for: unsupported schema version, unknown model, `fallback=true`, invalid experiment ID, non-daily frequency, `end_date` before `start_date`, missing random seed, random count not equal to a positive integer, explicit mode without asset IDs, duplicate normalized IDs, primary horizon absent from report horizons, and report horizon greater than forecast horizon.

Add low-level type assertions that existing defaults remain `frequency == "1d"`, `primary_horizon == 1`, `include_latest_forecast is False`, and `fallback is False`.

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run:

```bash
rtk pytest -q tests/test_kronos_experiment_config.py tests/test_kronos_evaluation_types.py
```

Expected: import or constructor failures because the high-level config types and fields do not yet exist.

- [ ] **Step 3: Implement the configuration contract.**

Define the public `KronosExperimentSpec` dataclass with these fields:

```python
@dataclass(frozen=True)
class KronosExperimentSpec:
    schema_version: int
    experiment_id: str
    model_name: str
    fallback: bool
    model_seed: int | None
    sample_count: int
    frequency: str
    adjust_type: str
    input_window: int
    start_date: str
    end_date: str | None
    end_date_latest: bool
    universe_mode: str
    universe_count: int
    universe_seed: int | None
    market: str
    asset_ids: tuple[str, ...]
    forecast_horizon: int
    report_horizons: tuple[int, ...]
    primary_horizon: int
    include_latest_forecast: bool
    baseline: str
    config_fingerprint: str

    def to_evaluation_config(self, *, asset_ids: tuple[str, ...], end_date: str) -> KronosEvaluationConfig:
        return KronosEvaluationConfig(
            asset_ids=asset_ids,
            start_date=self.start_date,
            end_date=end_date,
            input_window=self.input_window,
            forecast_horizon=self.forecast_horizon,
            evaluation_horizons=self.report_horizons,
            sample_count=self.sample_count,
            models=(self.model_name,),
            adjust_type=self.adjust_type,
            frequency=self.frequency,
            primary_horizon=self.primary_horizon,
            include_latest_forecast=self.include_latest_forecast,
            fallback=self.fallback,
            experiment_id=self.experiment_id,
            config_fingerprint=self.config_fingerprint,
            seed=self.model_seed,
        )
```

Expose `load_experiment_spec(path: Path) -> KronosExperimentSpec` and `canonical_spec_payload(spec: KronosExperimentSpec) -> dict[str, Any]`. Implement them with `json.loads`, `canonical_json_fingerprint`, `normalize_asset_ids`, and ISO-date normalization already present in `kronos_evaluation_types.py`. The loader must reject unknown keys rather than silently ignoring misspelled parameters. `end_date: "latest_available"` is represented as `end_date_latest=True` and resolved only by the database-aware CLI stage.

Extend `KronosEvaluationConfig` with `frequency`, `primary_horizon`, `include_latest_forecast`, `fallback`, `experiment_id`, and `config_fingerprint`, all with backward-compatible defaults. Validate `frequency == "1d"` in this implementation, `primary_horizon` membership in `evaluation_horizons`, and `fallback is False` for the current no-fallback contract. Include all new fields in the existing config payload serialization so frozen metadata detects changes.

- [ ] **Step 4: Run tests, inspect the normalized payload, and commit.**

Run:

```bash
rtk pytest -q tests/test_kronos_experiment_config.py tests/test_kronos_evaluation_types.py
rtk git diff --check
```

Expected: all focused tests pass. Commit:

```bash
rtk git add src/stock_research/kronos_experiment_config.py src/stock_research/kronos_evaluation_types.py tests/test_kronos_experiment_config.py tests/test_kronos_evaluation_types.py
rtk git commit -m "feat: add configurable Kronos experiment schema"
```

## Task 2: Freeze the random universe and trading-date provenance

**Files:**
- Create: `src/stock_research/kronos_experiment_universe.py`
- Create: `tests/test_kronos_experiment_universe.py`

- [ ] **Step 1: Write failing selector tests.**

Use a monkeypatched `connect`/`fetch_all` seam and deterministic candidate rows. Verify:

```python
selection = select_universe(
    mode="random",
    count=2,
    seed=20260808,
    market="CN_A",
    adjust_type="qfq",
    input_window=250,
    cutoff_date="2026-06-30",
    service="stock_research",
)
    assert len(selection.asset_ids) == 2
    selection_again = select_universe(
        mode="random",
        count=2,
        seed=20260808,
        market="CN_A",
        adjust_type="qfq",
        input_window=250,
        cutoff_date="2026-06-30",
        service="stock_research",
    )
    assert selection.asset_ids == selection_again.asset_ids
assert selection.candidate_count == 3
assert selection.candidate_fingerprint == canonical_json_fingerprint(selection.candidates)
```

Cover exclusion of non-`listed` assets, ST names/flags, non-CN_A assets, and assets with fewer than 250 tradable qfq bars before the cutoff. Cover explicit mode preserving the supplied order and rejecting duplicates. Test `resolve_latest_market_date(adjust_type="qfq")` returns the maximum qfq `market_daily_bar.trade_date` from the fake database.

- [ ] **Step 2: Run the selector tests to verify they fail.**

```bash
rtk pytest -q tests/test_kronos_experiment_universe.py
```

Expected: import or missing-query-function failures.

- [ ] **Step 3: Implement the selector and provenance types.**

Define:

```python
@dataclass(frozen=True)
class UniverseSelection:
    asset_ids: tuple[str, ...]
    candidates: tuple[dict[str, Any], ...]
    selected_rows: tuple[dict[str, Any], ...]
    candidate_count: int
    selection_seed: int | None
    filters: Mapping[str, Any]
    candidate_fingerprint: str
    selection_fingerprint: str


def resolve_latest_market_date(*, adjust_type: str, service: str) -> str:
    """Return the maximum qfq market_daily_bar trade date as ISO text."""


def select_universe(*, mode: str, count: int, seed: int | None, market: str,
                    asset_ids: Sequence[str] | None, adjust_type: str,
                    input_window: int, cutoff_date: str, service: str) -> UniverseSelection:
    """Return a frozen explicit or deterministic random universe."""
```

Use a sorted candidate query against public `asset_master` and qfq `market_daily_bar`: require `a.market = %s`, `a.status = 'listed'`, `a.delist_date IS NULL`, no ST name matching `^(\\*?ST|S\\*ST)` (case-insensitive), no qfq bar with `is_st = true` through the cutoff, and at least `input_window` rows with `trade_status = '1'` and finite OHLC values through the cutoff. Order candidates by `asset_id` before applying `random.Random(seed).sample`; never use database `ORDER BY random()`.

For explicit mode, normalize the supplied IDs and use them without sampling. Record the exact filters, seed, candidate rows, selected rows, and both fingerprints. Add a `write_universe_selection(path, selection)` helper that writes the JSON sidecar with sorted keys and no secret values.

Add `load_trade_calendar_dates(adjust_type, start_date, end_date, service)` using `market.trading_calendar` open rows for SH/SZ/BJ, with a qfq `market_daily_bar` distinct-date fallback only for dates already observed in the frozen bar query. It must return strictly increasing ISO dates and never synthesize weekdays.

- [ ] **Step 4: Run tests and commit.**

```bash
rtk pytest -q tests/test_kronos_experiment_universe.py
rtk git diff --check
rtk git add src/stock_research/kronos_experiment_universe.py tests/test_kronos_experiment_universe.py
rtk git commit -m "feat: freeze deterministic Kronos experiment universes"
```

## Task 3: Add partial-truth and forecast-only snapshot semantics

**Files:**
- Modify: `src/stock_research/kronos_evaluation_data.py`
- Modify: `tests/test_kronos_evaluation_data.py`

- [ ] **Step 1: Write failing snapshot tests.**

Add tests with a seven-date synthetic frame and `forecast_horizon=3`:

```python
frame = make_daily_frame(periods=7)
frame = frame.loc[
    frame["trade_date"] != pd.Timestamp("2024-01-06")
].copy()
partial = build_rolling_snapshots(
    frame,
    trade_dates=make_trade_dates(7),
    input_window=3,
    forecast_horizon=3,
    minimum_truth_horizon=1,
    origin_dates=["2024-01-03"],
)[0]
assert partial.status == "partial_truth"
assert len(partial.realized) == 2

forecast_only = build_rolling_snapshots(
    make_daily_frame(periods=3),
    trade_dates=make_trade_dates(6),
    input_window=3,
    forecast_horizon=3,
    minimum_truth_horizon=1,
    forecast_only_origins=["2024-01-03"],
    origin_dates=["2024-01-03"],
)[0]
assert forecast_only.status == "forecast_only"
assert forecast_only.realized == ()
assert len(forecast_only.future_timestamps) == 3
```

Add a pending-calendar test with an empty future timestamp list and `forecast_only_origins`, asserting `status == "pending_calendar"`. Retain the existing tests that call the function without the new keyword arguments and assert the old `insufficient_truth` behavior.

- [ ] **Step 2: Run the focused data tests to verify they fail.**

```bash
rtk pytest -q tests/test_kronos_evaluation_data.py
```

- [ ] **Step 3: Implement the new status rules.**

Add these statuses to `SNAPSHOT_STATUSES`:

```python
{"ready", "partial_truth", "forecast_only", "pending_calendar",
 "insufficient_input", "insufficient_truth", "invalid_input"}
```

Extend `build_rolling_snapshots` with `minimum_truth_horizon: int | None = None` and `forecast_only_origins: Iterable[str] = ()`. Preserve the old default by setting `minimum_truth_horizon = forecast_horizon` when omitted. For each origin:

1. Keep the existing real-history validation and no-padding behavior.
2. Build future timestamps from the supplied frozen calendar.
3. If all `forecast_horizon` real bars exist, use `ready`.
4. If at least `minimum_truth_horizon` real bars exist but fewer than `forecast_horizon`, use `partial_truth` and retain the realized prefix.
5. If the origin is explicitly in `forecast_only_origins`, has exactly `forecast_horizon` future timestamps, and has no real bars, use `forecast_only`.
6. If the origin is explicitly in `forecast_only_origins` but the frozen calendar has fewer than `forecast_horizon` future timestamps, use `pending_calendar` and do not call the model.
7. Otherwise preserve `insufficient_truth`.

Update `prepare_rolling_snapshots` to pass the new arguments and include calendar min/max, requested truth horizon, and status counts in source metadata. Keep input fingerprints based only on asset, origin, and history; include future timestamps, realized prefix, status, and reason only in the full snapshot fingerprint.

- [ ] **Step 4: Run all data tests and commit.**

```bash
rtk pytest -q tests/test_kronos_evaluation_data.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_data.py tests/test_kronos_evaluation_data.py
rtk git commit -m "feat: support partial truth in Kronos snapshots"
```

## Task 4: Allow eligible snapshots through the client and runner

**Files:**
- Modify: `src/stock_research/kronos_evaluation_client.py`
- Modify: `src/stock_research/kronos_evaluation_runner.py`
- Modify: `scripts/run_kronos_rolling_evaluation.py`
- Modify: `tests/test_kronos_evaluation_client.py`
- Modify: `tests/test_kronos_evaluation_runner.py`

- [ ] **Step 1: Write failing client and runner tests.**

Add a client test that a `partial_truth` snapshot with three future timestamps posts the same frozen history and timestamp payload as a `ready` snapshot. Add tests that `forecast_only` is accepted and `pending_calendar` is rejected before HTTP.

Add a runner fixture with two snapshots for one asset: one `partial_truth` with one realized bar and one `forecast_only` with zero realized bars. Assert `run_model` attempts both eligible snapshots, writes three forecast rows for each, writes one realized row only for the partial snapshot, and records `pending_calendar` as skipped when present.

Add an integrity test that changing the high-level config fingerprint or `primary_horizon` makes an existing prepared directory incompatible, while old metadata without those optional fields still loads through the backward-compatible defaults.

- [ ] **Step 2: Run the focused tests to verify they fail.**

```bash
rtk pytest -q tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_runner.py
```

- [ ] **Step 3: Implement status-aware prediction and artifact validation.**

In `KronosClient.predict_daily`, accept only `{"ready", "partial_truth", "forecast_only"}` and require `len(snapshot.future_timestamps) > 0`; keep `pending_calendar`, `insufficient_truth`, `insufficient_input`, and `invalid_input` as local validation failures.

In `run_model`, replace the `snapshot.status != "ready"` skip with an explicit eligible-status set. Update manifest validation, cache matching, artifact row validation, status counts, and report integrity checks to compare against the snapshot's actual status rather than assuming every non-ready snapshot is skipped. Forecast rows must still cover every frozen future timestamp; realized rows must exactly cover the frozen realized prefix.

Add sidecar constants and top-level validation for:

```python
EXPERIMENT_CONFIG_FILENAME = "experiment_config.json"
UNIVERSE_SELECTION_FILENAME = "universe_selection.json"
LATEST_FORECAST_FILENAME = "latest_forecast.json"
```

The legacy CLI's documented top-level set must accept these files so a prepared config-driven experiment can be resumed through the old stages.

- [ ] **Step 4: Run the focused tests and commit.**

```bash
rtk pytest -q tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_runner.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_client.py src/stock_research/kronos_evaluation_runner.py scripts/run_kronos_rolling_evaluation.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_runner.py
rtk git commit -m "feat: run Kronos partial-truth snapshots"
```

## Task 5: Score only available horizons and exclude forecast-only rows

**Files:**
- Modify: `src/stock_research/kronos_evaluation_metrics.py`
- Modify: `src/stock_research/kronos_evaluation_runner.py`
- Modify: `tests/test_kronos_evaluation_metrics.py`
- Modify: `tests/test_kronos_evaluation_runner.py`

- [ ] **Step 1: Write failing metric tests.**

Test that a forecast with four predicted horizons and only one realized close returns an h=1 score, marks h=3/h=5/h=10 as pending, and does not increase the aggregate success count for those pending horizons. Test that a `forecast_only` row produces no accuracy metrics. Test that persistence baseline is emitted only when the primary horizon has realized truth.

- [ ] **Step 2: Run the focused metric tests to verify they fail.**

```bash
rtk pytest -q tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py
```

- [ ] **Step 3: Implement horizon-aware scoring.**

Add `partial_truth`, `forecast_only`, `pending_calendar`, and `pending_truth` to the metrics module's missing-status set. In `_build_metric_rows`, calculate `available_horizons = [h for h in horizons if h <= len(realized) and h <= len(forecast)]`, call `score_forecast` only with that available list, and set each output row's status to `success` only when that horizon has a score; otherwise use `pending_truth` for an otherwise successful model run or the manifest error status for failed runs.

Use `config.primary_horizon` as the required baseline horizon. Emit persistence and drift baseline rows only when the snapshot has at least that many realized closes; slice the baseline and actual arrays to the largest available horizon. Keep `forecast_only` rows in coverage/status accounting but ensure `aggregate_metrics` and model comparisons consume only rows with actual metric fields and success status.

Add `primary_horizon` and `scored` fields to the internal metric rows, preserve the existing summary CSV column order, and include primary-horizon coverage plus pending counts in `metrics_summary.json`/the Markdown report. Do not call h=3/h=5/h=10 output “accuracy” when their truth is absent.

- [ ] **Step 4: Run metrics, runner, and regression tests, then commit.**

```bash
rtk pytest -q tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_metrics.py src/stock_research/kronos_evaluation_runner.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py
rtk git commit -m "feat: score only realized Kronos horizons"
```

## Task 6: Build the single config-driven CLI and first configuration

**Files:**
- Create: `scripts/run_kronos_experiment.py`
- Create: `configs/kronos_2026_07_small_rolling.json`
- Create: `tests/test_kronos_experiment_cli.py`

- [ ] **Step 1: Write failing CLI tests.**

Test the parser accepts:

```bash
python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage prepare
python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage predict
python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage report
python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage run
```

Monkeypatch the database selector, `prepare_experiment`, `run_model`, and `build_report`; assert the `run` stage passes the normalized model, date, sample count, input window, report horizons, and one selected model to the existing core functions. Add a second temporary config changing only `start_date`, `input_window`, `sample_count`, and `model.name` and assert the same dispatch path receives the changed values without importing or editing another Python module.

Test that an existing output directory is rejected unless `--resume` is supplied, and that the CLI emits exactly one JSON summary line on validation errors.

- [ ] **Step 2: Run the CLI tests to verify they fail.**

```bash
rtk pytest -q tests/test_kronos_experiment_cli.py
```

- [ ] **Step 3: Implement the config-driven workflow.**

The script must expose `build_parser() -> argparse.ArgumentParser`, `main(argv: list[str] | None = None) -> int`, and `run_experiment(spec_path: Path, *, stage: str, resume: bool = False) -> dict[str, Any]`. `main` must catch configuration and runtime exceptions and print exactly one JSON object; `run_experiment` must return the structured summary described below.

The workflow must:

1. Load and validate the JSON spec.
2. Resolve `end_date=latest_available` through `resolve_latest_market_date`.
3. Use the ISO date immediately before `start_date` as the random-universe cutoff, so the current 2026-07-01 experiment uses 2026-06-30 and selection cannot use July data.
4. Select/freeze the universe and create `outputs/research/kronos_rolling_eval/<experiment_id>/`.
5. Build a `KronosEvaluationConfig` with exactly one configured model, `fallback=spec.fallback`, `primary_horizon=spec.primary_horizon`, `include_latest_forecast=spec.include_latest_forecast`, and the canonical config fingerprint; the approved file resolves these values to `False`, `1`, and `True`.
6. Call `prepare_experiment` with an injected snapshot loader that reads daily bars only through the frozen data boundary, loads the frozen trading calendar, uses `minimum_truth_horizon=primary_horizon`, and marks the latest origin as `forecast_only` when the next ten calendar sessions are available.
7. Write `experiment_config.json` and `universe_selection.json` atomically before prediction; refuse to overwrite them unless `--resume` is explicit and the fingerprints match.
8. For `predict`/`run`, load the token from the configured environment, call `client.assert_model(spec.model_name)`, and invoke `run_model` once. Never call a second model and never retry with fallback.
9. For `report`/`run`, call `build_report`, then write `latest_forecast.json` from the latest origin's forecast rows, preserving `forecast_only`, `pending_truth`, and `pending_calendar` states.
10. Return one JSON summary containing experiment ID, output directory, frozen end date, selected count, model, snapshot counts, primary-horizon coverage, and report paths.

Keep `scripts/run_kronos_rolling_evaluation.py` unchanged as the backward-compatible staged interface except for accepting the new sidecar names.

- [ ] **Step 4: Add the approved first configuration and run CLI tests.**

Create `configs/kronos_2026_07_small_rolling.json` with:

```json
{
  "schema_version": 1,
  "experiment_id": "2026-07-small-rolling",
  "model": {"name": "small", "fallback": false, "seed": 20260806, "sample_count": 20},
  "data": {
    "frequency": "1d",
    "adjust_type": "qfq",
    "input_window": 250,
    "start_date": "2026-07-01",
    "end_date": "latest_available"
  },
  "universe": {
    "mode": "random",
    "count": 20,
    "seed": 20260808,
    "market": "CN_A",
    "asset_ids": null
  },
  "prediction": {
    "forecast_horizon": 10,
    "report_horizons": [1, 3, 5, 10],
    "include_latest_forecast": true
  },
  "evaluation": {"primary_horizon": 1, "baseline": "persistence"}
}
```

Run:

```bash
rtk pytest -q tests/test_kronos_experiment_cli.py
rtk git diff --check
rtk git add scripts/run_kronos_experiment.py configs/kronos_2026_07_small_rolling.json tests/test_kronos_experiment_cli.py
rtk git commit -m "feat: add config-driven Kronos experiment CLI"
```

## Task 7: Update the operator runbook and full regression suite

**Files:**
- Modify: `docs/quant_system/70_kronos_rolling_evaluation_runbook.md`
- Modify: `tests/test_kronos_rolling_evaluation_cli.py` if sidecar validation changes require assertions.

- [ ] **Step 1: Document the parameter-only workflow.**

Add the exact operator commands:

```bash
rtk python scripts/run_kronos_experiment.py \
  --config configs/kronos_2026_07_small_rolling.json \
  --stage run
```

Document that future tests change only the JSON fields for dates, model, universe mode/count/seed, input window, forecast horizon, sample count, report horizons, and primary horizon. Document that `experiment_id` must be new for a new frozen output, `--resume` is only for continuing the same fingerprint, and `forecast_only`/`pending_truth` never count toward accuracy.

- [ ] **Step 2: Run the complete test suite.**

```bash
rtk pytest -q tests/test_kronos_experiment_config.py tests/test_kronos_experiment_universe.py tests/test_kronos_experiment_cli.py tests/test_kronos_evaluation_types.py tests/test_kronos_evaluation_data.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py tests/test_kronos_rolling_evaluation_cli.py
```

Expected: all focused and regression tests pass with no changed dashboard tests.

- [ ] **Step 3: Commit documentation and regression updates.**

```bash
rtk git diff --check
rtk git add docs/quant_system/70_kronos_rolling_evaluation_runbook.md tests/test_kronos_rolling_evaluation_cli.py
rtk git commit -m "docs: document parameterized Kronos evaluations"
```

## Task 8: Execute and verify the approved 2026-07 small experiment

**Files:**
- Runtime output only: `outputs/research/kronos_rolling_eval/2026-07-small-rolling/`

- [ ] **Step 1: Run a read-only preflight.**

Run the config validation and database preflight without prediction:

```bash
rtk python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage prepare
```

Verify the summary reports exactly 20 selected assets, a qfq database end date, a frozen candidate-pool fingerprint, and no `insufficient_input` count caused by an invalid universe. If the latest origin has no ten-session calendar, the summary must explicitly report `pending_calendar`; it must not fabricate dates.

- [ ] **Step 2: Run the small-model prediction and report.**

With `KRONOS_INTERNAL_TOKEN` available in the environment, run:

```bash
rtk python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage run
```

The command must use only the configured small service, sample count 20, model seed 20260806, and no fallback. It must not modify production caches or dashboard data.

- [ ] **Step 3: Verify the frozen output contract.**

Run:

```bash
rtk python scripts/run_kronos_experiment.py --config configs/kronos_2026_07_small_rolling.json --stage report --resume
rtk python -m pytest -q tests/test_kronos_evaluation_runner.py tests/test_kronos_experiment_cli.py
rtk git status --short
```

Inspect the output and assert:

- `universe.csv` contains exactly 20 IDs and matches `universe_selection.json`;
- `experiment_config.json` fingerprint equals the config fingerprint in the report/manifest;
- all successful forecast rows pass OHLC constraints and have model identity `small`;
- historical h=1 rows have realized truth and are the only rows used in the primary accuracy summary;
- h=3/h=5/h=10 pending rows are visibly labeled pending rather than counted as accuracy;
- `latest_forecast.json` is separate and marked `forecast_only` or `pending_calendar`;
- no prior prediction appears in any later snapshot history;
- the report contains Kronos small versus persistence baseline at h=1.

- [ ] **Step 4: Hand off the result.**

Report the output directory, frozen end date, selected stock IDs, primary h=1 sample count, direction hit rate, mean absolute return error, persistence comparison, pending forecast count, and any failed origins with their exact reasons. Do not claim the experiment is successful until these checks and the verification-before-completion checklist pass.

## Self-review checklist

- Every spec requirement maps to Tasks 1–8: reusable JSON configuration (Tasks 1 and 6), random frozen universe (Task 2), 250-bar real-history input (Task 3), 10-bar forecasts (Tasks 3–4), 20 paths and small identity (Tasks 4 and 8), h=1-only accuracy (Task 5), C-layer latest forecast (Tasks 3, 6, and 8), frozen outputs (Tasks 4 and 6), and tests/runbook (Tasks 7–8).
- No step relies on a second custom experiment script; `run_kronos_experiment.py` is the sole new entry point.
- The low-level `KronosEvaluationConfig` remains backward compatible through defaults, while the JSON schema rejects unsupported combinations before database access.
- The plan never synthesizes future exchange sessions from weekdays; missing future calendar data is represented as `pending_calendar`.
- The plan separates model fallback policy from model selection and hard-fails model identity mismatches.
