# Kronos small/base Rolling Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only, parameterized daily rolling evaluator that freezes 20 stocks' historical daily-K snapshots, runs Kronos-small and Kronos-base under identical inputs, compares them with simple baselines, and produces reproducible accuracy and model-capability reports.

**Architecture:** Keep the evaluation logic in focused Python modules: one module for configuration and snapshot contracts, one for PostgreSQL data extraction, one for the existing Kronos /v1/predict HTTP contract, one for metrics, and one for resumable artifact orchestration. The CLI runs in three explicit stages—prepare, predict, and report—so the historical inputs are frozen before either model is run. The production dashboard and its prediction cache are not modified.

**Tech Stack:** Python 3.11+, pandas, psycopg, requests, pytest, PyArrow for immutable tabular artifacts, the existing Kronos /v1/predict service on 187, and the existing market_daily_bar PostgreSQL table.

---

## File map

Create these focused modules and tests:

- src/stock_research/kronos_evaluation_types.py — validated configuration, normalized bars, rolling snapshot and run-manifest contracts.
- src/stock_research/kronos_evaluation_data.py — PostgreSQL daily-bar loading, trading-calendar construction, snapshot generation, input fingerprints, and data-quality statuses.
- src/stock_research/kronos_evaluation_client.py — authenticated HTTP client for /health and /v1/predict, including model identity checks and response normalization.
- src/stock_research/kronos_evaluation_metrics.py — point, direction, interval, quantile, baseline, aggregate, and paired small/base metrics.
- src/stock_research/kronos_evaluation_runner.py — prepare/predict/report orchestration, resumable manifests, artifact writing, and report rendering.
- scripts/run_kronos_rolling_evaluation.py — command-line entry point with explicit prepare, predict, and report stages.
- tests/test_kronos_evaluation_types.py — contract and parameter validation tests.
- tests/test_kronos_evaluation_data.py — synthetic-frame snapshot and no-future-leakage tests.
- tests/test_kronos_evaluation_client.py — request/response and model-mismatch tests.
- tests/test_kronos_evaluation_metrics.py — deterministic metric and comparison tests.
- tests/test_kronos_evaluation_runner.py — fake-client end-to-end artifact and resume tests.
- tests/test_kronos_rolling_evaluation_cli.py — CLI stage/argument dispatch tests.
- docs/quant_system/70_kronos_rolling_evaluation_runbook.md — operator runbook for the 187 model process, the three CLI stages, and post-run acceptance.
- pyproject.toml — add pyarrow so the required Parquet artifacts are reproducible in the research environment.

Do not modify dashboard/src, dashboard/src/api/kronos.ts, the production dashboard API, or the online Kronos cache schema.

## Task 1: Add evaluation contracts and configuration

**Files:**
- Create: src/stock_research/kronos_evaluation_types.py
- Create: tests/test_kronos_evaluation_types.py

- [ ] **Step 1: Write failing contract tests.**

Add tests for:

~~~python
def test_config_accepts_the_confirmed_defaults():
    config = KronosEvaluationConfig(
        asset_ids=("CN:SH:600418", "CN:SZ:000001"),
        start_date="2025-01-02",
        end_date="2025-01-31",
    )
    assert config.input_window == 250
    assert config.forecast_horizon == 10
    assert config.evaluation_horizons == (1, 3, 5, 10)
    assert config.sample_count == 20
    assert config.models == ("small", "base")
    assert config.roll_step == 1


def test_config_rejects_duplicate_assets_and_invalid_horizons():
    with pytest.raises(ValueError, match="unique"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418", "CN:SH:600418"),
            start_date="2025-01-02",
            end_date="2025-01-31",
        )
    with pytest.raises(ValueError, match="horizon"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            evaluation_horizons=(1, 11),
            forecast_horizon=10,
        )


def test_snapshot_key_and_fingerprint_are_stable():
    snapshot = make_ready_snapshot()
    assert snapshot.key == "CN:SH:600418|2025-01-02"
    assert snapshot.input_fingerprint == make_ready_snapshot().input_fingerprint
~~~

