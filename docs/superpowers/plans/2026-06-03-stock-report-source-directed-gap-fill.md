# Stock Report Source-Directed Gap Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-directed public web gap-fill path for stocks where AkShare Eastmoney returned no research reports.

**Architecture:** Keep `research.stock_report_source/event` unchanged and reuse the existing collection-to-source/event normalization. Add a `bing_site_search` adapter that rewrites existing stock-report search tasks into targeted Bing `site:` queries for known public research/rating domains, then feeds the current search-result parser.

**Tech Stack:** Python, pandas, urllib, existing `stock_research` CLI, pytest.

---

### Task 1: Source-Directed Adapter

**Files:**
- Modify: `src/stock_research/stock_report_web_collection.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_stock_report_web_collection.py`

- [ ] **Step 1: Write failing tests**

Add tests that verify:

```python
def test_collect_bing_site_search_rewrites_queries_to_source_domains():
    ...
```

The test should call `collect_stock_report_web_sources_from_plan(..., dry_run=False, adapter="bing_site_search", fetcher=fake_fetcher)` and assert the fetcher receives Bing URLs containing `site:` clauses for public research/rating domains.

Add a CLI parser test that verifies `collect-stock-report-web-sources --adapter bing_site_search` is accepted.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_stock_report_web_collection.py tests/test_factor_cli.py -k "bing_site_search or stock_report" -v
```

Expected: fail because `bing_site_search` is not implemented or not accepted by CLI choices.

- [ ] **Step 3: Implement minimal adapter**

Add `bing_site_search` as a collection adapter. For each plan row, create targeted copies for:

```text
site:pdf.dfcfw.com
site:data.eastmoney.com/report
site:stock.finance.sina.com.cn
site:10jqka.com.cn
```

Use Bing URLs and reuse `_build_live_collection`.

- [ ] **Step 4: Verify tests pass**

Run:

```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_stock_report_web_collection.py tests/test_factor_cli.py -k "bing_site_search or stock_report" -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Smoke a small sample**

Run the existing sample path with `--adapter bing_site_search` and no database writes:

```bash
cd /Users/xiwei/stock_research && .venv/bin/stock-research collect-stock-report-web-sources \
  --search-plan-path outputs/research/stock_report_web_gap_20260603/stock_report_search_plan_sample_nonst25.csv \
  --output-dir outputs/research/stock_report_web_gap_20260603/sample_nonst25_bing_site_live \
  --adapter bing_site_search \
  --max-results-per-task 2
```

Expected: command exits 0 and writes collection/source/event CSVs. Hit rate can be zero for the sample; this step validates the adapter path and artifacts, not coverage.
