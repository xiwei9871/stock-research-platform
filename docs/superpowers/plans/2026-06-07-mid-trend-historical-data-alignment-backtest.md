# Mid Trend Historical Data Alignment Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 `2024-01-02` 至 `2024-12-31` 的 mid trend 严格回测输入链路，并用同一套 `mid trend + high_only_new_entry + tail_z=0.4 + reversal_z=0.4` 回测验证非 2025 小牛市环境下是否失效。

**Architecture:** 不修改策略代码，先补齐历史 `watchlist diagnostics -> industry mainline regime -> mid trend funnel -> intraday overlay` 四层数据。每一层都输出到独立目录，先做覆盖率校验，再进入下一层，避免把缺失上下文误判为策略失效。

**Tech Stack:** Python CLI (`python -m stock_research.cli`), pandas CSV processing, existing `stock_research` modules, PostgreSQL-backed research service.

---

## File Structure

- Read: `src/stock_research/cli.py`
  - 使用已有 CLI：`build-watchlist-diagnostics-range`、`industry-mainline-regime-diagnostics`、`build-strong-winner-discovery-pool`、`build-mid-trend-watch-funnel`。
- Read: `src/stock_research/mid_trend_intraday_risk_overlay.py`
  - 使用已有函数 `run_mid_trend_intraday_risk_overlay_backtest`，因为当前没有单独 CLI。
- Create output dir: `outputs/research/watchlist_diagnostics_20240102_20241231/`
  - 存放 2024 每日 watchlist diagnostics CSV/Markdown。
- Create output dir: `outputs/research/industry_mainline_regime_20240102_20241231/`
  - 存放合并后的 industry mainline regime 和 market regime。
- Create output dir: `outputs/research/strong_winner_discovery_pool_20230101_20250101/`
  - 已生成，可复用；如需重跑按本计划命令执行。
- Create output dir: `outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/`
  - 使用 2024 regime/mainline 后重新生成的 funnel。
- Create output dir: `outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned/`
  - 最终严格口径 overlay 回测产物。

---

### Task 1: Confirm Historical Score Coverage

**Files:**
- Read: database table `factor.stock_score_daily`
- Create: none

- [ ] **Step 1: Query available score versions**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
from stock_research.db import connect, fetch_all
from stock_research.config import SETTINGS

sql = """
SELECT
    score_version,
    min(trade_date)::text AS min_date,
    max(trade_date)::text AS max_date,
    count(*) AS rows
FROM factor.stock_score_daily
WHERE trade_date BETWEEN %s AND %s
GROUP BY score_version
ORDER BY min_date, score_version
"""

with connect(SETTINGS.research_service) as conn:
    rows = fetch_all(conn, sql, ["2023-01-01", "2025-01-01"])

for row in rows:
    print(row)
PY
```

Expected current result:

```text
manual_v1 starts at 2024-01-02 and ends at 2024-12-31
no comparable manual_v1 rows for 2023
```

- [ ] **Step 2: Decide strict test window**

Use `2024-01-02` to `2024-12-31` as the first strict historical stress test window.

Record this decision in the final report:

```text
2023 is not a strict comparable period under manual_v1 because score rows are absent.
The first comparable pre-2025 stress window is full-year 2024.
```

---

### Task 2: Build 2024 Watchlist Diagnostics Cache

**Files:**
- Create/update: `outputs/research/watchlist_diagnostics_20240102_20241231/`

- [ ] **Step 1: Resume/build 2024 diagnostics range by month**

Run each month separately. Do not pass `--force`; existing daily files will be skipped and missing files will be generated.

```bash
cd /Users/xiwei/stock_research

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-01-02 \
  --end-date 2024-01-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-02-01 \
  --end-date 2024-02-29 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-03-01 \
  --end-date 2024-03-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-04-01 \
  --end-date 2024-04-30 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-05-01 \
  --end-date 2024-05-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-06-01 \
  --end-date 2024-06-30 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-07-01 \
  --end-date 2024-07-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-08-01 \
  --end-date 2024-08-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-09-01 \
  --end-date 2024-09-30 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-10-01 \
  --end-date 2024-10-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-11-01 \
  --end-date 2024-11-30 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231