The test module must define make_ready_snapshot with concrete deterministic Bar dictionaries and must compute the fingerprint through the public fingerprint helper. Also assert that models are normalized to ("small", "base"), forecast_horizon is at most 10 for the current service contract, and sample_count is between 1 and 100.

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run:

~~~bash
rtk pytest -q tests/test_kronos_evaluation_types.py
~~~

Expected: collection or import failures because the new contracts do not yet exist.

- [ ] **Step 3: Implement the contracts.**

Define these public types:

~~~python
@dataclass(frozen=True)
class KronosEvaluationConfig:
    asset_ids: tuple[str, ...]
    start_date: str
    end_date: str
    input_window: int = 250
    roll_step: int = 1
    forecast_horizon: int = 10
    evaluation_horizons: tuple[int, ...] = (1, 3, 5, 10)
    sample_count: int = 20
    models: tuple[str, ...] = ("small", "base")
    adjust_type: str = "qfq"
    db_service: str = "stock_research"
    predict_url: str = "http://192.168.3.187:8123"
    token_env: str = "KRONOS_INTERNAL_TOKEN"
    timeout_seconds: float = 60.0
    seed: int | None = 20260806


@dataclass(frozen=True)
class RollingSnapshot:
    asset_id: str
    origin_date: str
    history: tuple[dict[str, Any], ...]
    future_timestamps: tuple[str, ...]
    realized: tuple[dict[str, Any], ...]
    input_fingerprint: str
    status: str
    reason: str | None = None

    @property
    def key(self) -> str:
        return f"{self.asset_id}|{self.origin_date}"
~~~

Normalize accepted codes using stock_research.assets.asset_id_from_baostock_code; accept canonical CN:SH:600418, sh.600418, 600418.SH, and six-digit codes only when the exchange can be resolved from core.asset_master. Reject duplicates after normalization. Validate dates, ordered horizons, and models in {"small", "base"}.

- [ ] **Step 4: Run the focused tests and commit.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_types.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_types.py tests/test_kronos_evaluation_types.py
rtk git commit -m "feat: add Kronos evaluation contracts"
~~~

Expected: all contract tests pass and only the two new files are committed.

## Task 2: Load historical bars and build frozen rolling snapshots

**Files:**
- Create: src/stock_research/kronos_evaluation_data.py
- Create: tests/test_kronos_evaluation_data.py

- [ ] **Step 1: Write failing synthetic-frame tests.**

Cover these cases:

~~~python
def test_build_snapshots_uses_only_bars_at_or_before_origin():
    frame = make_daily_frame("CN:SH:600418", start="2024-01-01", periods=20)
    snapshots = build_rolling_snapshots(
        frame,
        trade_dates=["2024-01-15"],
        input_window=5,
        forecast_horizon=3,
    )
    assert snapshots[0].history[-1]["timestamp"] == "2024-01-15"
    assert all(row["timestamp"] <= "2024-01-15" for row in snapshots[0].history)
    assert snapshots[0].future_timestamps == (
        "2024-01-16", "2024-01-17", "2024-01-18"
    )


def test_missing_history_or_truth_is_explicitly_statused_without_padding():
    frame = make_daily_frame("CN:SH:600418", start="2024-01-01", periods=7)
    snapshots = build_rolling_snapshots(
        frame,
        trade_dates=["2024-01-03", "2024-01-07"],
        input_window=5,
        forecast_horizon=3,
    )
    assert snapshots[0].status == "insufficient_input"
    assert snapshots[1].status == "insufficient_truth"
    assert len(snapshots[0].history) < 5


def test_input_fingerprint_changes_when_a_history_value_changes():
    first = build_ready_snapshot(make_daily_frame(close_offset=0.0))
    changed = build_ready_snapshot(make_daily_frame(close_offset=0.01))
    assert first.input_fingerprint != changed.input_fingerprint
~~~

The test module must define make_daily_frame with pd.date_range, deterministic OHLCV values, and one asset_id; it must replace every abbreviated fixture argument with concrete data before the test is committed.

- [ ] **Step 2: Run the focused tests and confirm they fail.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_data.py
~~~

