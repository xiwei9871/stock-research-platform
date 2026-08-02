# Rolling Sector Oversold Gap Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 2026-07-21 至 2026-07-31 冻结回放中的 preflight gap 变成可审计、可重跑的数据库回填流程，并保证以后每日滚动运行不再因为同类缺口回退到长时间阻塞。

**Architecture:** 先做数据宇宙和资产代码的分类修复，不把所有 gap 直接当成外部下载任务；然后按行情、状态、板块衍生、财务、估值、指数六类执行独立回填。策略运行始终只读数据库，任何外部数据源只允许出现在独立 backfill/ingest 任务中，回填后由同一套 PIT preflight 和冻结回放验收。

**Tech Stack:** Python 3.14, pandas, psycopg/PostgreSQL, existing `stock_research` CLI, Baostock/Tushare/Eastmoney/AkShare adapters only inside ingestion jobs, pytest.

---

## Current diagnosis

The committed 2026-07-21 preflight artifact reports 3,750 gaps:

| Dataset | Gaps | First action |
| --- | ---: | --- |
| `market.concept_daily_bar` | 976 | repair active membership and rebuild derived bars |
| `valuation_history` | 706 | backfill `factor.factor_daily` valuation factors |
| `core.asset_status_daily` | 686 | rebuild from canonical daily bars |
| `market_daily_bar` | 686 | classify stale/unmapped assets, then backfill true active assets |
| `finance_history` | 673 | backfill PIT finance rows for active assets |
| `market.industry_daily_bar` | 21 | rebuild after membership and market bars |
| `market.index_daily_bar` | 2 | fill 252-session `STAR_50` and `BSE_50` history |

The 686 market/status asset IDs split into 367 assets absent from
`core.asset_master` and 319 assets present in the master. The 367 must not be
blindly downloaded. The 319 are the true first-pass data candidates; most are
`CN:BJ:920xxx`, for which the current `stock_qfq`/`stock_hfq` source services
have no `bj*` source tables. The existing concept normalizer also maps
`900xxx` B-share codes to `CN:BJ:900xxx`; that creates invalid asset IDs and
must be rejected before membership synchronization.

The 252-session replay window starts on 2025-05-28 for the 2026-07-21 anchor
and on 2025-06-10 for the 2026-07-31 anchor. The backfill scope for a complete
9-anchor replay is therefore 2025-05-28 through 2026-07-31.

## Task 1: Freeze and classify the gap workplan

**Files:**
- Create: `src/stock_research/rolling_oversold/gap_backfill.py`
- Create: `tests/test_rolling_oversold_gap_backfill.py`
- Create: `docs/superpowers/verification/2026-08-02-rolling-sector-oversold-gap-audit.md`

- [ ] **Step 1: Write the failing classifier test.**

Use a fixture containing the committed `preflight.json` shape and a mocked
asset-master lookup. The classifier must produce `invalid_membership` for an
asset missing from `core.asset_master`, `market_bar_backfill` for an eligible
asset with no cutoff bar, and preserve sector/index gap rows unchanged.

```python
def test_build_gap_workplan_separates_invalid_memberships_from_real_backfills():
    result = build_gap_workplan(
        gaps=[
            DataGap("market_daily_bar", "CN:BJ:900901", "2026-07-21", "2026-07-21", 1, 0, "missing_cutoff_bar"),
            DataGap("market_daily_bar", "CN:BJ:920001", "2026-07-21", "2026-07-21", 1, 0, "missing_cutoff_bar"),
            DataGap("market.index_daily_bar", "BSE_50", None, "2026-07-21", 252, 21, "insufficient_252_session_history"),
        ],
        asset_master={"CN:BJ:920001"},
    )
    assert result["invalid_membership"] == ["CN:BJ:900901"]
    assert result["market_bar_backfill"] == ["CN:BJ:920001"]
    assert result["index_backfill"] == ["BSE_50"]
```

