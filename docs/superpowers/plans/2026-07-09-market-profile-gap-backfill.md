# Market Profile Gap Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the Stock Workspace market profile gaps for `np_parent`, `region`, and `concept tags`, with repeatable audits and source-specific fallbacks.

**Architecture:** Keep the authoritative serving tables unchanged: `finance.income_statement.np_parent`, `core.asset_master.region`, and `core.concept_membership`. Add source-specific ingestion paths behind existing CLI commands, store raw vendor payloads where available, and use the audit command as the acceptance gate after each batch.

**Tech Stack:** Python, PostgreSQL, AkShare, Tushare where quota permits, pytest, existing `stock_research` CLI.

---

## Current Audit

Run:

```bash
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Current result from 2026-07-09:

```text
market_profile_audit|active_assets|5209|region_present|0|concept_present|3710|np_parent_present|294
```

Detailed gap query result:

```text
active_assets=5209
region_present=0
region_gap=5209
concept_present=3710
concept_gap=1499
np_parent_present=294
np_parent_gap=4915
profit_raw_assets=294
profit_raw_rows=294
```

Concept source coverage:

```text
em: 2144 memberships, 1710 assets, 27 concepts
ths: 9616 memberships, 3351 assets, 243 concepts
```

Observed concept gaps include regular listed companies, not only ST or recent IPOs, for example `000008 神州高铁`, `000026 飞亚达`, `000031 大悦城`, `000065 北方国际`.

## File Structure

- Modify: `src/stock_research/core_data.py`
  - Existing home for concept source adapters and concept daily bar derivation.
  - Add only concept-specific helpers when a source cannot fit the current adapter shape.
- Modify: `src/stock_research/market_profile_backfill.py`
  - Existing home for region, `np_parent`, and market profile audit backfills.
  - Add source-specific fallback helpers here for non-concept market profile fields.
- Modify: `src/stock_research/cli.py`
  - Existing CLI entry points for market profile backfills.
  - Expose batch controls and source selection through flags.
- Modify: `src/stock_research/stock_metadata_db_hydration.py`
  - Existing service wrapper used by cron and hydration jobs.
  - Keep no-proxy protection for public data sources.
- Test: `tests/test_core_data.py`
  - Unit coverage for source adapters, normalization, and no-erase behavior on vendor failures.
- Test: `tests/test_market_profile_backfill_cli.py`
  - CLI flag and service wiring coverage.
- Test: `tests/test_stock_metadata_db_hydration.py`
  - Service wrapper coverage.

## Task 1: Stabilize Concept Tag Sources

**Files:**
- Modify: `src/stock_research/core_data.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/stock_metadata_db_hydration.py`
- Test: `tests/test_core_data.py`
- Test: `tests/test_market_profile_backfill_cli.py`
- Test: `tests/test_stock_metadata_db_hydration.py`

- [ ] **Step 1: Verify the current concept gap**

Run:

```bash
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Expected current baseline before the next supplement source:

```text
market_profile_audit|active_assets|5209|region_present|0|concept_present|3710|np_parent_present|294
```

- [ ] **Step 2: Keep 同花顺 concept ingestion as the default broad source**

Ensure `sync_concept_memberships_from_akshare()` supports `concept_system="ths"` with:

```python
board_fetcher = ak.stock_board_concept_name_ths
constituent_fetcher = fetch_ths_concept_constituents_direct
board_source = "akshare:stock_board_concept_name_ths"
constituent_source = "ths:q.10jqka.com.cn_gn_detail"
```

Run:

```bash
rtk .venv/bin/pytest tests/test_core_data.py::test_sync_concept_memberships_from_akshare_defaults_to_ths_sources -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Keep 东方财富 concept ingestion as a supplementary source**

Ensure CLI can explicitly call:

```bash
rtk .venv/bin/python -m stock_research.cli sync-market-profile-concepts --concept-system em --max-concepts 50
```

Expected behavior:

```text
market_profile_concepts_synced|...
```

Failed vendor concepts may be reported, but existing memberships must not be erased when a source call fails.

- [ ] **Step 4: Add a targeted supplement source only for the remaining 1499 concept gaps**

Add a new adapter only if it returns stock-to-concept tags directly for currently missing assets. The adapter must normalize to the existing membership contract:

```python
{
    "asset_id": asset_id,
    "concept_system": source_name,
    "concept_code": concept_code,
    "concept_name": concept_name,
    "start_date": trade_date,
    "end_date": None,
    "source": source_label,
}
```

Add a test that uses a missing asset fixture and asserts one membership row is inserted without closing unrelated `ths` or `em` memberships.

Run:

```bash
rtk .venv/bin/pytest tests/test_core_data.py tests/test_market_profile_backfill_cli.py tests/test_stock_metadata_db_hydration.py -q
```

Expected:

```text
29 passed
```

- [ ] **Step 5: Accept concept coverage**

Run:

```bash
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Acceptance target:

```text
concept_present >= 5000
concept_gap <= 209
```

Any remaining gap must be exported as a CSV containing `symbol`, `name`, `exchange`, `list_date`, and the reason: vendor absent, ST/suspended/delisted naming issue, or unresolved source error.