Expected: import or missing-function failures.

- [ ] **Step 3: Implement the PostgreSQL loader and snapshot builder.**

Implement:

~~~python
def load_daily_bars(
    asset_ids: Sequence[str],
    *,
    max_date: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    sql = """
        SELECT trade_date::text AS trade_date,
               asset_id, open, high, low, close, volume, amount,
               trade_status, is_st
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date <= %s
          AND asset_id = ANY(%s)
        ORDER BY asset_id, trade_date
    """
~~~

Use stock_research.db.connect and fetch_all. Load through the last required truth date, and derive the global exchange calendar from distinct dates in the same adjust_type slice. For each asset and origin date:

1. select the last input_window rows with trade_date <= origin_date;
2. select the next forecast_horizon global trading dates after the origin;
3. require a real bar for every future timestamp; missing rows produce insufficient_truth;
4. reject non-finite numeric fields, duplicate dates, invalid OHLC relationships, and non-monotonic timestamps;
5. serialize the six Kronos input fields (open, high, low, close, volume, amount) and compute a SHA-256 fingerprint over canonical JSON;
6. never pad history, forward-fill truth, or use bars after the origin in history.

Retain source metadata for experiment.json: adjust_type, source table, row count, min/max date, and query timestamp.

- [ ] **Step 4: Run tests, inspect the query diff, and commit.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_data.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_data.py tests/test_kronos_evaluation_data.py
rtk git commit -m "feat: freeze Kronos rolling evaluation snapshots"
~~~

## Task 3: Add the explicit-snapshot Kronos client

**Files:**
- Create: src/stock_research/kronos_evaluation_client.py
- Create: tests/test_kronos_evaluation_client.py

- [ ] **Step 1: Write failing request and response tests.**

Use a fake requests.Session and assert the exact payload sent to the existing 187 service:

~~~python
def test_predict_daily_posts_the_frozen_snapshot():
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)
    result = client.predict_daily(snapshot, model="small", sample_count=20, seed=7)
    assert result["status"] == "succeeded"
    request = session.requests[-1]
    assert request["url"] == "http://kronos.test/v1/predict"
    assert request["json"]["model"] == "small"
    assert request["json"]["daily"]["history"] == list(snapshot.history)
    assert request["json"]["daily"]["future_timestamps"] == list(snapshot.future_timestamps)


def test_model_mismatch_fails_before_prediction():
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(health={"status": "ok", "model": "Kronos-small"}),
    )
    with pytest.raises(KronosClientError, match="base|small"):
        client.predict_daily(snapshot, model="base", sample_count=20, seed=7)
~~~

Also test non-200 responses, timeout errors, missing token, malformed JSON, and health responses that report Kronos-base for a requested small run.

- [ ] **Step 2: Run the focused tests and confirm they fail.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_client.py
~~~

- [ ] **Step 3: Implement KronosClient.**

Expose:

~~~python
class KronosClient:
    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def assert_model(self, model: str) -> dict[str, Any]:
        raise NotImplementedError
    def predict_daily(
        self,
        snapshot: RollingSnapshot,
        *,
        model: str,
        sample_count: int,
        seed: int | None,
    ) -> dict[str, Any]:
        raise NotImplementedError
~~~

Use requests.Session, X-Kronos-Token, the configured timeout, and JSON ISO timestamps. assert_model must normalize small/Kronos-small and base/Kronos-base. The client must fail closed on model mismatch; it must not silently fall back to the active model. Preserve the raw response under each run artifact so the 20-sample result can be audited.

- [ ] **Step 4: Run tests and commit.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_client.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_client.py tests/test_kronos_evaluation_client.py
rtk git commit -m "feat: add frozen-snapshot Kronos client"
~~~

## Task 4: Implement point, interval, baseline, and paired metrics

**Files:**
- Create: src/stock_research/kronos_evaluation_metrics.py
- Create: tests/test_kronos_evaluation_metrics.py

- [ ] **Step 1: Write deterministic metric tests.**

Cover:

~~~python
def test_score_forecast_computes_return_error_and_direction():
    scored = score_forecast(
        last_close=100.0,
        actual_closes=[102.0, 98.0, 105.0],
        p10=[98.0, 96.0, 100.0],
        p50=[101.0, 99.0, 104.0],
        p90=[104.0, 103.0, 110.0],
        horizons=(1, 3),
    )
    assert scored["h1"]["direction_hit"] is True
    assert scored["h3"]["actual_return"] == pytest.approx(-0.02)
    assert 0.0 <= scored["h1"]["interval_coverage"] <= 1.0


def test_persistence_and_drift_baselines_are_deterministic():
    result = build_baselines([100.0, 102.0, 101.0], horizon=3, drift_window=2)
    assert result["persistence"] == [100.0, 100.0, 100.0]
    assert len(result["drift"]) == 3


def test_paired_comparison_returns_model_delta_and_block_bootstrap_interval():
    rows = [
        {"origin_date": "2025-01-02", "asset_id": "CN:SH:600418", "small": 0.10, "base": 0.08},
        {"origin_date": "2025-01-03", "asset_id": "CN:SH:600418", "small": 0.12, "base": 0.09},
        {"origin_date": "2025-01-02", "asset_id": "CN:SZ:000001", "small": 0.07, "base": 0.08},
    ]
    comparison = compare_models(rows, left="small", right="base", seed=7)
    assert comparison["paired_count"] == len(rows)
    assert comparison["base_minus_small"] is not None
    assert comparison["ci_low"] <= comparison["ci_high"]
~~~

- [ ] **Step 2: Run focused tests and confirm they fail.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_metrics.py
~~~

- [ ] **Step 3: Implement the metric functions.**

Use these primary formulas for each horizon h:

~~~python
actual_return = actual_close[h - 1] / last_close - 1.0
predicted_return = predicted_p50[h - 1] / last_close - 1.0
absolute_return_error = abs(predicted_return - actual_return)
normalized_price_error = abs(predicted_p50[h - 1] - actual_close[h - 1]) / abs(last_close)
direction_hit = (predicted_return >= 0) == (actual_return >= 0)
interval_coverage = p10[h - 1] <= actual_close[h - 1] <= p90[h - 1]
~~~

Implement persistence and recent-drift baselines, P10/P50/P90 pinball loss, interval width, per-stock/per-horizon aggregation, and paired base-minus-small differences. For overlapping daily windows, bootstrap complete origin-date blocks rather than treating individual rows as independent. Use deterministic random.Random(seed) and return the 2.5% and 97.5% empirical bounds. A missing or failed run is excluded from a metric denominator but remains visible in coverage counts.

- [ ] **Step 4: Run tests and commit.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_metrics.py
rtk git diff --check
rtk git add src/stock_research/kronos_evaluation_metrics.py tests/test_kronos_evaluation_metrics.py
rtk git commit -m "feat: add Kronos rolling evaluation metrics"
~~~

## Task 5: Add resumable artifact orchestration

**Files:**
- Create: src/stock_research/kronos_evaluation_runner.py
- Create: tests/test_kronos_evaluation_runner.py
- Modify: pyproject.toml to add pyarrow

- [ ] **Step 1: Write fake-client runner tests.**

Test that a two-stock, two-origin fixture:

1. writes experiment.json, universe.csv, input_snapshots/, and run_manifest.csv during preparation;
2. writes raw prediction and realized rows during a small run;
3. resumes without calling the client again for a completed asset_id|origin_date|model key;
4. preserves a model_error status without running base as a fallback;
5. combines small and base results into model/horizon summaries and a final report.md.

The fake client must record calls and return a fixed P10/P50/P90 payload so the assertions are deterministic.

- [ ] **Step 2: Run focused tests and confirm they fail.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_runner.py
~~~

- [ ] **Step 3: Add the Parquet dependency and implement the runner.**

Add the literal dependency below to [project].dependencies:

~~~toml
"pyarrow",
~~~

Expose:

~~~python
def prepare_experiment(config: KronosEvaluationConfig, *, output_dir: Path) -> PreparationResult:
    raise NotImplementedError
