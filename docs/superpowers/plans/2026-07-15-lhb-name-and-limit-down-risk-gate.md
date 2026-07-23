# LHB Name and Limit-Down Risk Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure LHB review artifacts display authoritative Chinese stock names and exclude near-limit-down candidates from Top5 while preserving their raw scores as auditable risk-watch rows.

**Architecture:** Add a small pure policy module that classifies A-share price-limit regimes and applies the Top5 eligibility gate. Extend asset-name synchronization to upsert missing securities, then enrich LHB publish inputs with source names and daily percentage change before ranking. Published `stock_name` and risk-audit fields remain authoritative for the dashboard, whose existing reader already preserves artifact names.

**Tech Stack:** Python 3, pandas, PostgreSQL SQL, pytest, existing `stock_research` strategy EOD publisher.

---

## File map

- Create `src/stock_research/lhb_review_policy.py`: pure name validation, price-limit regime classification, near-limit-down threshold evaluation, and Top5 gate/reranking.
- Create `tests/test_lhb_review_policy.py`: boundary and ranking tests for the pure policy.
- Modify `src/stock_research/core_data.py`: replace update-only Chinese-name sync with idempotent public/core upserts.
- Modify `tests/test_core_data.py`: prove inserts, updates, board flags, and idempotent conflict behavior are represented in SQL.
- Modify `src/stock_research/strategy_eod_publish.py`: load LHB source names and `pct_chg`, resolve display names, apply policy after raw scoring, and publish audit fields.
- Modify `tests/test_strategy_eod_publish.py`: prove name precedence, LHB fallback, raw-score preservation, risk downgrade, and Top5 refill.
- Modify `tests/test_dashboard_review_queue.py`: prove an artifact-provided name wins even when asset master has no row.
- Regenerate `outputs/research/strategy_daily_eod/2026-07-14/strategy_lhb_shortline_review.csv` and related score-audit outputs through the official publisher; do not edit generated CSVs manually.

### Task 1: Upsert missing securities during Chinese-name synchronization

**Files:**
- Modify: `tests/test_core_data.py`
- Modify: `src/stock_research/core_data.py:92-144`

- [ ] **Step 1: Change the existing test to require public and core upserts**

Replace the update-only assertions with assertions that both SQL statements insert full identity fields and update on conflict:

```python
def test_sync_chinese_stock_names_from_akshare_upserts_public_and_core(monkeypatch):
    conn = FakeConnection()

    class FakeAk:
        @staticmethod
        def stock_info_a_code_name():
            import pandas as pd
            return pd.DataFrame([
                {"code": "001399", "name": "惠科股份"},
                {"code": "688001", "name": "华兴源创"},
            ])

    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "ak", FakeAk)

    assert core_data.sync_chinese_stock_names_from_akshare(conn) == 2
    public_sql, public_rows = conn.executed_many[0]
    core_sql, core_rows = conn.executed_many[1]
    assert "INSERT INTO asset_master" in public_sql
    assert "ON CONFLICT (asset_id) DO UPDATE" in public_sql
    assert "INSERT INTO core.asset_master" in core_sql
    assert "ON CONFLICT (asset_id) DO UPDATE" in core_sql
    assert "is_star" in core_sql
    assert public_rows[0] == (
        "CN:SZ:001399", core_data.SETTINGS.default_market, "001399", "SZ",
        "惠科股份", core_data.SETTINGS.default_currency,
    )
    assert core_rows[1] == (
        "CN:SH:688001", "688001.SH", "688001", "688001", "华兴源创",
        "SH", "STAR", True, False, True, False,
    )
```

- [ ] **Step 2: Run the test and verify RED**

Run: `rtk pytest -q tests/test_core_data.py::test_sync_chinese_stock_names_from_akshare_upserts_public_and_core`

Expected: FAIL because current SQL uses `UPDATE` and normalized rows contain only three fields.

- [ ] **Step 3: Expand normalized rows and implement two idempotent upserts**

Make `_normalize_akshare_code_name_rows` return `(asset_id, symbol, name, exchange, ts_code)`. Derive separate public and core tuples in Python, including board flags. Use SQL shaped as follows:

```python
public_sql = """
INSERT INTO asset_master (
    asset_id, market, symbol, exchange, name, currency, status, source, updated_at
)
VALUES (%s, %s, %s, %s, %s, %s, 'listed', 'akshare:stock_info_a_code_name', now())
ON CONFLICT (asset_id) DO UPDATE SET
    market = EXCLUDED.market,
    symbol = EXCLUDED.symbol,
    name = EXCLUDED.name,
    exchange = EXCLUDED.exchange,
    currency = EXCLUDED.currency,
    updated_at = now()
"""
core_sql = """
INSERT INTO core.asset_master (
    asset_id, ts_code, akshare_code, symbol, name, exchange, board,
    is_active, is_beijing, is_star, is_chinext, source, updated_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        'akshare:stock_info_a_code_name', now())
ON CONFLICT (asset_id) DO UPDATE SET
    ts_code = EXCLUDED.ts_code,
    akshare_code = EXCLUDED.akshare_code,
    symbol = EXCLUDED.symbol,
    name = EXCLUDED.name,
    exchange = EXCLUDED.exchange,
    board = EXCLUDED.board,
    is_active = true,
    is_beijing = EXCLUDED.is_beijing,
    is_star = EXCLUDED.is_star,
    is_chinext = EXCLUDED.is_chinext,
    updated_at = now()
"""
```

Build public tuples as `(asset_id, SETTINGS.default_market, symbol, exchange, name, SETTINGS.default_currency)` and core tuples as `(asset_id, ts_code, symbol, symbol, name, exchange, board, True, is_beijing, is_star, is_chinext)`. Preserve existing list/delist metadata on conflict by not updating those columns.

- [ ] **Step 4: Run focused and module tests**

Run: `rtk pytest -q tests/test_core_data.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/core_data.py tests/test_core_data.py
rtk git commit -m "fix: upsert missing Chinese stock names"
```

### Task 2: Implement the pure LHB review risk policy

**Files:**
- Create: `src/stock_research/lhb_review_policy.py`
- Create: `tests/test_lhb_review_policy.py`

- [ ] **Step 1: Write price-limit boundary tests**

```python
import pandas as pd
from stock_research.lhb_review_policy import classify_price_limit, apply_lhb_top5_gate

def test_classify_price_limit_regimes_and_boundaries():
    cases = [
        ("CN:SZ:001399", "惠科股份", -9.50, "main_board", -9.50, True),
        ("CN:SZ:001399", "惠科股份", -9.49, "main_board", -9.50, False),
        ("CN:SZ:000078", "ST海王", -4.80, "st", -4.80, True),
        ("CN:SZ:300001", "特锐德", -19.00, "chinext", -19.00, True),
        ("CN:SH:688001", "华兴源创", -19.00, "star", -19.00, True),
        ("CN:BJ:920001", "北交样本", -29.00, "beijing", -29.00, True),
    ]
    for asset_id, name, pct_chg, regime, threshold, gated in cases:
        decision = classify_price_limit(asset_id=asset_id, stock_name=name, pct_chg=pct_chg)
        assert decision.regime == regime
        assert decision.threshold == threshold
        assert decision.near_limit_down is gated

def test_missing_pct_change_is_not_gated_but_is_auditable():
    decision = classify_price_limit(asset_id="CN:SZ:001399", stock_name="惠科股份", pct_chg=None)
    assert decision.near_limit_down is False
    assert decision.data_status == "pct_chg_missing"
```

- [ ] **Step 2: Write ranking and raw-score preservation tests**

```python
def test_gate_downgrades_limit_down_candidate_and_refills_top5():
    frame = pd.DataFrame([
        {"asset_id": f"CN:SZ:00000{i}", "stock_name": f"股票{i}", "score_total": 80 - i, "pct_chg": 1.0}
        for i in range(1, 7)
    ])
    frame.loc[3, ["asset_id", "stock_name", "pct_chg"]] = ["CN:SZ:001399", "惠科股份", -9.99]

    result = apply_lhb_top5_gate(frame)
    gated = result.loc[result["asset_id"].eq("CN:SZ:001399")].iloc[0]
    assert gated["raw_score"] == gated["score_total"]
    assert gated["top5_eligible"] is False
    assert gated["review_tier"] == "risk_watch"
    assert gated["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert len(result.loc[result["review_tier"].eq("top5_focus")]) == 5
    assert "CN:SZ:000006" in set(result.loc[result["review_tier"].eq("top5_focus"), "asset_id"])
```

- [ ] **Step 3: Run the tests and verify RED**

