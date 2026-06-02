# Watchlist Diagnostics Data Enrichment v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich watchlist diagnostics with real Dragon / LHB / failure-event inputs so `must_watch` is driven by recent case-aligned signals instead of placeholders.

**Architecture:** Keep the existing diagnostics classifier and CLI/report contracts intact, but enrich the workflow layer with real `asset_id -> ts_code` mapping and 20-trading-day recent-event attachment from existing research outputs. This approach reuses the case library and LHB diagnostics already built, avoids inventing a new event detector, and isolates the new logic in watchlist-owned helpers.

**Tech Stack:** Python, pandas, Postgres via existing db helpers, CSV research artifacts in `outputs/research`, pytest.

---

## File Structure

- Modify: `src/stock_research/watchlist/workflow.py`
  - Add asset master mapping and recent-event enrichment helpers.
- Modify: `src/stock_research/watchlist/diagnostics.py`
  - Ensure enriched fields are preserved and used by the existing rule logic.
- Modify: `tests/test_watchlist_workflow.py`
  - Add RED/GREEN coverage for `asset_id -> ts_code`, 20-day event selection, and fallback behavior.
- Modify: `tests/test_watchlist_diagnostics.py`
  - Add RED/GREEN coverage that real enriched fields affect `risk_watch` / `opportunity_watch`.
- Optional diagnostic verification only: use real CLI output under `outputs/research/`.

## Task 1: Add failing enrichment tests

**Files:**
- Modify: `tests/test_watchlist_workflow.py`
- Modify: `tests/test_watchlist_diagnostics.py`

- [ ] **Step 1: Write the failing workflow test for `asset_id -> ts_code` enrichment**

```python
def test_build_watchlist_diagnostics_snapshot_maps_asset_to_ts_code(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_asset_identity_map",
        lambda asset_ids: pd.DataFrame(
            [{"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "stock_name": "深中华A"}]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_recent_case_event_frame",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_recent_lhb_event_frame",
        lambda **kwargs: pd.DataFrame(),
    )

    result = build_watchlist_diagnostics_snapshot(trade_date="2026-05-20")

    assert result["full"].iloc[0]["ts_code"] == "000017.SZ"
    assert result["full"].iloc[0]["stock_name"] == "深中华A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_workflow.py::test_build_watchlist_diagnostics_snapshot_maps_asset_to_ts_code`

Expected: FAIL because the enrichment helpers or fields do not exist yet.

- [ ] **Step 3: Write the failing workflow test for 20-trading-day recent-event attachment**

```python
def test_build_watchlist_diagnostics_snapshot_attaches_latest_event_within_20_days(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_asset_identity_map",
        lambda asset_ids: pd.DataFrame(
            [{"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "stock_name": "深中华A"}]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_recent_case_event_frame",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "ts_code": "000017.SZ",
                    "stock_name": "深中华A",
                    "event_date": "2026-05-06",
                    "verified_case_type_v2_1": "failed_second_wave",
                    "success_or_failure": "failure",
                    "event_type": "peak",
                    "confidence": 0.8,
                },
                {
                    "ts_code": "000017.SZ",
                    "stock_name": "深中华A",
                    "event_date": "2026-05-19",
                    "verified_case_type_v2_1": "failed_reversal",
                    "success_or_failure": "failure",
                    "event_type": "reversal",
                    "confidence": 0.9,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_recent_lhb_event_frame",
        lambda **kwargs: pd.DataFrame(),
    )

    result = build_watchlist_diagnostics_snapshot(trade_date="2026-05-20")

    row = result["full"].iloc[0]
    assert row["event_structure"] == "failed_reversal"
    assert bool(row["failure_flag"]) is True
    assert row["case_event_type"] == "reversal"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_workflow.py::test_build_watchlist_diagnostics_snapshot_attaches_latest_event_within_20_days`

Expected: FAIL because the workflow does not yet attach real recent events.

- [ ] **Step 5: Write the failing diagnostics test for enriched risk/opportunity signals**

