# Yanbaoke Technical Bottleneck Quota Burn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the remaining ~594 Yanbaoke report quota before the 2026-07-01 monthly refresh, prioritizing reports that improve Technical Bottleneck discovery, evidence completeness, and daily review quality.

**Architecture:** This is an operations/research execution plan, not a new strategy. Reuse the existing Yanbaoke downloader/importer, stock report source/event tables, PDF field backfill, and Technical Bottleneck evidence workflow. Download allocation is quota-aware, deduped, and focused on the three current Technical Bottleneck evidence fields: `revenue_exposure_bucket`, `customer_certification_stage`, and `supplier_concentration_type`.

**Tech Stack:** Existing `stock-research` CLI, `src/stock_research/yanbaoke_reports.py`, `src/stock_research/tech_bottleneck_evidence_workflow.py`, pandas CSV queues, local PDF storage, optional DB writes through existing stock report upsert helpers.

---

## Operating Constraints

- Current date: 2026-06-29.
- Quota target: consume up to 594 reports before 2026-07-01 refresh.
- Primary beneficiary: Technical Bottleneck, not Mid Trend.
- Do not download random reports just to burn quota.
- Do not change trading strategy logic.
- Do not add entry filters, re-entry, slow exit, carry, or ownership hold.
- Use only existing Yanbaoke APIs and existing importer paths.
- Keep downloaded PDFs under a dated output package.
- Write DB only after a 10-20 report smoke run succeeds.
- Do not print or commit `YANBAOKE_API_KEY`.

## Quota Allocation

| Bucket | Reports | Purpose | Source |
| --- | ---: | --- | --- |
| A. Direct evidence gaps | 180 | Fill current Tech Bottleneck missing/partial evidence fields | `tech_bottleneck_evidence_workflow_*/*yanbaoke_backfill_tasks.csv` |
| B. Current candidates / active focus | 120 | Add depth to current top candidates and likely Daily Review names | top candidate snapshots, strategy review artifacts |
| C. P0/P1 bottleneck industries | 170 | Build industry-chain context for future discovery | `yanbaoke_sector_priority.csv` P0/P1 themes |
| D. Supplier/customer/certification evidence | 84 | Support supplier concentration and customer certification attribution | supplier/customer focused queues |
| E. Deadline reserve | 40 | Replace failed/no-qualified tasks and burn final usable quota | highest-scored remaining queue |
| **Total** | **594** |  |  |

## Batch Schedule

| Time | Quota | Scope | Stop condition |
| --- | ---: | --- | --- |
| 2026-06-29 evening | 240 | A=120, B=80, C=40 | Stop if API errors persist for 3 consecutive tasks or downloaded >=240 |
| 2026-06-30 morning | 220 | A=60, C=90, D=50, E=20 | Stop if duplicate/no-qualified rate >50% after first 60 attempted tasks |
| 2026-06-30 afternoon | 100 | C=40, D=34, E=26 | Stop if remaining quota <=34 |
| 2026-06-30 night fallback | 34 | E only | Stop at quota exhaustion or 23:30 local time |

---

## File Map

- Read: `outputs/research/tech_bottleneck_evidence_workflow_20260619_full_support_final/tech_bottleneck_yanbaoke_backfill_tasks.csv`
  - Direct high-confidence evidence gap queue.
- Read: `outputs/research/tech_bottleneck_evidence_workflow_20260619_merged_cninfo_final/tech_bottleneck_yanbaoke_backfill_tasks.csv`
  - Broader direct evidence gap queue.
- Read: `outputs/research/yanbaoke_priority_plan_20250101_20260612/yanbaoke_priority_queue.csv`
  - Existing quota-aware broad Yanbaoke queue.
- Read: `outputs/research/tech_bottleneck_supplier_yanbaoke_backfill_20260619/supplier_concentration_yanbaoke_tasks.csv`
  - Supplier concentration focused tasks.
- Read: `config/yanbaoke_sector_priority.csv`
  - P0/P1 sector priority map.
