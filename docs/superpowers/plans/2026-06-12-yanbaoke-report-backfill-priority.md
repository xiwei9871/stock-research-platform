# Yanbaoke Report Backfill Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a quota-aware Yanbaoke research-report backfill planner that ranks candidates by report type, stock importance, sector priority, broker quality, time window, and coverage gaps before any large download run.

**Architecture:** Add a planning-only module that accepts Yanbaoke candidate metadata and existing report coverage, writes prioritized CSV/Markdown artifacts, and exposes a CLI command. It reuses existing stock-report downstream concepts without downloading PDFs in this scope.

**Tech Stack:** Python 3, pandas, pytest, argparse CLI, existing `stock_research` package structure.

---

## File Structure

- Create `config/yanbaoke_sector_priority.csv`
  - Static sector/theme priority mapping and pilot quota buckets.
- Create `src/stock_research/yanbaoke_report_backfill.py`
  - Pure pandas planner: normalization, scoring, gap matrices, sector-quota pilot queue, Markdown report.
- Create `tests/test_yanbaoke_report_backfill.py`
  - Focused unit tests for deterministic scoring, gap output, sector quotas, and artifact writing.
- Modify `src/stock_research/cli.py`
  - Add `yanbaoke-report-backfill-plan` parser and dispatch.
- Modify `tests/test_factor_cli.py`
  - Add parser and dispatch tests for the new CLI command.
- Create `docs/ops/yanbaoke-report-backfill-runbook.md`
  - Operator runbook for the first inventory and pilot sequence.

## Task 1: Sector Priority Config

**Files:**
- Create: `config/yanbaoke_sector_priority.csv`
- Test: `tests/test_yanbaoke_report_backfill.py`

- [ ] **Step 1: Write the failing config loader test**

Add this to new file `tests/test_yanbaoke_report_backfill.py`:

```python
from pathlib import Path

import pandas as pd

from stock_research.yanbaoke_report_backfill import load_sector_priority_config


def test_load_sector_priority_config_contains_default_quota_buckets():
    config = load_sector_priority_config()

    assert set(config["sector_priority"]) >= {"P0", "P1", "P2", "P3"}
    assert config.loc[config["sector_priority"].eq("P0"), "pilot_quota"].max() == 1200
    assert "AI算力" in set(config["sector_name"])
    assert "半导体" in set(config["sector_name"])
    assert "银行" in set(config["sector_name"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_load_sector_priority_config_contains_default_quota_buckets
```

Expected: FAIL because `stock_research.yanbaoke_report_backfill` does not exist.

- [ ] **Step 3: Add the sector priority CSV**

Create `config/yanbaoke_sector_priority.csv`:

```csv
sector_name,match_keywords,sector_priority,sector_quota_bucket,pilot_quota
AI算力,AI算力|算力|服务器|光模块|液冷|数据中心,P0,p0_growth_tech_healthcare,1200
半导体,半导体|先进封装|芯片|晶圆|国产替代,P0,p0_growth_tech_healthcare,1200
机器人,机器人|减速器|伺服|人形机器人,P0,p0_growth_tech_healthcare,1200
低空经济,低空经济|eVTOL|无人机|通航,P0,p0_growth_tech_healthcare,1200
智能驾驶,智能驾驶|自动驾驶|车路云|激光雷达,P0,p0_growth_tech_healthcare,1200
创新药,创新药|医疗器械|CXO|医药研发,P0,p0_growth_tech_healthcare,1200
电力设备新能源,电力设备|新能源|储能|电网|光伏|风电,P1,p1_policy_prosperity_export_consumption,900
军工卫星,军工|卫星|商业航天|北斗,P1,p1_policy_prosperity_export_consumption,900
出海链,出海|跨境电商|工程机械|家电|海外收入,P1,p1_policy_prosperity_export_consumption,900
消费复苏,消费复苏|食品饮料|旅游|酒店|医美,P1,p1_policy_prosperity_export_consumption,900
金融地产,银行|保险|券商|地产|房地产,P2,p2_finance_real_estate_cycle_macro,500
周期资源,煤炭|有色|化工|钢铁|资源品,P2,p2_finance_real_estate_cycle_macro,500
宏观策略,宏观|策略|固收|海外配置|资产配置,P2,cross_sector_macro_theme,300
普通长尾,短评|晨会|日报|普通点评,P3,p3_long_tail,0
```