```python
def test_build_watchlist_diagnostics_uses_real_enriched_fields_for_grouping():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0, "ts_code": "000017.SZ", "stock_name": "深中华A"},
            {"trade_date": "2026-05-20", "asset_id": "CN:SH:600118", "rank": 2, "score_total": 88.0, "ts_code": "600118.SH", "stock_name": "中国卫星"},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "amount_vs_20d": 4.5, "high_to_close_drawdown": 0.10, "volatility_5d": 0.12},
            {"asset_id": "CN:SH:600118", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "dragon_risk_score": 0.80, "overheat_avoid": True, "crowded_late_entry": True},
            {"asset_id": "CN:SH:600118", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
        ]
    )
    lhb_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "lhb_risk_score": 0.70, "lhb_negative_net_buy": True, "lhb_institution_selling": True},
            {"asset_id": "CN:SH:600118", "lhb_risk_score": 0.10, "lhb_negative_net_buy": False, "lhb_institution_selling": False},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "event_structure": "failed_second_wave", "failure_flag": True},
            {"asset_id": "CN:SH:600118", "event_structure": "second_wave_candidate", "failure_flag": False},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["CN:SZ:000017", "watch_group"] == "risk_watch"
    assert full.loc["CN:SH:600118", "watch_group"] == "opportunity_watch"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py::test_build_watchlist_diagnostics_uses_real_enriched_fields_for_grouping`

Expected: FAIL because the current workflow does not supply these real fields yet.

- [ ] **Step 7: Commit**

```bash
git add tests/test_watchlist_workflow.py tests/test_watchlist_diagnostics.py
git commit -m "test: add watchlist diagnostics enrichment coverage"
```

## Task 2: Add asset identity and recent-event helpers

**Files:**
- Modify: `src/stock_research/watchlist/workflow.py`
- Test: `tests/test_watchlist_workflow.py`

- [ ] **Step 1: Implement asset master identity loader**

```python
def _load_asset_identity_map(
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    columns = ["asset_id", "ts_code", "stock_name"]
    if not asset_ids:
        return pd.DataFrame(columns=columns)
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, ts_code, name
        FROM core.asset_master
        WHERE asset_id IN ({placeholders})
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, asset_ids)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame = frame.rename(columns={"name": "stock_name"})
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    return frame.loc[:, columns].drop_duplicates(subset=["asset_id"], keep="first").reset_index(drop=True)
```

- [ ] **Step 2: Implement recent case-event loader**

```python
def _load_recent_case_event_frame(
    *,
    trade_date: str,
    ts_codes: list[str],
    lookback_days: int = 20,
    path: str = "/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_failure_v2_1.csv",
) -> pd.DataFrame:
    columns = [
        "ts_code",
        "stock_name",
        "event_date",
        "verified_case_type_v2_1",
        "success_or_failure",
        "event_type",
        "confidence",
    ]
    if not ts_codes:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path)
    frame["ts_code"] = frame["ts_code"].astype(str).str.upper()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
    current = pd.Timestamp(trade_date)
    start = current - pd.tseries.offsets.BDay(lookback_days)
    frame = frame[
        frame["ts_code"].isin({code.upper() for code in ts_codes})
        & frame["event_date"].notna()
        & (frame["event_date"] <= current)
        & (frame["event_date"] >= start)
    ].copy()
    return frame.loc[:, columns].sort_values(["ts_code", "event_date"]).reset_index(drop=True)
```

- [ ] **Step 3: Implement recent LHB-event loader**

```python
def _load_recent_lhb_event_frame(
    *,
    trade_date: str,
    ts_codes: list[str],
    lookback_days: int = 20,
    path: str = "/Users/xiwei/stock_research/outputs/research/lhb_risk_feature_case_detail_v2_1.csv",
) -> pd.DataFrame:
    columns = [
        "ts_code",
        "stock_name",
        "event_date",
        "lhb_risk_score",
        "lhb_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "lhb_after_event_attention",
        "lhb_risk_level",
    ]
    if not ts_codes:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path)
    frame["ts_code"] = frame["ts_code"].astype(str).str.upper()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
    current = pd.Timestamp(trade_date)
    start = current - pd.tseries.offsets.BDay(lookback_days)
    frame = frame[
        frame["ts_code"].isin({code.upper() for code in ts_codes})
        & frame["event_date"].notna()
        & (frame["event_date"] <= current)
        & (frame["event_date"] >= start)
    ].copy()
    return frame.loc[:, [column for column in columns if column in frame.columns]].sort_values(
        ["ts_code", "event_date"]
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run workflow tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_workflow.py -k "maps_asset_to_ts_code or attaches_latest_event_within_20_days"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/watchlist/workflow.py tests/test_watchlist_workflow.py
git commit -m "feat: add watchlist diagnostics enrichment loaders"
```