- Use: `src/stock_research/yanbaoke_reports.py`
  - Existing search, filter, quota selection, download, import, PDF field backfill.
- Use: `src/stock_research/tech_bottleneck_evidence_workflow.py`
  - Recompute evidence gaps after imports.
- Create: `outputs/research/yanbaoke_quota_burn_20260629/`
  - All queues, downloaded manifests, PDFs, import artifacts, validation reports.

---

## Task 1: Preflight And Quota Snapshot

**Files:**
- Create directory: `outputs/research/yanbaoke_quota_burn_20260629/`
- Create: `outputs/research/yanbaoke_quota_burn_20260629/run_notes.md`

- [ ] **Step 1: Confirm API key exists without printing it**

Run:

```bash
cd /Users/xiwei/stock_research
test -n "${YANBAOKE_API_KEY:-}" && echo "YANBAOKE_API_KEY=set" || echo "YANBAOKE_API_KEY=missing"
```

Expected:

```text
YANBAOKE_API_KEY=set
```

- [ ] **Step 2: Create output directory**

Run:

```bash
cd /Users/xiwei/stock_research
mkdir -p outputs/research/yanbaoke_quota_burn_20260629
```

Expected: directory exists.

- [ ] **Step 3: Record operating note**

Run:

```bash
cat > outputs/research/yanbaoke_quota_burn_20260629/run_notes.md <<'EOF'
# Yanbaoke Quota Burn 2026-06-29

- Remaining quota target: 594 reports.
- Purpose: Technical Bottleneck evidence and industry-chain attribution.
- Strategy impact: none.
- API key: environment variable only; not written to disk.
- Deadline: before 2026-07-01 quota refresh.
EOF
```

Expected: `run_notes.md` exists and contains no secret.

---

## Task 2: Build A Deduped Master Task Queue

**Files:**
- Create: `outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv`
- Create: `outputs/research/yanbaoke_quota_burn_20260629/master_task_summary.csv`

- [ ] **Step 1: Build merged task queue from direct Tech Bottleneck and reserve sources**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

out = Path("outputs/research/yanbaoke_quota_burn_20260629")
sources = [
    ("A_direct_final", Path("outputs/research/tech_bottleneck_evidence_workflow_20260619_full_support_final/tech_bottleneck_yanbaoke_backfill_tasks.csv"), 1000),
    ("A_direct_broad", Path("outputs/research/tech_bottleneck_evidence_workflow_20260619_merged_cninfo_final/tech_bottleneck_yanbaoke_backfill_tasks.csv"), 900),
    ("D_supplier", Path("outputs/research/tech_bottleneck_supplier_yanbaoke_backfill_20260619/supplier_concentration_yanbaoke_tasks.csv"), 760),
    ("E_support_retry", Path("outputs/research/tech_bottleneck_support_data_audit_20260619/tech_bottleneck_yanbaoke_retry_tasks.csv"), 700),
    ("C_priority_queue", Path("outputs/research/yanbaoke_priority_plan_20250101_20260612/yanbaoke_priority_queue.csv"), 600),
]

frames = []
for source_name, path, base_priority in sources:
    if not path.exists():
        continue
    frame = pd.read_csv(path, dtype=object).fillna("")
    if "ts_code" not in frame.columns and "stock_code" in frame.columns:
        frame["ts_code"] = frame["stock_code"]
    if "symbol" not in frame.columns:
        frame["symbol"] = frame["ts_code"].astype(str).str.split(".").str[0]
    if "asset_id" not in frame.columns:
        frame["asset_id"] = ""
    if "stock_name" not in frame.columns:
        frame["stock_name"] = ""
    if "start_date" not in frame.columns:
        frame["start_date"] = "2024-01-01"
    if "end_date" not in frame.columns:
        frame["end_date"] = "2026-06-29"
    if "status" not in frame.columns:
        frame["status"] = "pending"
    frame["quota_source"] = source_name
    frame["quota_priority"] = base_priority
    frames.append(frame)