- [ ] **Step 2: Run the focused test and verify it fails.**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_gap_backfill.py::test_build_gap_workplan_separates_invalid_memberships_from_real_backfills -q
```

Expected: `FAIL` because the classifier module does not exist.

- [ ] **Step 3: Implement the read-only workplan builder.**

Implement these exact interfaces:

```python
def load_preflight_gaps(path: str | Path) -> tuple[DataGap, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(DataGap(**row) for row in payload["gaps"])

def classify_asset_gap(
    *, dataset: str, asset_id: str, asset_master_present: bool,
    list_date: date | None, delist_date: date | None, cutoff: date,
) -> str:
    if not asset_master_present:
        return "invalid_membership"
    if dataset in {"market_daily_bar", "core.asset_status_daily"}:
        return "market_bar_backfill"
    if dataset == "finance_history":
        return "finance_backfill"
    if dataset == "valuation_history":
        return "valuation_backfill"
    if dataset == "market.index_daily_bar":
        return "index_backfill"
    return "derived_backfill"

def build_gap_workplan(
    *, gaps: Iterable[DataGap], asset_master: set[str],
    cutoff: date | None = None,
) -> dict[str, list[str]]:
    del cutoff
    workplan = {
        "invalid_membership": [], "market_bar_backfill": [],
        "finance_backfill": [], "valuation_backfill": [],
        "index_backfill": [], "derived_backfill": [],
    }
    for gap in gaps:
        key = gap.asset_id
        if gap.dataset == "market.index_daily_bar":
            bucket = "index_backfill"
        elif key is None:
            bucket = "derived_backfill"
        else:
            bucket = classify_asset_gap(
                dataset=gap.dataset, asset_id=key,
                asset_master_present=key in asset_master,
                list_date=None, delist_date=None, cutoff=date.max,
            )
        if key is not None and key not in workplan[bucket]:
            workplan[bucket].append(key)
    return {name: sorted(values) for name, values in workplan.items()}

def write_gap_workplan(workplan: dict[str, list[str]], output_dir: str | Path) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "gap_workplan.json"
    csv_path = root / "gap_workplan.csv"
    json_path.write_text(json.dumps(workplan, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [(bucket, value) for bucket, values in sorted(workplan.items()) for value in values]
    csv_path.write_text(
        "bucket,asset_or_key\n" + "\n".join(f"{bucket},{value}" for bucket, value in rows) + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "csv": str(csv_path)}
```

Do not write to PostgreSQL in this module. The output must include JSON and
CSV files with the original dataset, asset/sector key, reason, and proposed
next task. This keeps the first step reversible and auditable.

- [ ] **Step 4: Run the classifier tests.**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_gap_backfill.py -q
```

Expected: all classifier tests pass.

- [ ] **Step 5: Generate the real workplan without mutating the database.**

Read:

```text
artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research_v2/rolling_sector_oversold/blocked/anchor=2026-07-21/version=rolling_oversold_v1/preflight.json
```

Query `core.asset_master` for all asset gap IDs and write the audit under
`artifacts/rolling_sector_oversold/gap_workplan_2026-07-21/`. The audit must
report the 367 no-master assets separately from the 319 master-present assets
before any source request is made.

- [ ] **Step 6: Commit the audit tool.**

```bash
rtk git add src/stock_research/rolling_oversold/gap_backfill.py \
  tests/test_rolling_oversold_gap_backfill.py \
  docs/superpowers/verification/2026-08-02-rolling-sector-oversold-gap-audit.md
rtk git commit -m "feat: classify rolling oversold data gaps"
```

## Task 2: Repair asset-code normalization and active membership universe

**Files:**
- Modify: `src/stock_research/core_data.py:_asset_id_from_cn_stock_code`
- Modify: `src/stock_research/rolling_oversold/loaders.py:_membership_sql`
- Modify: `src/stock_research/loaders/baostock_ingestion.py:sync_industry_memberships`
- Create: `tests/test_core_data_concept_asset_ids.py`
- Modify: `tests/test_rolling_oversold_loaders_preflight.py`

- [ ] **Step 1: Add regression tests for unsupported B-share IDs and active-master filtering.**

```python
def test_concept_normalizer_does_not_turn_shanghai_b_share_into_bse_asset():
    assert _asset_id_from_cn_stock_code("900901") is None

def test_membership_loader_excludes_asset_without_active_asset_master(monkeypatch):
    sql, params = capture_membership_query("2026-07-21")
    assert "JOIN core.asset_master" in sql
    assert "list_date" in sql and "delist_date" in sql
    assert params.count("2026-07-21") >= 4
```

- [ ] **Step 2: Run the tests and verify the new tests fail.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_core_data_concept_asset_ids.py \
  tests/test_rolling_oversold_loaders_preflight.py -q
```

Expected: the `900901` test fails because the current code maps every `9xxxxx`
code to `CN:BJ`; the SQL assertion fails because membership loading does not
join `core.asset_master`.

- [ ] **Step 3: Implement the minimum normalization and universe fix.**

Change `_asset_id_from_cn_stock_code` so `900xxx` returns `None`; retain
`920xxx` as `CN:BJ:920xxx`. Change `_membership_sql` to join the master and
apply the PIT listing window:

```sql
JOIN core.asset_master a ON a.asset_id = m.asset_id
WHERE m.start_date <= %s
  AND (m.end_date IS NULL OR m.end_date > %s)
  AND (a.list_date IS NULL OR a.list_date <= %s)
  AND (a.delist_date IS NULL OR a.delist_date > %s)
```

Update `_membership_params` to provide the four cutoff parameters before any
optional system list. Do not delete historical membership rows.

After a successful industry snapshot sync, close active rows that are absent
from the current snapshot, using the same end-date semantics already used by
concept membership. This prevents old SH/SZ rows without a master record from
remaining active forever.

- [ ] **Step 4: Re-run focused tests.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_core_data_concept_asset_ids.py \
  tests/test_rolling_oversold_loaders_preflight.py \
  tests/test_consumer_oversold_loaders.py -q
```

Expected: all pass, with no regression to PIT membership behavior.

- [ ] **Step 5: Refresh memberships in the database.**

Use the existing source sync tasks, not strategy code:

```bash
rtk env DB_SERVICE=stock_research /Users/xiwei/stock_research/.venv/bin/stock-research \
  sync-industry-memberships --trade-date 2026-07-21
rtk /Users/xiwei/stock_research/.venv/bin/stock-research \
  sync-market-profile-concepts --trade-date 2026-07-21 \
  --service stock_research --concept-system em
```

Run the same two syncs for 2026-07-31 after the first date is validated. The
900xxx rows should become closed/ignored, not converted into BSE assets.

- [ ] **Step 6: Commit the universe repair.**

```bash
rtk git add src/stock_research/core_data.py \
  src/stock_research/rolling_oversold/loaders.py \
  src/stock_research/loaders/baostock_ingestion.py \
  tests/test_core_data_concept_asset_ids.py \
  tests/test_rolling_oversold_loaders_preflight.py
rtk git commit -m "fix: restrict rolling universe to valid PIT assets"
```

## Task 3: Add a database-only targeted market-bar backfill executor

**Files:**
- Create: `src/stock_research/rolling_oversold/market_backfill.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_rolling_oversold_market_backfill.py`
- Modify: `docs/daily-close-pipeline-runbook.md`

- [ ] **Step 1: Write source-selection and idempotency tests.**

The executor must accept an explicit asset list and date range, write raw
payloads first, then upsert `market_daily_bar` on
`(asset_id, trade_date, adjust_type)`. A second run over the same range must
write zero new logical rows and must not duplicate data.

```python
def test_targeted_market_backfill_is_idempotent_and_keeps_source_metadata():
    result = run_market_backfill(
        asset_ids=["CN:BJ:920001"],
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        adjust_types=("raw", "qfq", "hfq"),
        source="approved_daily_source",
        dry_run=False,
    )
    assert result["upsert_conflict_key"] == ["asset_id", "trade_date", "adjust_type"]
    assert result["source"] == "approved_daily_source"
```

- [ ] **Step 2: Run the new test and verify it fails.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_market_backfill.py -q
```

Expected: `FAIL` because no targeted rolling backfill executor exists.

- [ ] **Step 3: Implement the executor with explicit source boundaries.**

Implement:

```python
def run_market_backfill(
    *, asset_ids: list[str], start_date: date, end_date: date,
    adjust_types: tuple[str, ...], source: str,
    service: str = SETTINGS.research_service, dry_run: bool = True,
) -> dict[str, object]:
    _validate_target_assets(service, asset_ids, start_date, end_date)
    rows = _fetch_approved_daily_source(
        asset_ids=asset_ids, start_date=start_date, end_date=end_date,
        adjust_types=adjust_types, source=source,
    )
    if not dry_run:
        raw_count = _upsert_raw_payloads(service, rows)
        bar_count = _upsert_market_bars(service, rows)
    else:
        raw_count = bar_count = 0
    return {
        "source": source,
        "raw_rows": raw_count,
        "bar_rows": bar_count,
        "upsert_conflict_key": ["asset_id", "trade_date", "adjust_type"],
    }
```

The executor must:

1. Validate all IDs against `core.asset_master` and refuse IDs not in the
   approved active universe unless `--include-invalid-assets` is explicitly
   used for a historical repair task.
2. Fetch through an existing ingestion adapter that supports BSE `920xxx`;
   the current `stock_qfq`/`stock_hfq` table loader is not sufficient because
   those services expose zero `bj*` source tables.
3. Store raw payloads with source, endpoint, request range, and payload hash.
4. Upsert raw/qfq/hfq rows into `market_daily_bar`.
5. Emit per-asset and per-day counts, missing source responses, and retryable
   failures into a JSON/CSV report.

The strategy loader must not import or call this module.

- [ ] **Step 4: Run focused tests and then a dry-run for the 319 master-present assets.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_market_backfill.py -q
rtk /Users/xiwei/stock_research/.venv/bin/stock-research rolling-sector-oversold-backfill \
  --dataset market_daily_bar \
  --gap-workplan artifacts/rolling_sector_oversold/gap_workplan_2026-07-21/gap_workplan.json \
  --start-date 2025-05-28 --end-date 2026-07-31 \
  --adjust-types raw,qfq,hfq --service stock_research --dry-run
```

Expected: the dry-run includes only eligible master-present assets and shows
the requested 2025-05-28 through 2026-07-31 range.

- [ ] **Step 5: Execute the market backfill in resumable batches.**

Run with a batch size of 25–50 assets and persist each batch result. Retry only
failed batches. Do not run the full nine-anchor strategy until the workplan
reports zero unresolved market-bar gaps for all anchor cutoff dates.

- [ ] **Step 6: Commit the backfill executor and runbook.**

```bash
rtk git add src/stock_research/rolling_oversold/market_backfill.py \
  src/stock_research/cli.py \
  tests/test_rolling_oversold_market_backfill.py \
  docs/daily-close-pipeline-runbook.md
rtk git commit -m "feat: add resumable rolling market backfill"
```

## Task 4: Rebuild status, industry, concept, and index derived data

**Files:**
- Modify: `src/stock_research/core_data.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/loaders/baostock_ingestion.py`
- Create: `tests/test_rolling_oversold_derived_backfill.py`

- [ ] **Step 1: Add derived rebuild tests.**

The tests must assert that each builder uses the requested date range,
upserts on its canonical key, and is safe to run twice:

```python
def test_derived_backfill_rebuilds_all_sector_systems_and_status_for_window(monkeypatch):
    result = run_derived_backfill(
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        industry_systems=("csrc",),
        concept_systems=("em",),
        service="stock_research",
    )
    assert result["asset_status_daily"]["start_date"] == "2025-05-28"
    assert result["industry_daily_bar"]["systems"] == ["csrc"]
    assert result["concept_daily_bar"]["systems"] == ["em"]
```

- [ ] **Step 2: Implement and expose a derived backfill command.**

Add `rolling-sector-oversold-backfill --dataset derived` (or an equivalent
named command) that runs, in order:

```python
build_asset_status_daily_for_service(
    start_date="2025-05-28", end_date="2026-07-31", adjust_type="hfq",
)
build_industry_daily_bars_for_service(
    start_date="2025-05-28", end_date="2026-07-31",
    industry_system=system, adjust_type="qfq",
)
build_concept_daily_bars_for_service(
    start_date="2025-05-28", end_date="2026-07-31",
    concept_system=system, adjust_type="qfq",
)
```

The command must discover systems from the active membership workplan rather
than silently assuming only `csrc`/`em`. Add the missing `build-concept-bars`
CLI parser if direct maintenance execution is needed.

Fill the two index gaps with 252 sessions through the existing index adapter;
add a targeted `--index-ids STAR_50,BSE_50` option and verify that each index
has at least 252 non-null close rows. The current database has only 21 rows for
each, so merely rerunning the current default sync is not acceptance.

- [ ] **Step 3: Run the derived tests and execute the rebuild.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_derived_backfill.py -q
rtk /Users/xiwei/stock_research/.venv/bin/stock-research rolling-sector-oversold-backfill \
  --dataset derived --start-date 2025-05-28 --end-date 2026-07-31 \
  --service stock_research
```

- [ ] **Step 4: Maintain PostgreSQL statistics after bulk writes.**

```bash
rtk psql service=stock_research -v ON_ERROR_STOP=1 -c \
  "VACUUM (ANALYZE) market_daily_bar, core.asset_status_daily, market.industry_daily_bar, market.concept_daily_bar, market.index_daily_bar;"
```

- [ ] **Step 5: Commit the derived rebuild path.**

```bash
rtk git add src/stock_research/core_data.py \
  src/stock_research/cli.py \
  src/stock_research/loaders/baostock_ingestion.py \
  tests/test_rolling_oversold_derived_backfill.py
rtk git commit -m "feat: rebuild rolling derived coverage"
```

## Task 5: Backfill PIT finance and valuation inputs

**Files:**
- Create: `src/stock_research/rolling_oversold/fundamental_backfill.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_rolling_oversold_fundamental_backfill.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Generate required report-period and valuation-date requests.**

For each eligible asset, query rows visible at each anchor using
`announcement_date <= anchor_date`. Keep at least five distinct report periods
for cumulative TTM (`latest quarter`, `prior fiscal year`, and `prior same
quarter`, including the intervening quarters). For valuation, request
`pe_ttm`, `ps_ttm`, and `ev_ebitda` factor rows through each anchor.

- [ ] **Step 2: Add tests for PIT visibility and idempotency.**

```python
def test_finance_backfill_never_publishes_future_announcements():
    rows = build_finance_backfill_rows(
        asset_ids=["CN:BJ:920001"], cutoff=date(2026, 7, 21)
    )
    assert all(row["announcement_date"] <= date(2026, 7, 21) for row in rows)
    assert len({row["report_period"] for row in rows}) >= 5

def test_valuation_backfill_keeps_factor_names_and_version():
    rows = build_valuation_backfill_rows(
        asset_ids=["CN:BJ:920001"], start_date=date(2025, 5, 28), end_date=date(2026, 7, 31)
    )
    assert {row["factor_name"] for row in rows} <= {"pe_ttm", "ps_ttm", "ev_ebitda"}
    assert all(row["calc_version"] for row in rows)
```

- [ ] **Step 3: Implement source-specific fundamental backfill.**

Use the existing `sync-baostock-finance` path for assets and periods it
supports. For BSE assets not present in Baostock, use an approved existing
fundamental adapter and write to the canonical `finance.*` and
`factor.factor_daily` tables with source/version metadata. Never fill missing
values with zero or with post-cutoff data. A failed source request remains a
gap and is reported for retry.

- [ ] **Step 4: Run targeted fundamental backfill and validate coverage.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_fundamental_backfill.py \
  tests/test_consumer_oversold_loaders.py -q
rtk /Users/xiwei/stock_research/.venv/bin/stock-research rolling-sector-oversold-backfill \
  --dataset fundamentals \
  --gap-workplan artifacts/rolling_sector_oversold/gap_workplan_2026-07-21/gap_workplan.json \
  --start-date 2025-05-28 --end-date 2026-07-31 --service stock_research
```

Expected: the rolling loader's `max_report_periods=5` test remains green and
the fundamental gap counts decrease without changing consumer default loader
semantics.

- [ ] **Step 5: Commit the fundamental backfill path.**

```bash
rtk git add src/stock_research/rolling_oversold/fundamental_backfill.py \
  src/stock_research/cli.py \
  tests/test_rolling_oversold_fundamental_backfill.py \
  docs/daily-factor-pipeline-runbook.md
rtk git commit -m "feat: backfill rolling PIT fundamentals"
```

## Task 6: Re-run preflight, replay, and measure normal runtime

**Files:**
- Modify: `docs/superpowers/verification/2026-08-02-rolling-sector-oversold-gap-audit.md`
- Create: `docs/superpowers/verification/2026-08-02-rolling-sector-oversold-backfill-validation.md`
- Modify: `tests/test_rolling_oversold_acceptance.py`

- [ ] **Step 1: Run the gap audit again.**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/stock-research rolling-sector-oversold-backfill \
  --dataset audit --start-date 2025-05-28 --end-date 2026-07-31 \
  --service stock_research
```

Acceptance: no unresolved `market_daily_bar`, `core.asset_status_daily`,
finance, valuation, sector-bar, or index gaps for the active PIT universe.

- [ ] **Step 2: Run the complete frozen replay.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-21 --anchor-end-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research_v2 \
  --service stock_research --sector-top-n 30 --stock-top-n 20 \
  --score-version rolling_oversold_v1 --adjust-type qfq
```

Acceptance: `blocked=0`, nine anchors processed, nine immutable snapshot
manifests, no unresolved backfill artifact, and all 1/3/5-day outcomes are
pending or complete according to available future sessions.

- [ ] **Step 3: Generate the 2026-07-30 focus report.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-report \
  --snapshot-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research_v2/rolling_sector_oversold/anchor=2026-07-30/version=rolling_oversold_v1 \
  --focus-patterns '芯片,半导体,CPO,算力,科技,消费' \
  --output-dir artifacts/rolling_sector_oversold/validation_2026-07-30
```

- [ ] **Step 4: Measure both replay modes.**

Run the existing daily command for one current session:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-daily --trade-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research_v2 \
  --service stock_research --sector-top-n 30 --stock-top-n 20
```

Record stage timings. The current database-only path already fails fast in
23.16 seconds before scoring. After successful coverage, the expected normal
daily target is under 180 seconds and the nine-anchor replay target remains
under the configured 3,600-second budget. If the successful one-anchor run
exceeds 180 seconds, profile the recorded stage timings before changing the
algorithm.

- [ ] **Step 5: Run final tests and commit the validation record.**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_rolling_oversold_*.py \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_v2_evaluation.py -q
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m compileall -q src/stock_research
rtk git diff --check
```

Expected: the existing 122 rolling tests and 213 selected regression tests
remain green, plus the new backfill tests; no strategy module imports an
external ingestion client.

```bash
rtk git add docs/superpowers/verification/2026-08-02-rolling-sector-oversold-gap-audit.md \
  docs/superpowers/verification/2026-08-02-rolling-sector-oversold-backfill-validation.md \
  tests/test_rolling_oversold_acceptance.py
rtk git commit -m "test: validate rolling oversold gap backfill"
```

## Runtime answer

补完并通过上述验收后，日常使用 `rolling-sector-oversold-daily`，不会再跑
9 个 anchor，也不会重新扫描无界历史：行情读取限定在 252 个交易日，财务
只取最近 5 个披露期，估值只取每个资产最新可见日期，预审检查为向量化/集合
运算。当前未补齐数据库时已经能在约 23 秒内 fail-closed；数据补齐后会多出
行业/股票评分和快照写入，因此计划把正常单日目标定为 **180 秒以内**，而不是
把 23 秒误当成成功运行耗时。一次性的 9-anchor 回放仍按 **1 小时以内**验收。

补数本身可能需要更久，尤其是 303 个 BSE 资产的历史日线和财务数据；它是一次
性、可分批、可恢复的 backfill 成本，不会叠加到以后的每日策略运行时间。