- [ ] **Step 4: Implement the config loader**

Create `src/stock_research/yanbaoke_report_backfill.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECTOR_PRIORITY_PATH = PROJECT_ROOT / "config" / "yanbaoke_sector_priority.csv"


def load_sector_priority_config(path: str | Path | None = None) -> pd.DataFrame:
    config_path = Path(path) if path is not None else DEFAULT_SECTOR_PRIORITY_PATH
    frame = pd.read_csv(config_path, dtype="string").fillna("")
    required = {"sector_name", "match_keywords", "sector_priority", "sector_quota_bucket", "pilot_quota"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"sector priority config missing columns: {sorted(missing)}")
    frame["pilot_quota"] = pd.to_numeric(frame["pilot_quota"], errors="coerce").fillna(0).astype(int)
    return frame
```

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_load_sector_priority_config_contains_default_quota_buckets
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/yanbaoke_sector_priority.csv src/stock_research/yanbaoke_report_backfill.py tests/test_yanbaoke_report_backfill.py
git commit -m "feat: add yanbaoke sector priority config"
```

## Task 2: Candidate Normalization And Scoring

**Files:**
- Modify: `src/stock_research/yanbaoke_report_backfill.py`
- Modify: `tests/test_yanbaoke_report_backfill.py`

- [ ] **Step 1: Write the failing scoring test**

Append to `tests/test_yanbaoke_report_backfill.py`:

```python
from stock_research.yanbaoke_report_backfill import build_scored_candidates