if not frames:
    raise SystemExit("no task sources found")

master = pd.concat(frames, ignore_index=True, sort=False).fillna("")
master["ts_code"] = master["ts_code"].astype(str).str.strip()
master["stock_name"] = master["stock_name"].astype(str).str.strip()
master = master[master["ts_code"].ne("") | master["stock_name"].ne("")].copy()

def missing_weight(text: str) -> int:
    parts = [p for p in str(text).split("|") if p]
    return len(parts)

master["_missing_weight"] = master.get("missing_fields", "").map(missing_weight) if "missing_fields" in master else 0
master["_evidence_rank"] = master.get("evidence_status", "").map({
    "missing_blocking": 3,
    "weak_pending_backfill": 2,
    "partial": 1,
}).fillna(0)
master["quota_score"] = (
    pd.to_numeric(master["quota_priority"], errors="coerce").fillna(0)
    + master["_missing_weight"] * 50
    + master["_evidence_rank"] * 30
)
master = master.sort_values(["quota_score", "ts_code", "stock_name"], ascending=[False, True, True])
master = master.drop_duplicates(subset=["ts_code", "stock_name", "quota_source"], keep="first")
master = master.drop_duplicates(subset=["ts_code", "stock_name"], keep="first")
master["task_id"] = ["yb_quota_%04d" % (i + 1) for i in range(len(master))]
master["status"] = "pending"

keep = [
    "task_id", "asset_id", "ts_code", "symbol", "stock_name", "start_date", "end_date", "status",
    "quota_source", "quota_priority", "quota_score", "evidence_status", "missing_fields",
    "source_collection_priority", "primary_chain_id", "primary_chain_name",
]
for column in keep:
    if column not in master.columns:
        master[column] = ""
master[keep].to_csv(out / "master_tasks.csv", index=False)
summary = master.groupby("quota_source", dropna=False).size().reset_index(name="task_count")
summary.to_csv(out / "master_task_summary.csv", index=False)
print("master_rows", len(master))
print(summary.to_string(index=False))
PY
```

Expected:

- `master_tasks.csv` exists.
- Direct evidence queues appear at the top.
- Row count should exceed 594 candidate tasks or at least enough tasks to support fallback.

- [ ] **Step 2: Inspect master queue**

Run:

```bash
cd /Users/xiwei/stock_research
head -20 outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv
cat outputs/research/yanbaoke_quota_burn_20260629/master_task_summary.csv
```

Expected:

- First rows are direct Technical Bottleneck missing/partial evidence names.
- No obvious empty `ts_code` plus empty `stock_name` rows.

---

## Task 3: Run 20-Report Smoke Download

**Files:**
- Input: `outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv`
- Create: `outputs/research/yanbaoke_quota_burn_20260629/smoke_20/`

- [ ] **Step 1: Run smoke without DB write**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research run-yanbaoke-report-backfill \
  --tasks-path outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/smoke_20 \
  --download-dir outputs/research/yanbaoke_quota_burn_20260629/smoke_20/pdfs \
  --max-downloads 20 \
  --monthly-budget 20 \
  --base-budget 8 \
  --top-budget 8 \
  --reserve-budget 4 \
  --max-broker-share 0.25 \
  --feature-trade-date 2026-06-29
```

Expected:

- Command exits 0.
- `yanbaoke_downloaded_reports.csv` has up to 20 downloaded rows.
- `yanbaoke_backfill_report.md` is created.