.venv/bin/python -m stock_research.cli build-watchlist-diagnostics-range \
  --start-date 2024-12-01 \
  --end-date 2024-12-31 \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research/watchlist_diagnostics_20240102_20241231
```

Expected:

```text
watchlist_diagnostics_range|summary|...
```

- [ ] **Step 2: Validate daily diagnostics coverage**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

path = Path("outputs/research/watchlist_diagnostics_20240102_20241231")
files = sorted(
    p for p in path.glob("watchlist_diagnostics_2024-*_diagnostics_v1.csv")
    if not p.name.startswith("watchlist_diagnostics_must_watch_")
)
dates = [p.name.replace("watchlist_diagnostics_", "").replace("_diagnostics_v1.csv", "") for p in files]
print("daily_files", len(files))
print("first", dates[0] if dates else "")
print("last", dates[-1] if dates else "")

sample_rows = []
for p in files[:3] + files[-3:]:
    frame = pd.read_csv(p, nrows=1)
    sample_rows.append((p.name, ",".join(frame.columns)))
print("sample_schema_count", len(set(schema for _, schema in sample_rows)))
for name, schema in sample_rows:
    print(name, schema[:240])
PY
```

Expected:

```text
daily_files should match the number of 2024 trading days available under manual_v1, around 242
first 2024-01-02
last 2024-12-31
sample_schema_count 1
```

Stop if `daily_files < 230` or `last` is before `2024-12-31`.

---

### Task 3: Merge Daily Diagnostics And Build Regime Files

**Files:**
- Create: `outputs/research/watchlist_diagnostics_20240102_20241231/watchlist_diagnostics_2024_full.csv`
- Create: `outputs/research/industry_mainline_regime_20240102_20241231/industry_mainline_regime_diagnostics.csv`
- Create: `outputs/research/industry_mainline_regime_20240102_20241231/market_regime_diagnostics.csv`

- [ ] **Step 1: Merge daily diagnostics**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

path = Path("outputs/research/watchlist_diagnostics_20240102_20241231")
files = sorted(
    p for p in path.glob("watchlist_diagnostics_2024-*_diagnostics_v1.csv")
    if not p.name.startswith("watchlist_diagnostics_must_watch_")
)
if not files:
    raise SystemExit("no daily diagnostics files found")

frames = [pd.read_csv(p, low_memory=False) for p in files]
merged = pd.concat(frames, ignore_index=True)
merged.to_csv(path / "watchlist_diagnostics_2024_full.csv", index=False)

dates = pd.to_datetime(merged["trade_date"], errors="coerce")
print("rows", len(merged))
print("dates", dates.min().date(), dates.max().date(), dates.nunique())
print("output", path / "watchlist_diagnostics_2024_full.csv")
PY
```

Expected:

```text
rows approximately daily_files * 50
dates 2024-01-02 2024-12-31
```

- [ ] **Step 2: Build industry mainline regime diagnostics**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.cli industry-mainline-regime-diagnostics \
  --diagnostics-path outputs/research/watchlist_diagnostics_20240102_20241231/watchlist_diagnostics_2024_full.csv \
  --start-date 2024-01-02 \
  --end-date 2024-12-31 \
  --output-dir outputs/research/industry_mainline_regime_20240102_20241231
```

Expected:

```text
industry_mainline_regime|diagnostics|outputs/research/industry_mainline_regime_20240102_20241231/industry_mainline_regime_diagnostics.csv
industry_mainline_regime|market_regimes|outputs/research/industry_mainline_regime_20240102_20241231/market_regime_diagnostics.csv
```