## Task 3: Attach latest enriched records to candidates

**Files:**
- Modify: `src/stock_research/watchlist/workflow.py`
- Test: `tests/test_watchlist_workflow.py`

- [ ] **Step 1: Implement latest-record selection helpers**

```python
def _latest_per_ts_code(frame: pd.DataFrame, *, date_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    ordered = frame.sort_values(["ts_code", date_column])
    return ordered.drop_duplicates(subset=["ts_code"], keep="last").reset_index(drop=True)


def _attach_identity_and_events(
    *,
    top_scores: pd.DataFrame,
    asset_identity: pd.DataFrame,
    case_events: pd.DataFrame,
    lhb_events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    enriched_scores = top_scores.merge(asset_identity, on="asset_id", how="left")
    latest_case = _latest_per_ts_code(case_events, date_column="event_date")
    latest_lhb = _latest_per_ts_code(lhb_events, date_column="event_date")
    event_frame = latest_case.rename(
        columns={
            "verified_case_type_v2_1": "event_structure",
            "event_date": "case_event_date",
            "event_type": "case_event_type",
            "confidence": "case_confidence",
        }
    )
    event_frame["failure_flag"] = event_frame["success_or_failure"].eq("failure")
    lhb_frame = latest_lhb.rename(columns={"event_date": "lhb_event_date"})
    return enriched_scores, event_frame, lhb_frame
```

- [ ] **Step 2: Wire the helpers into `build_watchlist_diagnostics_snapshot(...)`**

```python
asset_identity = _load_asset_identity_map(asset_ids)
ts_codes = asset_identity["ts_code"].dropna().astype(str).tolist()
case_events = _load_recent_case_event_frame(trade_date=trade_date, ts_codes=ts_codes)
lhb_events = _load_recent_lhb_event_frame(trade_date=trade_date, ts_codes=ts_codes)
top_scores, event_frame, lhb_frame = _attach_identity_and_events(
    top_scores=top_scores,
    asset_identity=asset_identity,
    case_events=case_events,
    lhb_events=lhb_events,
)
```

- [ ] **Step 3: Ensure `stock_name` and `ts_code` are preserved into diagnostics outputs**

```python
for required in ("asset_id", "ts_code", "stock_name"):
    if required not in top_scores.columns:
        top_scores[required] = pd.Series(dtype="object")
```

- [ ] **Step 4: Run workflow tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_workflow.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/watchlist/workflow.py tests/test_watchlist_workflow.py
git commit -m "feat: attach recent case and lhb events to watchlist candidates"
```

## Task 4: Carry through real Dragon / LHB / factor fields

**Files:**
- Modify: `src/stock_research/watchlist/workflow.py`
- Modify: `src/stock_research/watchlist/diagnostics.py`
- Test: `tests/test_watchlist_diagnostics.py`

- [ ] **Step 1: Expand factor frame to include `volatility_5d`**

```python
columns = ["asset_id", "amount_vs_20d", "high_to_close_drawdown", "volatility_5d"]
frame = frame[frame["feature_name"].isin({"amount_vs_20d", "high_to_close_drawdown", "volatility_5d"})]
```

- [ ] **Step 2: Map case-event fields into diagnostics inputs**

```python
event_frame = event_frame.rename(
    columns={
        "verified_case_type_v2_1": "event_structure",
    }
)
event_frame["failure_flag"] = event_frame["success_or_failure"].eq("failure")
```

- [ ] **Step 3: Map LHB fields into diagnostics inputs**

```python
lhb_frame = lhb_frame.rename(
    columns={
        "lhb_risk_score": "lhb_risk_score",
        "lhb_negative_net_buy": "lhb_negative_net_buy",
        "lhb_institution_selling": "lhb_institution_selling",
        "lhb_high_pump_risk": "lhb_high_pump_risk",
        "lhb_after_event_attention": "lhb_after_event_attention",
        "lhb_risk_level": "lhb_risk_level",
    }
)
```

- [ ] **Step 4: Add `stock_name`, `ts_code`, and case metadata to diagnostics defaults/preservation**

```python
def _classification_defaults() -> dict[str, Any]:
    return {
        **_dragon_defaults(),
        **_lhb_defaults(),
        **_event_defaults(),
        "ts_code": "",
        "stock_name": "",
        "case_event_date": "",
        "case_event_type": "",
        "case_confidence": 0.0,
        "volatility_5d": 0.0,
        "amount_vs_20d": 0.0,
        "high_to_close_drawdown": 0.0,
    }