- [ ] **Step 2: Validate smoke outputs**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path("outputs/research/yanbaoke_quota_burn_20260629/smoke_20")
downloads = pd.read_csv(root / "yanbaoke_downloaded_reports.csv") if (root / "yanbaoke_downloaded_reports.csv").exists() else pd.DataFrame()
print("download_rows", len(downloads))
print("status_counts")
print(downloads.get("status", pd.Series(dtype=object)).value_counts(dropna=False).to_string())
print("unique_brokers", downloads.get("broker", pd.Series(dtype=object)).nunique())
print("pdf_files", len(list((root / "pdfs").glob("*.pdf"))))
PY
```

Expected:

- `download_rows > 0`.
- No repeated API or auth errors.
- Broker concentration is not obviously one broker only.

---

## Task 4: Batch 1 Download - 240 Reports

**Files:**
- Create: `outputs/research/yanbaoke_quota_burn_20260629/batch_1_240/`

- [ ] **Step 1: Run Batch 1**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research run-yanbaoke-report-backfill \
  --tasks-path outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/batch_1_240 \
  --download-dir outputs/research/yanbaoke_quota_burn_20260629/batch_1_240/pdfs \
  --max-downloads 240 \
  --monthly-budget 240 \
  --base-budget 80 \
  --top-budget 120 \
  --reserve-budget 40 \
  --max-broker-share 0.25 \
  --write-db \
  --feature-trade-date 2026-06-29
```

Expected:

- Command exits 0 or stops only after quota/budget exhaustion.
- Downloaded rows are close to 240 unless many tasks have no qualified reports.

- [ ] **Step 2: Validate Batch 1**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path("outputs/research/yanbaoke_quota_burn_20260629/batch_1_240")
downloads = pd.read_csv(root / "yanbaoke_downloaded_reports.csv") if (root / "yanbaoke_downloaded_reports.csv").exists() else pd.DataFrame()
tasks = pd.read_csv(root / "yanbaoke_backfill_tasks.csv") if (root / "yanbaoke_backfill_tasks.csv").exists() else pd.DataFrame()
print("downloaded", len(downloads))
print("task_status")
print(tasks.get("status", pd.Series(dtype=object)).value_counts(dropna=False).to_string())
print("broker_top10")
print(downloads.get("broker", pd.Series(dtype=object)).value_counts().head(10).to_string())
PY
```

Expected:

- `downloaded >= 160`; if lower, Batch 2 must increase reserve/fallback.
- No single broker exceeds 25-30% of downloads.

---

## Task 5: Batch 2 Download - 220 Reports

**Files:**
- Create: `outputs/research/yanbaoke_quota_burn_20260629/batch_2_220/`

- [ ] **Step 1: Build remaining task queue excluding Batch 1 downloaded stocks**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path("outputs/research/yanbaoke_quota_burn_20260629")
master = pd.read_csv(root / "master_tasks.csv", dtype=object).fillna("")
batch1_path = root / "batch_1_240" / "yanbaoke_downloaded_reports.csv"
downloaded = pd.read_csv(batch1_path, dtype=object).fillna("") if batch1_path.exists() else pd.DataFrame()
counts = downloaded.groupby("ts_code").size().to_dict() if not downloaded.empty and "ts_code" in downloaded.columns else {}
master["existing_download_count"] = master["ts_code"].map(lambda x: int(counts.get(str(x), 0)))
remaining = master[master["existing_download_count"].lt(3)].copy()
remaining = remaining.sort_values(["quota_score", "existing_download_count"], ascending=[False, True])
remaining.to_csv(root / "batch_2_remaining_tasks.csv", index=False)
print("remaining_rows", len(remaining))
PY
```

Expected: `batch_2_remaining_tasks.csv` exists.

- [ ] **Step 2: Run Batch 2**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research run-yanbaoke-report-backfill \
  --tasks-path outputs/research/yanbaoke_quota_burn_20260629/batch_2_remaining_tasks.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/batch_2_220 \
  --download-dir outputs/research/yanbaoke_quota_burn_20260629/batch_2_220/pdfs \
  --max-downloads 220 \
  --monthly-budget 220 \
  --base-budget 70 \
  --top-budget 90 \
  --reserve-budget 60 \
  --max-broker-share 0.25 \
  --write-db \
  --feature-trade-date 2026-06-30