Run: `rtk pytest -q tests/test_lhb_review_policy.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the policy module**

Implement these stable interfaces:

```python
@dataclass(frozen=True)
class PriceLimitDecision:
    regime: str
    threshold: float
    near_limit_down: bool
    data_status: str

def is_valid_stock_name(value: object, *, asset_id: str = "") -> bool: ...

def classify_price_limit(
    *, asset_id: str, stock_name: object, pct_chg: object
) -> PriceLimitDecision: ...

def apply_lhb_top5_gate(frame: pd.DataFrame, *, top_n: int = 5) -> pd.DataFrame: ...
```

Classification order must be ST name first, then Beijing (`CN:BJ`, `.BJ`, or 43/83/87/92 prefix), STAR (688 prefix), ChiNext (300/301/302 prefix), else main board. `apply_lhb_top5_gate` sorts by numeric `score_total` descending and `asset_id` ascending, retains all rows, assigns ranks only after sorting, and assigns `top5_focus`, `watch`, or `risk_watch` without using future data.

- [ ] **Step 5: Run policy tests**

Run: `rtk pytest -q tests/test_lhb_review_policy.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
rtk git add src/stock_research/lhb_review_policy.py tests/test_lhb_review_policy.py
rtk git commit -m "feat: gate near-limit-down LHB candidates"
```

### Task 3: Enrich LHB publication with names and close-state risk data

**Files:**
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `src/stock_research/strategy_eod_publish.py:753-920`
- Modify: `src/stock_research/strategy_eod_publish.py:1016-1050`

- [ ] **Step 1: Add a failing publication test for the 2026-07-14 shape**

Build an LHB result with six candidates and monkeypatch `_lhb_base_score_lookup_for_trade_date` to return payloads containing `stock_name`, `pct_chg`, and scores. Assert:

```python
assert row_001399["stock_name"] == "惠科股份"
assert row_001399["score_total"] == pytest.approx(69.3698)
assert row_001399["raw_score"] == pytest.approx(69.3698)
assert row_001399["review_tier"] == "risk_watch"
assert row_001399["risk_gate_code"] == "near_limit_down_followthrough_risk"
assert review.loc[review["review_tier"].eq("top5_focus"), "asset_id"].nunique() == 5
```

Also add a name precedence test where candidate name wins over master/LHB lookup, master wins when candidate is blank, and same-day LHB name wins when master is missing.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `rtk pytest -q tests/test_strategy_eod_publish.py -k 'lhb and (name or limit_down or refill)'`

Expected: FAIL because current output has no `stock_name` or risk audit columns and ranks all candidates by score alone.

- [ ] **Step 3: Extend the LHB source query and lookup payload**

Change `_load_lhb_base_score_source_frames` so the LHB frame includes:

```sql
COALESCE(NULLIF(a.name, ''), NULLIF(t.name, '')) AS stock_name,
d.pct_chg
```

with joins to same-day `market.lhb_top_list_daily t` on `trade_date` and `ts_code`, and same-day `market_daily_bar d` through the resolved asset ID with `adjust_type = 'hfq'`. Aggregate or deduplicate same-day LHB rows before joining so one security produces one score row.

Add `stock_name` and `pct_chg` to `_lhb_base_score_lookup_for_trade_date` payloads. Preserve normalized and raw asset lookup keys.

- [ ] **Step 4: Publish resolved names and apply the gate**

Import `is_valid_stock_name` and `apply_lhb_top5_gate`. Extend review columns with:

```python
"stock_name", "raw_score", "top5_eligible", "risk_gate_code",
"risk_gate_reason", "price_limit_regime",
"near_limit_down_threshold", "pct_chg",
```

For LHB rows, resolve name in this order: valid row name, lookup payload name (already `core` then LHB), then normalized code/asset ID. Populate `pct_chg` from the lookup. After collecting rows, call `apply_lhb_top5_gate(review)` instead of assigning Top5 by rank alone. Do not apply the policy to other strategies.

The gate may refill only from rows already present in the strategy's own candidate frame. Do not expand the candidate frame from the broader base-score universe, because those securities may not have passed the lifecycle, rule, or auction layers. If the strategy frame has fewer than five eligible rows after gating, publish fewer than five `top5_focus` rows.

- [ ] **Step 5: Run focused publication tests**

Run: `rtk pytest -q tests/test_strategy_eod_publish.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
rtk git add src/stock_research/strategy_eod_publish.py tests/test_strategy_eod_publish.py
rtk git commit -m "fix: publish LHB names and risk-gated Top5"
```

### Task 4: Lock dashboard behavior to artifact-provided names

**Files:**
- Modify: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Add the dashboard regression test**

```python
def test_attach_asset_names_keeps_published_lhb_name_when_master_missing(monkeypatch):
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})
    rows = review_queue._attach_asset_names([
        {"asset_id": "CN:SZ:001399", "stock_name": "惠科股份"}
    ])
    assert rows[0]["stock_name"] == "惠科股份"