```

- [ ] **Step 5: Run diagnostics tests**

Run: `./.venv/bin/pytest -q tests/test_watchlist_diagnostics.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/watchlist/workflow.py src/stock_research/watchlist/diagnostics.py tests/test_watchlist_diagnostics.py
git commit -m "feat: enrich watchlist diagnostics with real dragon and lhb fields"
```

## Task 5: Real-date smoke verification

**Files:**
- Modify: none
- Output only: `outputs/research/`

- [ ] **Step 1: Run the real diagnostics CLI**

Run:

```bash
./.venv/bin/stock-research build-watchlist-diagnostics \
  --trade-date 2026-05-19 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research
```

Expected:
- command exits successfully
- full CSV path printed
- must-watch CSV path printed
- markdown path printed

- [ ] **Step 2: Inspect must-watch non-emptiness**

Run:

```bash
./.venv/bin/python - <<'PY'
import pandas as pd
full = pd.read_csv("outputs/research/watchlist_diagnostics_2026-05-19_diagnostics_v1.csv")
must_watch = pd.read_csv("outputs/research/watchlist_diagnostics_must_watch_2026-05-19_diagnostics_v1.csv")
print({"full_rows": len(full), "must_watch_rows": len(must_watch)})
print(full["watch_group"].value_counts(dropna=False).to_dict())
PY
```

Expected:
- diagnostics file contains real `ts_code`, `stock_name`, `event_structure`
- `must_watch_rows` is no longer systematically zero when recent matching cases exist

- [ ] **Step 3: Commit**

```bash
git add outputs/research/watchlist_diagnostics_2026-05-19_diagnostics_v1.csv \
        outputs/research/watchlist_diagnostics_must_watch_2026-05-19_diagnostics_v1.csv \
        outputs/research/watchlist_diagnostics_2026-05-19_diagnostics_v1.md
git commit -m "chore: verify watchlist diagnostics enrichment on real trade date"
```

## Task 6: Full verification

**Files:**
- Modify: none
- Test: `tests/test_watchlist_diagnostics.py`
- Test: `tests/test_watchlist_workflow.py`
- Test: `tests/test_watchlist_report.py`
- Test: `tests/test_watchlist_cli.py`

- [ ] **Step 1: Run watchlist-focused suite**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_watchlist_diagnostics.py \
  tests/test_watchlist_workflow.py \
  tests/test_watchlist_report.py \
  tests/test_watchlist_cli.py
```

Expected: PASS

- [ ] **Step 2: Run full suite**

Run:

```bash
./.venv/bin/pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/stock_research/watchlist/diagnostics.py \
        src/stock_research/watchlist/workflow.py \
        tests/test_watchlist_diagnostics.py \
        tests/test_watchlist_workflow.py \
        outputs/research/watchlist_diagnostics_2026-05-19_diagnostics_v1.csv \
        outputs/research/watchlist_diagnostics_must_watch_2026-05-19_diagnostics_v1.csv \
        outputs/research/watchlist_diagnostics_2026-05-19_diagnostics_v1.md
git commit -m "feat: enrich watchlist diagnostics with real case and lhb inputs"
```

## Self-Review

- Spec coverage:
  - `asset_id -> ts_code` mapping: covered by Tasks 1-3
  - 20-trading-day recent-event alignment: covered by Tasks 1-3
  - real Dragon/LHB/failure enrichment: covered by Tasks 3-4
  - `stock_name` and `volatility_5d`: covered by Task 4
  - real-date smoke verification: covered by Task 5
- Placeholder scan:
  - no `TODO` / `TBD` placeholders remain
  - all code-changing tasks include concrete code and commands
- Type consistency:
  - `build_watchlist_diagnostics_snapshot`, `_load_asset_identity_map`, `_load_recent_case_event_frame`, and `_load_recent_lhb_event_frame` are named consistently throughout the plan