def run_model(
    config: KronosEvaluationConfig,
    *,
    model: str,
    output_dir: Path,
    client: KronosClient,
) -> ModelRunResult:
    raise NotImplementedError
def build_report(*, output_dir: Path) -> dict[str, Any]:
    raise NotImplementedError
~~~

Preparation must write canonical JSON snapshots and an immutable experiment.json containing config, universe, source metadata, code revision, and creation time. Prediction must write the manifest after every run so interruption is resumable. The run key is snapshot.key + | + model; a completed key with the same input fingerprint, model identity, parameters, and seed is a cache hit. A changed fingerprint or model weight identity must force a new run.

Write these artifacts exactly:

~~~text
experiment.json
universe.csv
input_snapshots/<asset_id>__<origin_date>.json
run_manifest.csv
forecast_bars.parquet
realized_bars.parquet
metrics_by_stock_horizon.csv
metrics_by_model_horizon.csv
model_comparison.csv
report.md
~~~

Use atomic temporary-file replacement for JSON, CSV, and Parquet writes. Do not overwrite the production Kronos cache. The report must include run counts by status, coverage by model/horizon, baseline comparisons, base-minus-small paired deltas, bootstrap intervals, model load/latency statistics, and one of the four fixed conclusions: small_preferred, base_preferred, no_clear_winner, or not_proven.

- [ ] **Step 4: Run tests and commit.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_runner.py
rtk git diff --check
rtk git add pyproject.toml src/stock_research/kronos_evaluation_runner.py tests/test_kronos_evaluation_runner.py
rtk git commit -m "feat: add resumable Kronos evaluation runner"
~~~

## Task 6: Add the three-stage CLI

**Files:**
- Create: scripts/run_kronos_rolling_evaluation.py
- Create: tests/test_kronos_rolling_evaluation_cli.py

- [ ] **Step 1: Write CLI dispatch tests.**

Assert that the parser accepts these exact stages and options:

~~~text
prepare --universe-file --start-date --end-date --output-dir
predict --model {small,base} --output-dir --predict-url --token-env
report --output-dir
~~~

Also test --input-window, --forecast-horizon, --horizons, --sample-count, --seed, --adjust-type, --db-service, --timeout-seconds, and --allow-smoke. Without --allow-smoke, prepare must reject a universe whose normalized size is not exactly 20; the two-stock fixture uses --allow-smoke. Verify that predict --model base passes only base to run_model, and that an invalid horizon or missing universe file returns a non-zero CLI result.

- [ ] **Step 2: Run focused tests and confirm they fail.**

~~~bash
rtk pytest -q tests/test_kronos_rolling_evaluation_cli.py
~~~

- [ ] **Step 3: Implement the CLI.**

Use argparse and print one JSON summary line to stdout. The operational sequence is:

~~~bash
rtk python3 scripts/run_kronos_rolling_evaluation.py \
  prepare \
  --universe-file config/kronos/evaluation_universe_20.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --output-dir outputs/research/kronos_rolling_eval/2025-01

rtk python3 scripts/run_kronos_rolling_evaluation.py \
  predict --model small \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8123

rtk python3 scripts/run_kronos_rolling_evaluation.py \
  predict --model base \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8124

rtk python3 scripts/run_kronos_rolling_evaluation.py \
  report --output-dir outputs/research/kronos_rolling_eval/2025-01
~~~

The prepared snapshot directory is the only input used by both predict stages. The CLI must refuse predict if preparation metadata is absent or if the active Kronos health model does not match the requested model. It must never substitute the active model or use dashboard /api/assets/... endpoints because those endpoints read current live data rather than the frozen historical snapshot.

- [ ] **Step 4: Run CLI tests and commit.**

~~~bash
rtk pytest -q tests/test_kronos_rolling_evaluation_cli.py
rtk git diff --check
rtk git add scripts/run_kronos_rolling_evaluation.py tests/test_kronos_rolling_evaluation_cli.py
rtk git commit -m "feat: add Kronos rolling evaluation CLI"
~~~

## Task 7: Document safe model switching and run acceptance

