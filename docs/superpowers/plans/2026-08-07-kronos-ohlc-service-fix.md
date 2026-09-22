# Kronos OHLC Service Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 187 服务器 Kronos 服务在反归一化后生成非法日 K OHLC 的根因，并用同一份冻结快照重新验证 small/base 月度滚动结果。

**Architecture:** 在 187 的 `service/raw_predictor.py` 对每根生成 K 线做最小确定性 OHLC 投影：保留 open/close，必要时扩张 high 到不低于 open/close、收缩 low 到不高于 open/close。这样所有后续 quantile、代表路径和聚合结果都从合法样本开始生成；CLI 客户端继续严格拒绝服务协议错误，不做客户端掩盖。修复前先用回归测试证明当前实现会失败，修复后在 187 重启服务并对同一冻结实验目录重跑。

**Tech Stack:** Python 3、NumPy、pandas、KronosPredictor、FastAPI/Uvicorn、remote SSH、stock_research frozen-evaluation CLI、pytest。

---

### Task 1: Freeze the reproduced defect and add a failing regression test

**Files:**
- Modify on 187: `/home/mqkj/kronos/tests/test_kronos_predict.py`
- Inspect on 187: `/home/mqkj/kronos/service/raw_predictor.py`

- [ ] **Step 1: Add a test that feeds one generated sample with invalid OHLC and asserts the returned path is projected.**

The test must use a deterministic fake predictor whose `generate()` returns shape `(1, 1, 1, 6)` with `open=10`, `high=9`, `low=9.5`, `close=11`, `volume=100`, and `amount=1000`. It calls `predict_with_samples(..., sample_count=1, pred_len=1)` and asserts the returned bar keeps `open==10`, `close==11`, has `high==11`, and has `low==9.5`.

- [ ] **Step 2: Run only the new test on 187 and confirm RED.**

Run from 187:

```bash
cd /home/mqkj/kronos
/home/mqkj/miniconda3/envs/kronos/bin/python -m pytest -q tests/test_kronos_predict.py -k ohlc
```

Expected before the fix: FAIL because the current inverse-normalized row returns `high=9` and `low=9.5` unchanged.

### Task 2: Implement the minimal source-level OHLC projection

**Files:**
- Modify on 187: `/home/mqkj/kronos/service/raw_predictor.py`
- Modify on 187: `/home/mqkj/kronos/tests/test_kronos_predict.py`

- [ ] **Step 1: Add a focused helper after `_validate_generated()`.**

Implement:

```python
def _project_ohlc(row: dict[str, Any]) -> None:
    open_value = float(row["open"])
    close_value = float(row["close"])
    row["high"] = max(float(row["high"]), open_value, close_value)
    row["low"] = min(float(row["low"]), open_value, close_value)
```

- [ ] **Step 2: Call `_project_ohlc(bar)` immediately after the six inverse-normalized fields are assigned and before the bar is appended to the path.**

Do not alter timestamps, open/close, sample count, seed, model generation, quantile calculation, or client validation.

- [ ] **Step 3: Run the focused test and the remote Kronos unit tests.**

Run:

```bash
cd /home/mqkj/kronos
/home/mqkj/miniconda3/envs/kronos/bin/python -m pytest -q tests/test_kronos_predict.py -k ohlc
/home/mqkj/miniconda3/envs/kronos/bin/python -m pytest -q tests/test_kronos_predict.py
```

Expected: the focused test and the existing helper tests pass.

### Task 3: Deploy safely and verify service identity/output contract

**Files/artifacts:**
- Remote service process at `192.168.3.187:8123` for Kronos-small.
- Remote temporary service process at `192.168.3.187:8124` for Kronos-base.
- Preserve service logs and health responses in the evaluation operation record; do not store the token.

- [ ] **Step 1: Record the current 8123 authenticated health and GPU state before restart.**

Confirm the normalized model is `small`, loaded on CUDA, and record `nvidia-smi` without exposing credentials.

- [ ] **Step 2: Stop only the current Kronos service process and restart 8123 from the patched `/home/mqkj/kronos` tree.**

Use the existing Uvicorn command and keep the production port at 8123. Do not stop any unrelated process.

- [ ] **Step 3: Authenticate the restarted 8123 health endpoint and run one known previously failing snapshot.**

The previous failing input is asset `CN:SH:600030`, origin `2025-01-21`, model `small`; require `sample_count=20`, 10 complete timestamps, and every representative bar to satisfy `high >= max(open, close)` and `low <= min(open, close)`.

- [ ] **Step 4: Start 8124 with `KRONOS_MODEL_NAME=Kronos-base` only after the 8123 gate passes.**

Authenticate 8124 as `base`, run the same one-snapshot preflight, and stop 8124 after the base run. Never fallback between model identities.

### Task 4: Re-run the frozen 20-stock rolling evaluation

**Files/artifacts:**
- Reuse frozen inputs: `outputs/research/kronos_rolling_eval/2025-01/input_snapshots/`.
- Write a new immutable result directory: `outputs/research/kronos_rolling_eval/2025-01-rerun-ohlc-fix/`.

- [ ] **Step 1: Copy only the prepared frozen experiment inputs into the new result directory without querying PostgreSQL again.**

The rerun must retain the same 20 assets, 360 snapshot keys, input fingerprints, 250-bar window, 10-bar horizon, four evaluation horizons, seed `20260806`, and sample count 20.

- [ ] **Step 2: Run small against authenticated 8123 and base against authenticated 8124 using the same output directory.**

Do not use `--allow-smoke`; do not write predictions to the dashboard or production cache.

- [ ] **Step 3: Generate the report and verify all 720 model rows are terminal.**

The report must include coverage, h=1/3/5/10 metrics, persistence/drift baselines, paired small/base comparison, latency, model identity, and any remaining protocol errors.

### Task 5: Final verification and handoff

**Files:**
- Report: `outputs/research/kronos_rolling_eval/2025-01-rerun-ohlc-fix/report.md`
- Manifest: `outputs/research/kronos_rolling_eval/2025-01-rerun-ohlc-fix/run_manifest.csv`
- Comparison: `outputs/research/kronos_rolling_eval/2025-01-rerun-ohlc-fix/model_comparison.csv`

- [ ] **Step 1: Re-run the 187 service unit tests and local evaluation tests.**
- [ ] **Step 2: Audit that no successful row violates OHLC invariants and that no model identity mismatch occurred.**
- [ ] **Step 3: Confirm 8123 is restored as Kronos-small and 8124 is stopped after the base rerun.**
- [ ] **Step 4: Run `git diff --check`, compileall, and inspect worktree status.**
- [ ] **Step 5: Report the rerun result honestly: distinguish model accuracy from service-output coverage and state whether the acceptance gate is proven.**