## Task 2: Fill Region

**Files:**
- Modify: `src/stock_research/market_profile_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_market_profile_backfill.py`
- Test: `tests/test_market_profile_backfill_cli.py`

- [ ] **Step 1: Confirm current region gap**

Run:

```bash
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Expected current baseline:

```text
region_present|0
```

- [ ] **Step 2: Use Tushare `stock_basic` only when quota allows**

The wrapper must catch quota failures and produce a readable non-destructive failure message:

```text
market_profile_regions_synced|status|failed|error|...
```

Run:

```bash
rtk .venv/bin/python -m stock_research.cli sync-market-profile-regions
```

Expected on quota failure:

```text
status|failed
```

Expected on success:

```text
market_profile_regions_synced|assets|...
```

- [ ] **Step 3: Add an AkShare fallback for stock basic region**

If Tushare remains limited, implement a fallback based on AkShare stock info/basic data. The normalized update must only touch `core.asset_master.region` and must match by exchange plus six-digit symbol.

Add a test fixture with:

```python
[
    {"A股代码": "000001", "注册地址": "广东省深圳市罗湖区深南东路5047号"},
    {"A股代码": "600000", "注册地址": "上海市中山东一路12号"},
]
```

Assert:

```python
assert updated_assets == 2
```

Run:

```bash
rtk .venv/bin/pytest tests/test_market_profile_backfill.py::test_sync_regions_from_tushare_falls_back_to_akshare -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Accept region coverage**

Run:

```bash
rtk .venv/bin/python -m stock_research.cli sync-market-profile-regions
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Acceptance target:

```text
region_present >= 5000
region_gap <= 209
```

## Task 3: Scale `np_parent` Backfill

**Files:**
- Modify: `src/stock_research/core_data.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_core_data.py`
- Test: `tests/test_market_profile_backfill_cli.py`

- [ ] **Step 1: Keep raw payload persistence before normalized writes**

For each asset, persist the raw AkShare/东方财富 profit sheet payload to:

```text
raw_akshare.finance_payload
source_endpoint='stock_profit_sheet_by_report_em'
```

Then normalize `np_parent` into:

```text
finance.income_statement.np_parent
```

- [ ] **Step 2: Batch by missing assets**

Run small batches first:

```bash
rtk .venv/bin/python -m stock_research.cli sync-market-profile-np-parent --limit 25
```

Expected example:

```text
market_profile_np_parent_synced|assets|25|income_statement|2340|raw_payload|23|failed_assets|2
```

The command must not stop the whole batch because one stock fails.

- [ ] **Step 3: Add retry and skip semantics for vendor failures**

For each asset:

```python
try:
    fetch_once()
except Exception:
    retry_once()
except Exception:
    record_failed_asset(symbol)
    continue
```

Run:

```bash
rtk .venv/bin/pytest tests/test_core_data.py::test_sync_market_profile_np_parent_skips_failed_asset_after_retry -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Continue daily batches until coverage is acceptable**

Run:

```bash
rtk .venv/bin/python -m stock_research.cli sync-market-profile-np-parent --limit 100
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Acceptance target:

```text
np_parent_present >= 5000
np_parent_gap <= 209
```

If a vendor source does not return a profit sheet for a stock, export the symbol to a failure CSV with the error class and last attempted source.

## Task 4: Add a Unified Progress Report

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_market_profile_backfill_cli.py`

- [ ] **Step 1: Add a concise report command**

Add or extend the audit output so it includes present and missing counts for all three fields:

```text
market_profile_audit|active_assets|5209|region_present|0|region_gap|5209|concept_present|3710|concept_gap|1499|np_parent_present|294|np_parent_gap|4915
```

- [ ] **Step 2: Keep Feishu or cron messages readable**

If these commands are called by cron, report only aggregate counts:

```text
市场画像补全进度：
活跃沪深股票 5209 只
地区：已补 0，缺 5209
概念：已补 3710，缺 1499
归母净利润：已补 294，缺 4915
```

Do not emit per-stock failure spam into the group. Put detailed failures into a local artifact path and include only the path in the message.

- [ ] **Step 3: Verify report tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_market_profile_backfill_cli.py -q
```

Expected:

```text
all tests pass
```

## Final Verification

Run the complete focused suite:

```bash
rtk .venv/bin/pytest tests/test_market_profile_backfill.py tests/test_market_profile_backfill_cli.py tests/test_core_data.py tests/test_stock_metadata_db_hydration.py -q
```

Expected current result:

```text
29 passed, 2 warnings
```

Run the final data audit:

```bash
rtk .venv/bin/python -m stock_research.cli market-profile-audit
```

Acceptance target before declaring this complete:

```text
active_assets=5209
region_present >= 5000
concept_present >= 5000
np_parent_present >= 5000
```

## Self-Review

- Spec coverage: `np_parent`, `region`, and `concept tags` each have a separate ingestion and acceptance task.
- Placeholder scan: no unresolved marker text, no generic implementation steps, and each command has an expected output shape.
- Type consistency: plan uses the existing table names and field names verified in the current database: `list_date`, `concept_system`, `concept_code`, `concept_name`, `source`.
