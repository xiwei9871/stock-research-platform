# Yanbaoke Technical Bottleneck Quota Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the remaining 221 Yanbaoke report quota for Technical Bottleneck evidence coverage before the July quota refresh.

**Architecture:** Reuse the existing 2026-06-29 Technical Bottleneck report-level reserve queue and direct UUID downloader. Avoid repeated search/filter calls; download only reserve UUIDs not already downloaded, then import successful PDFs into the local report evidence pipeline.

**Tech Stack:** Python, pandas, existing `stock_research.yanbaoke_reports` import functions, local JSON API key.

---

### Task 1: Validate Remaining Download Universe

**Files:**
- Read: `outputs/research/yanbaoke_quota_burn_20260629/master_report_level_reserve_queue.csv`
- Read: `outputs/research/yanbaoke_quota_burn_20260629/yanbaoke_quota_burn_combined_downloads.csv`
- Output: `outputs/research/yanbaoke_quota_burn_20260630/remaining_reserve_audit.csv`

- [ ] **Step 1: Count reserve UUIDs not already downloaded**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
prev = Path("outputs/research/yanbaoke_quota_burn_20260629")
out = Path("outputs/research/yanbaoke_quota_burn_20260630")
out.mkdir(parents=True, exist_ok=True)
reserve = pd.read_csv(prev / "master_report_level_reserve_queue.csv")
downloaded = pd.read_csv(prev / "yanbaoke_quota_burn_combined_downloads.csv")
done = set(downloaded.loc[downloaded["status"].astype(str).eq("downloaded"), "uuid"].dropna().astype(str))
reserve["uuid"] = reserve["report_id"].astype(str)
remaining = reserve[reserve["uuid"].notna() & reserve["uuid"].ne("nan") & ~reserve["uuid"].isin(done)].copy()
remaining.to_csv(out / "remaining_reserve_audit.csv", index=False)
print({"reserve_rows": len(reserve), "downloaded": len(done), "remaining": len(remaining)})
PY
```

Expected: remaining reserve count is comfortably above 221, or enough to make a best-effort run.

### Task 2: Add Exact Success Target to Direct UUID Downloader

**Files:**
- Modify: `scripts/download_yanbaoke_reserve_by_uuid.py`

- [ ] **Step 1: Add `--target-successes` argument**

Implementation must stop the loop once the current output manifest has reached the requested number of downloaded rows. This prevents overshooting when using a larger attempt budget to compensate for expired UUIDs.

- [ ] **Step 2: Verify script compiles**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python -m py_compile scripts/download_yanbaoke_reserve_by_uuid.py
```

Expected: exit code 0.

### Task 3: Download Remaining 221 Reports

**Files:**
- Input: `outputs/research/yanbaoke_quota_burn_20260629/master_report_level_reserve_queue.csv`
- Existing manifests:
  - `outputs/research/yanbaoke_quota_burn_20260629/smoke_20/yanbaoke_downloaded_reports.csv`
  - `outputs/research/yanbaoke_quota_burn_20260629/direct_smoke_5/yanbaoke_direct_uuid_downloads.csv`
  - `outputs/research/yanbaoke_quota_burn_20260629/direct_batch_588/yanbaoke_direct_uuid_downloads.csv`
  - `outputs/research/yanbaoke_quota_burn_20260629/direct_supplement_160/yanbaoke_direct_uuid_downloads.csv`
  - `outputs/research/yanbaoke_quota_burn_20260629/direct_tail_40/yanbaoke_direct_uuid_downloads.csv`
- Output: `outputs/research/yanbaoke_quota_burn_20260630/direct_quota_221/`

- [ ] **Step 1: Run direct UUID downloader**

Run with `--target-successes 221` and a larger attempt budget so failed/expired UUIDs do not prevent quota usage.

### Task 4: Import New Downloads to Evidence Pipeline

**Files:**
- Input: `outputs/research/yanbaoke_quota_burn_20260630/direct_quota_221/yanbaoke_direct_uuid_downloads.csv`
- Output directory: `outputs/research/yanbaoke_quota_burn_20260630/imported_evidence/`

- [ ] **Step 1: Import with `import_yanbaoke_report_downloads`**

Use `write_db=True` and `feature_trade_date=2026-06-30`.

### Task 5: Summarize and Verify

**Files:**
- Output: `outputs/research/yanbaoke_quota_burn_20260630/final_quota_burn_summary.md`
- Output: `outputs/research/yanbaoke_quota_burn_20260630/yanbaoke_quota_burn_download_summary.csv`

- [ ] **Step 1: Verify counts**

Required checks:

```text
downloaded_rows == pdf_count == unique_uuid_downloaded
downloaded_rows is 221 if enough reserve UUIDs succeed
source/event/field rows match downloaded_rows after import
```

- [ ] **Step 2: Record caveats**

If fewer than 221 downloads succeed because reserve UUIDs are expired/unavailable, report exact attempted/error counts and stop without inventing alternative sources.