```

- [ ] **Step 2: Run the test**

Run: `rtk pytest -q tests/test_dashboard_review_queue.py`

Expected: PASS with current reader behavior. If it fails, minimally adjust `_attach_asset_names` so a valid artifact name is never overwritten by master data.

- [ ] **Step 3: Commit the regression test**

```bash
rtk git add tests/test_dashboard_review_queue.py src/stock_research/dashboard/review_queue.py
rtk git commit -m "test: preserve published LHB stock names"
```

### Task 5: Run integrated verification and regenerate 2026-07-14 artifacts

**Files:**
- Generated: `outputs/research/strategy_daily_eod/2026-07-14/strategy_lhb_shortline_review.csv`
- Generated: `outputs/research/strategy_daily_eod/2026-07-14/strategy_score_audit_detail.csv`
- Generated as selected by publisher: other 2026-07-14 strategy EOD manifests/summaries

- [ ] **Step 1: Run the focused suite**

Run:

```bash
rtk pytest -q \
  tests/test_core_data.py \
  tests/test_lhb_review_policy.py \
  tests/test_strategy_eod_publish.py \
  tests/test_dashboard_review_queue.py
```

Expected: all tests PASS.

- [ ] **Step 2: Run the broader strategy/dashboard regression suite**

Run:

```bash
rtk pytest -q \
  tests/test_strategy_daily_eod.py \
  tests/test_strategy_score_audit.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_readiness.py
```

Expected: all tests PASS.

- [ ] **Step 3: Synchronize current Chinese names**

Run the service function directly:

```bash
rtk python -c "from stock_research.core_data import sync_chinese_stock_names_from_akshare_for_service as run; print(run())"
```

Expected: a positive normalized-row count and no SQL error. Verify both tables:

```sql
SELECT asset_id, ts_code, name FROM core.asset_master WHERE asset_id = 'CN:SZ:001399';
SELECT asset_id, symbol, name FROM asset_master WHERE asset_id = 'CN:SZ:001399';
```

Expected name: `惠科股份` in both rows.

- [ ] **Step 4: Republish the target date through the official command**

Run:

```bash
rtk python -m stock_research.strategy_eod_publish \
  --trade-date 2026-07-14 \
  --output-root outputs
```

Expected: JSON summary with successful LHB strategy publication and review artifact path under `2026-07-14`.

- [ ] **Step 5: Verify the regenerated artifacts programmatically**

Run:

```bash
rtk python -c "import pandas as pd; p='outputs/research/strategy_daily_eod/2026-07-14/strategy_lhb_shortline_review.csv'; d=pd.read_csv(p); r=d[d.asset_id.astype(str).str.contains('001399')].iloc[0]; print(r[['stock_name','score_total','raw_score','review_tier','risk_gate_code','pct_chg']].to_dict()); print(d[d.review_tier.eq('top5_focus')][['rank','stock_name','asset_id','score_total']].to_dict('records'))"
```

Expected:

- `stock_name == '惠科股份'`.
- `score_total` and `raw_score` remain approximately `69.3698`.
- `review_tier == 'risk_watch'`.
- `risk_gate_code == 'near_limit_down_followthrough_risk'`.
- Exactly five eligible rows are `top5_focus` when at least five eligible candidates exist.
- The previous sixth-ranked eligible candidate is present in Top5.

- [ ] **Step 6: Inspect worktree and commit only intentional source/test changes**

Run: `rtk git status --short`

Do not stage the pre-existing `tech_bottleneck_review_universe_frontend_*` changes. Check `rtk git ls-files outputs/research/strategy_daily_eod/2026-07-14`; if the regenerated files are tracked, review and commit only the LHB-related artifact diffs. If they are untracked, leave them as runtime evidence and report their paths.

- [ ] **Step 7: Run final verification before completion**

Run: `rtk git diff --check`

Expected: no whitespace errors. Record exact test counts, publisher status, and the 001399 artifact row in the final handoff.