def test_build_scored_candidates_prioritizes_deep_p0_missing_coverage():
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头成长空间打开",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            },
            {
                "report_id": "r2",
                "report_date": "2025-03-01",
                "title": "晨会纪要",
                "broker": "普通证券",
                "stock_code": "000002.SZ",
                "stock_name": "普通公司",
                "industry_lv1": "综合",
                "industry_lv2": "普通长尾",
                "theme": "",
            },
        ]
    )
    existing = pd.DataFrame(
        columns=["report_date", "normalized_title", "normalized_broker", "stock_code", "report_type"]
    )

    scored = build_scored_candidates(candidates, existing_coverage=existing)

    top = scored.sort_values("priority_score", ascending=False).iloc[0]
    assert top["report_id"] == "r1"
    assert top["report_type_bucket"] == "P1"
    assert top["sector_priority"] == "P0"
    assert top["sector_quota_bucket"] == "p0_growth_tech_healthcare"
    assert top["coverage_gap_reason"] == "missing_asset_report"
    assert top["priority_score"] > scored.loc[scored["report_id"].eq("r2"), "priority_score"].iloc[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_build_scored_candidates_prioritizes_deep_p0_missing_coverage
```

Expected: FAIL because `build_scored_candidates` is not implemented.

- [ ] **Step 3: Implement deterministic scoring**

Replace `src/stock_research/yanbaoke_report_backfill.py` with the Task 1 content plus:

```python
A_TIER_BROKER_KEYWORDS = (
    "中信证券",
    "中金",
    "华泰",
    "国泰君安",
    "国泰海通",
    "招商证券",
    "海通证券",
    "广发证券",
    "中信建投",
    "申万宏源",
    "兴业证券",
    "国信证券",
    "光大证券",
    "东吴证券",
    "高盛",
    "摩根士丹利",
    "摩根大通",
    "花旗",
    "瑞银",
    "汇丰",
)


def build_scored_candidates(
    candidates: pd.DataFrame,
    *,
    existing_coverage: pd.DataFrame | None = None,
    sector_config: pd.DataFrame | None = None,
) -> pd.DataFrame:
    sector_rules = sector_config if sector_config is not None else load_sector_priority_config()
    existing = existing_coverage.copy() if existing_coverage is not None else pd.DataFrame()
    frame = _normalize_candidate_columns(candidates)
    frame["normalized_title"] = frame["title"].map(_normalize_text)
    frame["normalized_broker"] = frame["broker"].map(_normalize_text)
    frame["report_type_bucket"] = frame["title"].map(classify_report_type_bucket)
    sector_fields = frame.apply(lambda row: _classify_sector(row, sector_rules), axis=1, result_type="expand")
    frame[["theme_bucket", "sector_priority", "sector_quota_bucket", "sector_pilot_quota"]] = sector_fields
    frame["asset_priority"] = frame.apply(_asset_priority, axis=1)
    frame["coverage_gap_reason"] = frame.apply(lambda row: _coverage_gap_reason(row, existing), axis=1)
    frame["priority_score"] = frame.apply(_priority_score, axis=1)
    frame = frame.sort_values(["priority_score", "report_date", "report_id"], ascending=[False, False, True]).reset_index(drop=True)
    return frame


def _normalize_candidate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    defaults = {
        "report_id": "",
        "report_date": "",
        "title": "",
        "broker": "",
        "stock_code": "",
        "stock_name": "",
        "industry_lv1": "",
        "industry_lv2": "",
        "theme": "",
    }
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = default
    for column in defaults:
        result[column] = result[column].astype("string").fillna("").str.strip()
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    result["report_id"] = result.apply(
        lambda row: row["report_id"] or "|".join([row["report_date"], row["broker"], row["stock_code"], row["title"]]),
        axis=1,
    )
    return result


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def classify_report_type_bucket(title: Any) -> str:
    text = str(title or "")
    if any(keyword in text for keyword in ["深度", "首次覆盖", "行业策略", "年度策略", "中期策略", "专题", "框架"]):
        return "P1"
    if any(keyword in text for keyword in ["业绩", "点评", "预告", "季报", "年报", "评级", "目标价", "政策"]):
        return "P2"
    return "P3"


def _classify_sector(row: pd.Series, sector_rules: pd.DataFrame) -> pd.Series:
    haystack = "|".join(str(row.get(column, "")) for column in ["title", "industry_lv1", "industry_lv2", "theme"])
    for rule in sector_rules.to_dict("records"):
        keywords = [item for item in str(rule["match_keywords"]).split("|") if item]
        if any(keyword in haystack for keyword in keywords):
            return pd.Series(
                [
                    str(rule["sector_name"]),
                    str(rule["sector_priority"]),
                    str(rule["sector_quota_bucket"]),
                    int(rule["pilot_quota"]),
                ]
            )
    return pd.Series(["未分类", "P3", "p3_long_tail", 0])


def _asset_priority(row: pd.Series) -> str:
    stock_code = str(row.get("stock_code", "")).strip()
    stock_name = str(row.get("stock_name", "")).strip()
    if stock_code or stock_name:
        return "core_candidate"
    return "cross_sector"


def _coverage_gap_reason(row: pd.Series, existing: pd.DataFrame) -> str:
    if existing.empty:
        return "missing_asset_report" if str(row.get("stock_code", "")).strip() else "missing_sector_report"
    normalized = existing.copy()
    for column in ["stock_code", "normalized_title", "normalized_broker"]:
        if column not in normalized.columns:
            normalized[column] = ""
        normalized[column] = normalized[column].astype("string").fillna("").map(_normalize_text)
    same_asset = normalized["stock_code"].eq(_normalize_text(row.get("stock_code", "")))
    same_title = normalized["normalized_title"].eq(_normalize_text(row.get("title", "")))
    same_broker = normalized["normalized_broker"].eq(_normalize_text(row.get("broker", "")))
    if bool((same_asset & same_title & same_broker).any()):
        return "existing_duplicate"
    if str(row.get("stock_code", "")).strip() and not bool(same_asset.any()):
        return "missing_asset_report"
    return "missing_sector_report"


def _priority_score(row: pd.Series) -> float:
    report_type_score = {"P1": 30, "P2": 20, "P3": 5}.get(str(row.get("report_type_bucket")), 0)
    sector_score = {"P0": 25, "P1": 18, "P2": 10, "P3": 0}.get(str(row.get("sector_priority")), 0)
    broker = str(row.get("broker", ""))
    broker_score = 20 if any(keyword in broker for keyword in A_TIER_BROKER_KEYWORDS) else 8
    date = pd.to_datetime(row.get("report_date"), errors="coerce")
    time_score = 15 if pd.notna(date) and date >= pd.Timestamp("2026-01-01") else 8
    gap_score = {
        "missing_asset_report": 10,
        "missing_sector_report": 8,
        "existing_duplicate": -30,
    }.get(str(row.get("coverage_gap_reason")), 0)
    return float(report_type_score + sector_score + broker_score + time_score + gap_score)
```

- [ ] **Step 4: Run the scoring tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_load_sector_priority_config_contains_default_quota_buckets tests/test_yanbaoke_report_backfill.py::test_build_scored_candidates_prioritizes_deep_p0_missing_coverage
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/yanbaoke_report_backfill.py tests/test_yanbaoke_report_backfill.py
git commit -m "feat: score yanbaoke report candidates"
```

## Task 3: Gap Matrices And Artifact Writer

**Files:**
- Modify: `src/stock_research/yanbaoke_report_backfill.py`
- Modify: `tests/test_yanbaoke_report_backfill.py`

- [ ] **Step 1: Write the failing artifact test**

Append:

```python
from stock_research.yanbaoke_report_backfill import build_yanbaoke_inventory_plan


def test_build_yanbaoke_inventory_plan_writes_gap_matrices(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            },
            {
                "report_id": "r2",
                "report_date": "2025-08-10",
                "title": "行业深度：银行资产质量",
                "broker": "招商证券",
                "stock_code": "",
                "stock_name": "",
                "industry_lv1": "银行",
                "industry_lv2": "银行",
                "theme": "银行",
            },
        ]
    )

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["candidate_reports"]).exists()
    assert Path(result["paths"]["sector_gap_matrix"]).exists()
    assert Path(result["paths"]["asset_gap_matrix"]).exists()
    assert Path(result["paths"]["priority_queue"]).exists()
    assert Path(result["paths"]["report"]).exists()
    sector_gap = pd.read_csv(result["paths"]["sector_gap_matrix"])
    assert set(sector_gap["sector_priority"]) >= {"P0", "P2"}
    assert "Yanbaoke Report Backfill Inventory" in Path(result["paths"]["report"]).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_build_yanbaoke_inventory_plan_writes_gap_matrices
```

Expected: FAIL because `build_yanbaoke_inventory_plan` is not implemented.

- [ ] **Step 3: Implement gap matrices and writer**

Append to `src/stock_research/yanbaoke_report_backfill.py`:

```python
def build_yanbaoke_inventory_plan(
    *,
    candidates: pd.DataFrame,
    existing_coverage: pd.DataFrame | None,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    sector_config: pd.DataFrame | None = None,
) -> dict[str, Any]:
    scored = build_scored_candidates(candidates, existing_coverage=existing_coverage, sector_config=sector_config)
    windowed = scored.loc[scored["report_date"].between(start_date, end_date)].reset_index(drop=True)
    sector_gap = build_sector_gap_matrix(windowed)
    asset_gap = build_asset_gap_matrix(windowed)
    report = render_inventory_report(windowed, sector_gap, asset_gap, start_date=start_date, end_date=end_date)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "candidate_reports": output / "yanbaoke_candidate_reports.csv",
        "sector_gap_matrix": output / "yanbaoke_sector_gap_matrix.csv",
        "asset_gap_matrix": output / "yanbaoke_asset_gap_matrix.csv",
        "priority_queue": output / "yanbaoke_priority_queue.csv",
        "report": output / "yanbaoke_backfill_inventory_report.md",
    }
    windowed.to_csv(paths["candidate_reports"], index=False)
    sector_gap.to_csv(paths["sector_gap_matrix"], index=False)
    asset_gap.to_csv(paths["asset_gap_matrix"], index=False)
    windowed.to_csv(paths["priority_queue"], index=False)
    paths["report"].write_text(report, encoding="utf-8")
    return {
        "candidates": windowed,
        "sector_gap_matrix": sector_gap,
        "asset_gap_matrix": asset_gap,
        "priority_queue": windowed,
        "report": report,
        "paths": {key: str(value) for key, value in paths.items()},
    }


def build_sector_gap_matrix(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(columns=["sector_priority", "theme_bucket", "candidate_count", "p1_count", "p2_count", "duplicate_count"])
    grouped = scored.groupby(["sector_priority", "theme_bucket"], dropna=False).agg(
        candidate_count=("report_id", "count"),
        p1_count=("report_type_bucket", lambda values: int((values == "P1").sum())),
        p2_count=("report_type_bucket", lambda values: int((values == "P2").sum())),
        duplicate_count=("coverage_gap_reason", lambda values: int((values == "existing_duplicate").sum())),
        max_priority_score=("priority_score", "max"),
    )
    return grouped.reset_index().sort_values(["sector_priority", "max_priority_score"], ascending=[True, False])


def build_asset_gap_matrix(scored: pd.DataFrame) -> pd.DataFrame:
    asset_rows = scored.loc[scored["stock_code"].astype(str).str.len().gt(0)].copy()
    if asset_rows.empty:
        return pd.DataFrame(columns=["stock_code", "stock_name", "theme_bucket", "candidate_count", "best_priority_score"])
    grouped = asset_rows.groupby(["stock_code", "stock_name", "theme_bucket"], dropna=False).agg(
        candidate_count=("report_id", "count"),
        best_priority_score=("priority_score", "max"),
        p1_count=("report_type_bucket", lambda values: int((values == "P1").sum())),
    )
    return grouped.reset_index().sort_values(["best_priority_score", "candidate_count"], ascending=[False, False])


def render_inventory_report(
    scored: pd.DataFrame,
    sector_gap: pd.DataFrame,
    asset_gap: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> str:
    lines = [
        "# Yanbaoke Report Backfill Inventory",
        "",
        f"- Window: `{start_date}` to `{end_date}`",
        f"- Candidate reports: `{len(scored)}`",
        f"- Sector groups: `{len(sector_gap)}`",
        f"- Asset groups: `{len(asset_gap)}`",
        "",
        "## Priority Distribution",
        "",
    ]
    if scored.empty:
        lines.append("No candidate reports in the requested window.")
    else:
        distribution = scored.groupby(["sector_priority", "report_type_bucket"]).size().reset_index(name="count")
        lines.append(distribution.to_markdown(index=False))
    lines.extend(["", "## Top Sector Gaps", ""])
    lines.append(sector_gap.head(20).to_markdown(index=False) if not sector_gap.empty else "No sector gaps.")
    lines.extend(["", "## Top Asset Gaps", ""])
    lines.append(asset_gap.head(20).to_markdown(index=False) if not asset_gap.empty else "No asset gaps.")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run artifact tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/yanbaoke_report_backfill.py tests/test_yanbaoke_report_backfill.py
git commit -m "feat: write yanbaoke inventory gap matrices"
```

## Task 4: Sector-Quota Pilot Queue

**Files:**
- Modify: `src/stock_research/yanbaoke_report_backfill.py`
- Modify: `tests/test_yanbaoke_report_backfill.py`

- [ ] **Step 1: Write the failing pilot queue test**

Append:

```python
from stock_research.yanbaoke_report_backfill import build_sector_quota_pilot_queue


def test_build_sector_quota_pilot_queue_respects_bucket_caps():
    rows = []
    for idx in range(5):
        rows.append(
            {
                "report_id": f"p0-{idx}",
                "report_date": "2026-04-20",
                "title": f"公司深度报告：AI算力 {idx}",
                "broker": "中信证券",
                "stock_code": f"00000{idx}.SZ",
                "stock_name": f"算力{idx}",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            }
        )
    for idx in range(5):
        rows.append(
            {
                "report_id": f"p2-{idx}",
                "report_date": "2025-08-10",
                "title": f"行业深度：银行 {idx}",
                "broker": "招商证券",
                "stock_code": "",
                "stock_name": "",
                "industry_lv1": "银行",
                "industry_lv2": "银行",
                "theme": "银行",
            }
        )
    scored = build_scored_candidates(pd.DataFrame(rows), existing_coverage=pd.DataFrame())

    pilot = build_sector_quota_pilot_queue(
        scored,
        quota_by_bucket={"p0_growth_tech_healthcare": 2, "p2_finance_real_estate_cycle_macro": 1},
        total_limit=3,
    )

    assert len(pilot) == 3
    assert (pilot["sector_quota_bucket"] == "p0_growth_tech_healthcare").sum() == 2
    assert (pilot["sector_quota_bucket"] == "p2_finance_real_estate_cycle_macro").sum() == 1
    assert pilot["pilot_rank"].tolist() == [1, 2, 3]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_build_sector_quota_pilot_queue_respects_bucket_caps
```

Expected: FAIL because `build_sector_quota_pilot_queue` is not implemented.

- [ ] **Step 3: Implement sector-quota queue selection**

Append:

```python
DEFAULT_PILOT_QUOTA_BY_BUCKET = {
    "p0_growth_tech_healthcare": 1200,
    "p1_policy_prosperity_export_consumption": 900,
    "p2_finance_real_estate_cycle_macro": 500,
    "cross_sector_macro_theme": 300,
    "manual_correction_reserve": 100,
}


def build_sector_quota_pilot_queue(
    scored: pd.DataFrame,
    *,
    quota_by_bucket: dict[str, int] | None = None,
    total_limit: int = 3000,
) -> pd.DataFrame:
    quotas = quota_by_bucket or DEFAULT_PILOT_QUOTA_BY_BUCKET
    eligible = scored.loc[~scored["coverage_gap_reason"].eq("existing_duplicate")].copy()
    selected_frames = []
    selected_ids: set[str] = set()
    for bucket, quota in quotas.items():
        if bucket == "manual_correction_reserve" or quota <= 0:
            continue
        bucket_rows = eligible.loc[eligible["sector_quota_bucket"].eq(bucket)]
        bucket_rows = bucket_rows.sort_values(["priority_score", "report_date", "report_id"], ascending=[False, False, True]).head(quota)
        selected_frames.append(bucket_rows)
        selected_ids.update(bucket_rows["report_id"].astype(str).tolist())
    selected = pd.concat(selected_frames, ignore_index=True) if selected_frames else pd.DataFrame(columns=eligible.columns)
    if len(selected) < total_limit:
        remainder = eligible.loc[~eligible["report_id"].astype(str).isin(selected_ids)]
        remainder = remainder.sort_values(["priority_score", "report_date", "report_id"], ascending=[False, False, True])
        selected = pd.concat([selected, remainder.head(total_limit - len(selected))], ignore_index=True)
    selected = selected.head(total_limit).copy()
    selected["pilot_rank"] = range(1, len(selected) + 1)
    return selected
```

- [ ] **Step 4: Add pilot queue output to `build_yanbaoke_inventory_plan`**

Inside `build_yanbaoke_inventory_plan`, after `asset_gap = build_asset_gap_matrix(windowed)`, add:

```python
    pilot_queue = build_sector_quota_pilot_queue(windowed, total_limit=3000)
```

Update `paths`:

```python
        "pilot_queue": output / "yanbaoke_pilot_queue_top3000.csv",
```

Write it:

```python
    pilot_queue.to_csv(paths["pilot_queue"], index=False)
```

Return it:

```python
        "pilot_queue": pilot_queue,
```

- [ ] **Step 5: Run all Yanbaoke tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/yanbaoke_report_backfill.py tests/test_yanbaoke_report_backfill.py
git commit -m "feat: build sector quota yanbaoke pilot queue"
```

## Task 5: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write parser and dispatch tests**

Append to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_yanbaoke_report_backfill_plan_command():
    args = build_parser().parse_args(
        [
            "yanbaoke-report-backfill-plan",
            "--candidate-path",
            "inputs/yanbaoke_candidates.csv",
            "--existing-coverage-path",
            "inputs/existing_report_coverage.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-12",
            "--output-dir",
            "outputs/research/yanbaoke_backfill",
        ]
    )

    assert args.command == "yanbaoke-report-backfill-plan"
    assert args.candidate_path == "inputs/yanbaoke_candidates.csv"
    assert args.existing_coverage_path == "inputs/existing_report_coverage.csv"
    assert args.start_date == "2025-01-01"
    assert args.end_date == "2026-06-12"
    assert args.output_dir == "outputs/research/yanbaoke_backfill"


def test_cli_dispatches_yanbaoke_report_backfill_plan(monkeypatch, tmp_path, capsys):
    candidate_path = tmp_path / "candidates.csv"
    existing_path = tmp_path / "existing.csv"
    candidate_path.write_text("report_id,report_date,title,broker\nr1,2026-01-01,公司深度,中信证券\n", encoding="utf-8")
    existing_path.write_text("report_date,normalized_title,normalized_broker,stock_code\n", encoding="utf-8")
    calls = []

    def fake_plan(**kwargs):
        calls.append(kwargs)
        return {
            "candidates": pd.DataFrame([{"report_id": "r1"}]),
            "pilot_queue": pd.DataFrame([{"report_id": "r1"}]),
            "paths": {
                "candidate_reports": "out/candidates.csv",
                "sector_gap_matrix": "out/sector.csv",
                "asset_gap_matrix": "out/asset.csv",
                "priority_queue": "out/priority.csv",
                "pilot_queue": "out/pilot.csv",
                "report": "out/report.md",
            },
        }

    monkeypatch.setattr(cli, "build_yanbaoke_inventory_plan", fake_plan)
    args = build_parser().parse_args(
        [
            "yanbaoke-report-backfill-plan",
            "--candidate-path",
            str(candidate_path),
            "--existing-coverage-path",
            str(existing_path),
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-12",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    cli.main(args)

    assert calls[0]["start_date"] == "2025-01-01"
    assert calls[0]["end_date"] == "2026-06-12"
    output = capsys.readouterr().out
    assert "yanbaoke_report_backfill_plan|candidate_reports|out/candidates.csv" in output
    assert "yanbaoke_report_backfill_plan|pilot_queue|out/pilot.csv" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_yanbaoke_report_backfill_plan_command tests/test_factor_cli.py::test_cli_dispatches_yanbaoke_report_backfill_plan
```

Expected: FAIL because the parser does not know the command.

- [ ] **Step 3: Add CLI import**

In `src/stock_research/cli.py`, near other stock-report imports, add:

```python
from stock_research.yanbaoke_report_backfill import build_yanbaoke_inventory_plan
```

- [ ] **Step 4: Add CLI parser**

In `build_parser()`, near other stock-report commands, add:

```python
    yanbaoke_report_backfill_plan = subparsers.add_parser("yanbaoke-report-backfill-plan")
    yanbaoke_report_backfill_plan.add_argument("--candidate-path", required=True)
    yanbaoke_report_backfill_plan.add_argument("--existing-coverage-path")
    yanbaoke_report_backfill_plan.add_argument("--start-date", default="2025-01-01")
    yanbaoke_report_backfill_plan.add_argument("--end-date", default="2026-06-12")
    yanbaoke_report_backfill_plan.add_argument("--output-dir", default="outputs/research/yanbaoke_backfill")
```

- [ ] **Step 5: Add CLI dispatch**

In `main()`, near other stock-report dispatch branches, add:

```python
    elif args.command == "yanbaoke-report-backfill-plan":
        candidates = pd.read_csv(args.candidate_path, dtype="string", low_memory=False)
        existing_coverage = (
            pd.read_csv(args.existing_coverage_path, dtype="string", low_memory=False)
            if args.existing_coverage_path
            else pd.DataFrame()
        )
        result = build_yanbaoke_inventory_plan(
            candidates=candidates,
            existing_coverage=existing_coverage,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"yanbaoke_report_backfill_plan|candidate_reports|{result['paths']['candidate_reports']}")
        print(f"yanbaoke_report_backfill_plan|sector_gap_matrix|{result['paths']['sector_gap_matrix']}")
        print(f"yanbaoke_report_backfill_plan|asset_gap_matrix|{result['paths']['asset_gap_matrix']}")
        print(f"yanbaoke_report_backfill_plan|priority_queue|{result['paths']['priority_queue']}")
        print(f"yanbaoke_report_backfill_plan|pilot_queue|{result['paths']['pilot_queue']}")
        print(f"yanbaoke_report_backfill_plan|report|{result['paths']['report']}")
        print(f"yanbaoke_report_backfill_plan|candidate_rows|{len(result['candidates'])}")
        print(f"yanbaoke_report_backfill_plan|pilot_rows|{len(result['pilot_queue'])}")
```

- [ ] **Step 6: Run CLI tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_yanbaoke_report_backfill_plan_command tests/test_factor_cli.py::test_cli_dispatches_yanbaoke_report_backfill_plan
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add yanbaoke report backfill plan cli"
```

## Task 6: Runbook And Smoke Verification

**Files:**
- Create: `docs/ops/yanbaoke-report-backfill-runbook.md`
- Modify: `tests/test_yanbaoke_report_backfill.py`

- [ ] **Step 1: Add a smoke artifact test**

Append:

```python
def test_yanbaoke_inventory_plan_outputs_expected_columns(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            }
        ]
    )
    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    priority = pd.read_csv(result["paths"]["priority_queue"])
    expected_columns = {
        "report_id",
        "report_date",
        "title",
        "broker",
        "stock_code",
        "industry_lv1",
        "industry_lv2",
        "theme_bucket",
        "sector_priority",
        "sector_quota_bucket",
        "asset_priority",
        "coverage_gap_reason",
        "priority_score",
    }
    assert expected_columns.issubset(set(priority.columns))