```

Expected:

- Batch 2 fills direct gaps not covered in Batch 1.
- Reserve begins consuming broader P0/P1 and supplier/customer tasks.

---

## Task 6: Batch 3 And Deadline Reserve - 134 Reports

**Files:**
- Create: `outputs/research/yanbaoke_quota_burn_20260629/batch_3_100/`
- Create: `outputs/research/yanbaoke_quota_burn_20260629/batch_4_reserve_34/`

- [ ] **Step 1: Calculate already downloaded count**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path("outputs/research/yanbaoke_quota_burn_20260629")
total = 0
for name in ["smoke_20", "batch_1_240", "batch_2_220"]:
    path = root / name / "yanbaoke_downloaded_reports.csv"
    if path.exists():
        frame = pd.read_csv(path, dtype=object)
        n = len(frame[frame.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")]) if "status" in frame else len(frame)
        print(name, n)
        total += n
print("downloaded_so_far", total)
print("remaining_to_594", max(0, 594 - total))
PY
```

Expected: remaining count is known before running the final batches.

- [ ] **Step 2: Run Batch 3 up to 100 reports**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research run-yanbaoke-report-backfill \
  --tasks-path outputs/research/yanbaoke_quota_burn_20260629/batch_2_remaining_tasks.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/batch_3_100 \
  --download-dir outputs/research/yanbaoke_quota_burn_20260629/batch_3_100/pdfs \
  --max-downloads 100 \
  --monthly-budget 100 \
  --base-budget 20 \
  --top-budget 40 \
  --reserve-budget 40 \
  --max-broker-share 0.30 \
  --write-db \
  --feature-trade-date 2026-06-30
```

Expected: downloads approach 100 unless quota is nearly exhausted.

- [ ] **Step 3: Run final reserve only if remaining quota exists**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research run-yanbaoke-report-backfill \
  --tasks-path outputs/research/yanbaoke_quota_burn_20260629/master_tasks.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/batch_4_reserve_34 \
  --download-dir outputs/research/yanbaoke_quota_burn_20260629/batch_4_reserve_34/pdfs \
  --max-downloads 34 \
  --monthly-budget 34 \
  --base-budget 0 \
  --top-budget 0 \
  --reserve-budget 34 \
  --max-broker-share 0.35 \
  --write-db \
  --feature-trade-date 2026-06-30
```

Expected: final reserve consumes remaining quota without changing strategy behavior.

---

## Task 7: Import / PDF Field / Evidence Verification

**Files:**
- Create: `outputs/research/yanbaoke_quota_burn_20260629/final_download_summary.csv`
- Create: `outputs/research/yanbaoke_quota_burn_20260629/final_evidence_refresh_notes.md`

- [ ] **Step 1: Summarize all downloaded reports**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path("outputs/research/yanbaoke_quota_burn_20260629")
frames = []
for subdir in ["smoke_20", "batch_1_240", "batch_2_220", "batch_3_100", "batch_4_reserve_34"]:
    path = root / subdir / "yanbaoke_downloaded_reports.csv"
    if path.exists():
        frame = pd.read_csv(path, dtype=object).fillna("")
        frame["batch"] = subdir
        frames.append(frame)
all_downloads = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
if not all_downloads.empty:
    all_downloads = all_downloads.drop_duplicates(subset=[c for c in ["uuid", "pdf_path"] if c in all_downloads.columns], keep="last")
all_downloads.to_csv(root / "final_download_summary.csv", index=False)
print("unique_download_rows", len(all_downloads))
if "status" in all_downloads:
    print(all_downloads["status"].value_counts(dropna=False).to_string())
if "broker" in all_downloads:
    print("broker_top10")
    print(all_downloads["broker"].value_counts().head(10).to_string())
if "budget_bucket" in all_downloads:
    print("budget_bucket")
    print(all_downloads["budget_bucket"].value_counts(dropna=False).to_string())