- [ ] **Step 3: Validate regime coverage**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
import pandas as pd

market = pd.read_csv("outputs/research/industry_mainline_regime_20240102_20241231/market_regime_diagnostics.csv")
mainline = pd.read_csv("outputs/research/industry_mainline_regime_20240102_20241231/industry_mainline_regime_diagnostics.csv")

market_dates = pd.to_datetime(market["rebalance_date"], errors="coerce")
mainline_dates = pd.to_datetime(mainline["rebalance_date"], errors="coerce")

print("market_rows", len(market), market_dates.min().date(), market_dates.max().date(), market_dates.nunique())
print(market["market_regime"].value_counts(dropna=False).to_string())
print("mainline_rows", len(mainline), mainline_dates.min().date(), mainline_dates.max().date(), mainline_dates.nunique())
print(mainline["mainline_tag"].value_counts(dropna=False).head(10).to_string())
PY
```

Expected:

```text
market rows cover 2024-01-02 to 2024-12-31
market_regime contains mainline, rotation, broad_market, or weak_market
mainline rows cover the same date range
mainline_tag is not all unknown
```

Stop if `market_regime` is all `unknown` or if `mainline_tag` is all missing.

---

### Task 4: Build Aligned 2024 Discovery Pool And Funnel

**Files:**
- Create/update: `outputs/research/strong_winner_discovery_pool_20230101_20250101/strong_winner_discovery_pool_detail.csv`
- Create: `outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv`

- [ ] **Step 1: Rebuild or reuse discovery pool**

If `outputs/research/strong_winner_discovery_pool_20230101_20250101/strong_winner_discovery_pool_detail.csv` exists and covers 2024, reuse it. Validate:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
import pandas as pd
from pathlib import Path

p = Path("outputs/research/strong_winner_discovery_pool_20230101_20250101/strong_winner_discovery_pool_detail.csv")
if not p.exists():
    raise SystemExit("missing discovery pool; run rebuild command")

frame = pd.read_csv(p, usecols=["trade_date"])
dates = pd.to_datetime(frame["trade_date"], errors="coerce")
print("rows", len(frame))
print("dates", dates.min().date(), dates.max().date(), dates.nunique())
PY
```

If missing, rebuild:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.cli build-strong-winner-discovery-pool \
  --start-date 2023-01-01 \
  --end-date 2025-01-01 \
  --score-version manual_v1 \
  --adjust-type qfq \
  --output-dir outputs/research/strong_winner_discovery_pool_20230101_20250101
```

Expected:

```text
dates 2024-01-02 2024-12-31
```

- [ ] **Step 2: Build aligned funnel using 2024 regime files**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.cli build-mid-trend-watch-funnel \
  --discovery-pool-path outputs/research/strong_winner_discovery_pool_20230101_20250101/strong_winner_discovery_pool_detail.csv \
  --market-regime-path outputs/research/industry_mainline_regime_20240102_20241231/market_regime_diagnostics.csv \
  --industry-mainline-path outputs/research/industry_mainline_regime_20240102_20241231/industry_mainline_regime_diagnostics.csv \
  --output-dir outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned
```

Expected:

```text
mid_trend_watch_funnel|detail|outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv
mid_trend_watch_funnel|rows|121000
```

- [ ] **Step 3: Validate funnel context is no longer missing**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
import pandas as pd

p = "outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv"
frame = pd.read_csv(p, low_memory=False)
dates = pd.to_datetime(frame["trade_date"], errors="coerce")
print("rows", len(frame), "dates", dates.min().date(), dates.max().date(), dates.nunique())
for column in ["market_regime", "mainline_status", "industry_mainline_score_v1", "mainline_context"]:
    print("")
    print(column)
    print(frame[column].value_counts(dropna=False).head(12).to_string())