```

- [ ] **Step 2: Run the smoke test**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py::test_yanbaoke_inventory_plan_outputs_expected_columns
```

Expected: PASS.

- [ ] **Step 3: Create the operator runbook**

Create `docs/ops/yanbaoke-report-backfill-runbook.md`:

```markdown
# Yanbaoke Report Backfill Runbook

## Purpose

Generate a quota-aware Yanbaoke candidate inventory and pilot queue for reports dated `2025-01-01` through `2026-06-12`.

## Inputs

- `inputs/yanbaoke_candidates.csv`: exported Yanbaoke metadata, one row per candidate report.
- `inputs/existing_report_coverage.csv`: existing internal coverage metadata.

Minimum candidate columns:

- `report_id`
- `report_date`
- `title`
- `broker`
- `stock_code`
- `stock_name`
- `industry_lv1`
- `industry_lv2`
- `theme`

## First Run

```bash
./.venv/bin/stock-research yanbaoke-report-backfill-plan \
  --candidate-path inputs/yanbaoke_candidates.csv \
  --existing-coverage-path inputs/existing_report_coverage.csv \
  --start-date 2025-01-01 \
  --end-date 2026-06-12 \
  --output-dir outputs/research/yanbaoke_backfill_20250101_20260612
```

## Outputs

- `yanbaoke_candidate_reports.csv`: normalized scored candidates.
- `yanbaoke_sector_gap_matrix.csv`: board and theme coverage matrix.
- `yanbaoke_asset_gap_matrix.csv`: stock-level gap matrix.
- `yanbaoke_priority_queue.csv`: full sorted queue.
- `yanbaoke_pilot_queue_top3000.csv`: first pilot download/import queue.
- `yanbaoke_backfill_inventory_report.md`: human review report.

## Review Gates

Before any large download:

- Confirm P0/P1 sectors dominate the pilot queue.
- Confirm Priority 3 reports are not more than 20% of the pilot queue.
- Confirm duplicate candidates are excluded from the pilot queue.
- Confirm unknown or misclassified sectors are reviewed from the sector gap matrix.

## Next Step After Review

Use `yanbaoke_pilot_queue_top3000.csv` as the approved input for the first controlled download/import batch. Recompute this plan after every 1,000 imported reports using refreshed existing coverage.
```