**Files:**
- Create: docs/quant_system/70_kronos_rolling_evaluation_runbook.md

- [ ] **Step 1: Document the current 187 service facts.**

Record that the production service is /home/mqkj/kronos, listens on port 8123, currently loads Kronos-small, and has Kronos-base weights installed. The runbook must not contain passwords or tokens.

- [ ] **Step 2: Document the base preflight process.**

Use a non-production research process on a separate port when possible:

~~~bash
cd /home/mqkj/kronos
KRONOS_MODEL_NAME=Kronos-base \
/home/mqkj/miniconda3/envs/kronos/bin/python -m uvicorn service.app:app \
  --host 0.0.0.0 --port 8124
~~~

The operator must first check /health, confirm model=Kronos-base, run one single-stock prediction, and record GPU memory and latency. If the second process cannot load because of GPU memory, stop the research process and use the existing service-switch procedure to run base serially; do not stop the production service before a rollback command is ready.

- [ ] **Step 3: Document the acceptance checks.**

The runbook must require:

~~~bash
rtk pytest -q tests/test_kronos_evaluation_types.py tests/test_kronos_evaluation_data.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py tests/test_kronos_rolling_evaluation_cli.py
rtk git diff --check
~~~

For a real experiment, verify that both model manifests have identical snapshot keys and input fingerprints, every status is accounted for, no model mismatch or fallback occurred, and report.md contains all four horizon rows and both baselines.

- [ ] **Step 4: Commit the runbook.**

~~~bash
rtk git add docs/quant_system/70_kronos_rolling_evaluation_runbook.md
rtk git commit -m "docs: add Kronos rolling evaluation runbook"
~~~

## Task 8: Verification and first controlled run

**Files:**
- No source changes; use artifacts under outputs/research/kronos_rolling_eval/.

- [ ] **Step 1: Run the complete unit and integration test set.**

~~~bash
rtk pytest -q tests/test_kronos_evaluation_types.py tests/test_kronos_evaluation_data.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py tests/test_kronos_rolling_evaluation_cli.py
rtk python3 -m compileall -q src/stock_research scripts/run_kronos_rolling_evaluation.py
~~~

Expected: all new tests pass and compilation exits 0.

- [ ] **Step 2: Run a two-stock, three-origin smoke evaluation against 187.**

Use a temporary universe file with exactly two fixture stocks, prepare snapshots, run whichever model is currently healthy, and confirm the generated manifest contains the expected snapshot keys, raw response, and sample_count=20. Do not use the smoke result as an accuracy conclusion.

- [ ] **Step 3: Run the confirmed 20-stock, one-month experiment.**

Use the final operator-supplied 20-stock universe and date parameters. Prepare once, run small, switch or launch base after health verification, run base, and then build the report. Preserve the complete experiment directory as an immutable research artifact.

- [ ] **Step 4: Perform the final evidence review before claiming results.**

Check:

~~~bash
rtk git status --short
rtk python3 -c "import json; from pathlib import Path; p=Path('outputs/research/kronos_rolling_eval/2025-01/report.md'); print(p.exists(), p)"
~~~

The final user-facing result must distinguish prediction accuracy, uncertainty calibration, model capability, latency, and data/model failures. It must not claim base is better merely because it has more parameters.

## Self-review checklist

- Spec coverage: Tasks 1–2 cover the 20-stock daily rolling snapshots, 250-bar input, strict no-leakage and future truth rules; Tasks 3 and 7 cover the existing 187 service and small/base model identity; Task 4 covers point, direction, interval and baseline metrics; Tasks 5–6 cover the required artifacts, parameters and resumability; Task 8 covers verification and the real run.
- Placeholder scan: the plan contains no TBD, TODO, or unspecified implementation step. The real run intentionally takes the operator-supplied universe and dates as CLI arguments, as required by the approved design.
- Type consistency: RollingSnapshot, KronosEvaluationConfig, KronosClient, prepare_experiment, run_model, and build_report are defined before their use in later tasks; model names are normalized consistently to small and base.
- Scope: no dashboard, production cache, strategy, or trading behavior changes are included.