PY
```

Expected:

```text
market_regime is not all unknown
mainline_status is not all unknown
industry_mainline_score_v1 has non-null numeric values
```

Stop if these fields remain all missing or all `unknown`.

---

### Task 5: Validate Shadow Top5 Has Signals Before Overlay

**Files:**
- Read: `outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv`

- [ ] **Step 1: Build primary and buffer signals in memory**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
import pandas as pd
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame

p = "outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv"
detail = pd.read_csv(p, low_memory=False)
primary = build_mid_trend_shadow_top10_from_frame(detail, top_n=5)["top10"]
buffer = build_mid_trend_shadow_top10_from_frame(detail, top_n=10)["top10"]

print("primary_rows", len(primary), "dates", primary["trade_date"].nunique() if not primary.empty else 0)
print("buffer_rows", len(buffer), "dates", buffer["trade_date"].nunique() if not buffer.empty else 0)
print(primary.head(10).to_string(index=False))
PY
```

Expected:

```text
primary_rows > 0
buffer_rows >= primary_rows
dates should cover most available 2024 rebalance dates
```

Stop if `primary_rows = 0`.

---

### Task 6: Run Strict 2024 Intraday Overlay Backtest

**Files:**
- Create: `outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned/`

- [ ] **Step 1: Run baseline + 0.4/0.4 overlay**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
from stock_research.mid_trend_intraday_risk_overlay import run_mid_trend_intraday_risk_overlay_backtest

result = run_mid_trend_intraday_risk_overlay_backtest(
    funnel_detail_path="outputs/research/mid_trend_watch_funnel_20240102_20241231_aligned/mid_trend_watch_funnel_detail.csv",
    start_date="2024-01-02",
    end_date="2024-12-31",
    output_dir="outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned",
    filter_mode="high_only_new_entry",
    tail_confirmation_zscore_threshold=0.4,
    reversal_zscore_threshold=0.4,
    high_rank_penalty=8.0,
    high_risk_action="penalty",
)
print(result["summary"].to_string(index=False))
print(result["paths"])
PY
```

Expected:

```text
summary has 2 rows
baseline periods > 0
filtered periods > 0
```

- [ ] **Step 2: Extract headline metrics**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
import pandas as pd

p = "outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned/mid_trend_intraday_risk_overlay_summary.csv"
summary = pd.read_csv(p)
for _, row in summary.iterrows():
    print(row["variant_name"])
    print("  total_return_pct", round(float(row["total_return"]) * 100, 2))
    print("  annualized_return_pct", round(float(row["annualized_return"]) * 100, 2))
    print("  max_drawdown_pct", round(float(row["max_drawdown"]) * 100, 2))
    print("  sharpe", round(float(row["sharpe_ratio"]), 3))
    print("  average_turnover_pct", round(float(row["average_turnover"]) * 100, 2))
    print("  trade_rows", int(row["trade_rows"]))
    if "total_return_delta_vs_baseline" in row:
        print("  return_delta_pp", round(float(row["total_return_delta_vs_baseline"]) * 100, 2))
        print("  drawdown_delta_pp", round(float(row["max_drawdown_delta_vs_baseline"]) * 100, 2))
PY
```

Expected:

```text
filtered row shows whether 0.4/0.4 improves or damages 2024 baseline
```

---

### Task 7: Produce Robustness Decision Report

**Files:**
- Create: `outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned/robustness_decision.md`

- [ ] **Step 1: Write decision report**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

out = Path("outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned")
summary = pd.read_csv(out / "mid_trend_intraday_risk_overlay_summary.csv")
risk = pd.read_csv(out / "mid_trend_intraday_risk_overlay_risk_distribution.csv")

baseline = summary.iloc[0]
filtered = summary.iloc[1]