- [ ] **Step 4: Run focused verification**

Run:

```bash
./.venv/bin/pytest -q tests/test_yanbaoke_report_backfill.py tests/test_factor_cli.py::test_cli_accepts_yanbaoke_report_backfill_plan_command tests/test_factor_cli.py::test_cli_dispatches_yanbaoke_report_backfill_plan
```

Expected: PASS.

- [ ] **Step 5: Run CLI smoke with a small fixture**

Create temporary input files under `/tmp/yanbaoke_smoke`:

```bash
mkdir -p /tmp/yanbaoke_smoke
printf 'report_id,report_date,title,broker,stock_code,stock_name,industry_lv1,industry_lv2,theme\nr1,2026-04-20,公司深度报告：AI算力龙头,中信证券,000001.SZ,算力龙头,计算机,AI算力,AI算力\n' > /tmp/yanbaoke_smoke/candidates.csv
printf 'report_date,normalized_title,normalized_broker,stock_code\n' > /tmp/yanbaoke_smoke/existing.csv
./.venv/bin/stock-research yanbaoke-report-backfill-plan \
  --candidate-path /tmp/yanbaoke_smoke/candidates.csv \
  --existing-coverage-path /tmp/yanbaoke_smoke/existing.csv \
  --start-date 2025-01-01 \
  --end-date 2026-06-12 \
  --output-dir /tmp/yanbaoke_smoke/out
```

Expected output includes:

```text
yanbaoke_report_backfill_plan|candidate_reports|/tmp/yanbaoke_smoke/out/yanbaoke_candidate_reports.csv
yanbaoke_report_backfill_plan|pilot_queue|/tmp/yanbaoke_smoke/out/yanbaoke_pilot_queue_top3000.csv
yanbaoke_report_backfill_plan|pilot_rows|1
```

- [ ] **Step 6: Commit**

```bash
git add docs/ops/yanbaoke-report-backfill-runbook.md tests/test_yanbaoke_report_backfill.py
git commit -m "docs: add yanbaoke report backfill runbook"
```

## Self-Review Checklist

- Spec coverage: sector priority, stock and sector candidate organization, pilot quota split, gap matrices, and CLI output are covered.
- Placeholder scan: this plan contains concrete file paths, commands, expected outputs, and implementation snippets.
- Type consistency: `build_yanbaoke_inventory_plan`, `build_scored_candidates`, `build_sector_quota_pilot_queue`, and CLI output keys use consistent names across tasks.