PY
```

Expected:

- `unique_download_rows` close to 594 or explains shortfall.
- Output CSV exists.

- [ ] **Step 2: Re-run PDF field backfill over final downloads if needed**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research stock-report-pdf-field-backfill \
  --source-path outputs/research/yanbaoke_quota_burn_20260629/final_download_summary.csv \
  --output-dir outputs/research/yanbaoke_quota_burn_20260629/pdf_field_backfill_final \
  --batch-size 100 \
  --write-db
```

Expected:

- `fields`, `summary`, and `report` files are created.
- Target price / pages / report type fields are parsed where available.

- [ ] **Step 3: Recompute Technical Bottleneck evidence workflow**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research tech-bottleneck-evidence-workflow \
  --asset-queue-path outputs/research/tech_bottleneck_evidence_workflow_20260619_merged_cninfo_final/tech_bottleneck_topn_evidence_backfill_queue.csv \
  --evidence-detail-path outputs/research/tech_bottleneck_source_backed_refresh_20260619_full_support_final/tech_bottleneck_evidence_detail.csv \
  --candidate-path outputs/research/tech_bottleneck_discovery_v0_1_closeout_20260608/tech_bottleneck_candidates.csv \
  --trade-date 2026-06-30 \
  --top-n 100 \
  --output-dir outputs/research/tech_bottleneck_evidence_workflow_20260630_after_yanbaoke_quota_burn
```

Expected:

- Recomputed workflow artifacts exist.
- `tech_bottleneck_weak_evidence_queue.csv` shrinks or clearly identifies remaining non-Yanbaoke gaps.

If the exact `evidence_detail_path` or `candidate_path` is missing, use the latest matching `tech_bottleneck_source_backed_refresh_*/*evidence_detail*.csv` and candidate CSV found under `outputs/research/`.

- [ ] **Step 4: Write final notes**

Run:

```bash
cd /Users/xiwei/stock_research
cat > outputs/research/yanbaoke_quota_burn_20260629/final_evidence_refresh_notes.md <<'EOF'
# Final Evidence Refresh Notes

Questions to answer manually:

1. How many Yanbaoke PDFs were downloaded before 2026-07-01 refresh?
2. How many were written to stock report source/event tables?
3. How many parsed usable PDF fields?
4. Which Technical Bottleneck evidence fields improved?
5. Which assets still have missing_blocking evidence?
6. Which industries now have materially better research coverage?
7. Which downloaded reports should become manual evidence seeds?
EOF
```

Expected: notes file exists.

---

## Task 8: Acceptance And Stop Rules

**Files:**
- Read: `outputs/research/yanbaoke_quota_burn_20260629/final_download_summary.csv`
- Read: `outputs/research/tech_bottleneck_evidence_workflow_20260630_after_yanbaoke_quota_burn/`

- [ ] **Step 1: Accept the quota burn if all criteria pass**

Acceptance:

- Total downloaded reports are at least 520, or shortfall is explained by API/no-qualified/no-quota status.
- Direct evidence gap assets receive priority over broad industry reports.
- Single-broker share does not dominate the batch.
- PDF files are present on disk.
- DB write/import path succeeded for downloaded records.
- No trading strategy files were modified.
- No buy/sell/re-entry rules were added.

- [ ] **Step 2: Stop downloading even if quota remains when quality collapses**

Stop if any condition holds:

- Repeated auth/API errors after 3 retries.
- No-qualified rate exceeds 70% for two consecutive batches.
- Remaining candidate queue is mostly P3/long-tail unrelated to Technical Bottleneck.
- Local disk or PDF import becomes unstable.
- It is past 2026-06-30 23:30 local time.

---

## Final Recommendation

Use the 594 reports aggressively, but not indiscriminately:

1. First fill direct Technical Bottleneck evidence gaps.
2. Then deepen current top candidates and active focus stocks.
3. Then spend on P0/P1 bottleneck industries.
4. Use final reserve only for high-priority fallback.
5. Treat all downloaded reports as research evidence, not strategy rules.

This preserves the current policy: Technical Bottleneck can use research evidence and report coverage, while Mid Trend remains separate and should not import report-reading/bottleneck evidence logic.