lines = [
    "# Mid Trend 0.4/0.4 Historical Robustness Decision",
    "",
    "## Scope",
    "- strict comparable window: 2024-01-02 to 2024-12-31",
    "- strategy: top5_weekly_max2_selective_trend_holding_protection_v1",
    "- overlay: high_only_new_entry, tail_z=0.4, reversal_z=0.4, high_rank_penalty=8",
    "- transaction_cost_bps: inherited from overlay module default unless explicitly changed",
    "",
    "## Baseline",
    f"- total_return: {float(baseline['total_return']) * 100:.2f}%",
    f"- annualized_return: {float(baseline['annualized_return']) * 100:.2f}%",
    f"- max_drawdown: {float(baseline['max_drawdown']) * 100:.2f}%",
    f"- sharpe: {float(baseline['sharpe_ratio']):.3f}",
    f"- average_turnover: {float(baseline['average_turnover']) * 100:.2f}%",
    "",
    "## Filtered",
    f"- total_return: {float(filtered['total_return']) * 100:.2f}%",
    f"- annualized_return: {float(filtered['annualized_return']) * 100:.2f}%",
    f"- max_drawdown: {float(filtered['max_drawdown']) * 100:.2f}%",
    f"- sharpe: {float(filtered['sharpe_ratio']):.3f}",
    f"- average_turnover: {float(filtered['average_turnover']) * 100:.2f}%",
    "",
    "## Delta",
    f"- total_return_delta: {float(filtered['total_return_delta_vs_baseline']) * 100:.2f}pp",
    f"- max_drawdown_delta: {float(filtered['max_drawdown_delta_vs_baseline']) * 100:.2f}pp",
    "",
    "## Risk Distribution",
    risk.to_markdown(index=False),
    "",
    "## Decision Rule",
    "- Pass: filtered total return is positive, max drawdown is not materially worse than baseline, and overlay does not turn a profitable baseline into a loss.",
    "- Watch: filtered total return is positive but return delta is negative or drawdown worsens by more than 2pp.",
    "- Fail: filtered total return is negative, or drawdown worsens by more than 5pp, or periods/trades are too sparse to evaluate.",
]

(out / "robustness_decision.md").write_text("\\n".join(lines) + "\\n", encoding="utf-8")
print(out / "robustness_decision.md")
PY
```

Expected:

```text
outputs/research/mid_trend_intraday_risk_overlay_20240102_20241231_t04_aligned/robustness_decision.md
```

- [ ] **Step 2: Final sanity checks**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/pytest tests/test_mid_trend_intraday_risk_overlay.py tests/test_mid_trend_shadow_weekly_control.py -q
git status --short
```

Expected:

```text
tests pass
git status shows no modified source files caused by this plan
new output directories may be untracked or ignored depending on repo settings
```

---

## Decision Criteria

The 2024 strict historical test should be interpreted as follows:

- **Can proceed to shadow with stronger confidence** if `0.4/0.4` remains profitable, improves or roughly preserves drawdown, and does not depend on 2025-only market behavior.
- **Keep as shadow only** if 2024 is profitable but weaker than baseline or drawdown control is unstable.
- **Do not promote to live capital** if 2024 filtered return is negative, drawdown expands materially, or the overlay only works in 2025-2026.

---

## Known Constraints

- `2023-01-01` to `2023-12-31` cannot be strictly tested with `manual_v1` unless historical score rows are backfilled or another score version is proven equivalent.
- A fallback that treats `unknown` regime as `broad_market` is not a strict strategy test because it bypasses the current mid trend mainline filters.
- The strict 2024 test requires full `watchlist diagnostics` coverage first; otherwise `market_regime` and `mainline_status` remain missing and shadow top5 produces zero signals.

---

## Self-Review

- Spec coverage: The plan covers data audit, diagnostics build, regime build, aligned funnel generation, pre-overlay signal validation, strict overlay backtest, and decision reporting.
- Placeholder scan: No task depends on undefined commands or unspecified files.
- Type consistency: Date columns are consistently treated as `trade_date` for daily diagnostics/funnel and `rebalance_date` for regime files.
