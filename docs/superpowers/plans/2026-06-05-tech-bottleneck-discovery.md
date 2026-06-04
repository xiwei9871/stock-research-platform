# Tech Bottleneck Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated `tech-bottleneck-discovery` research lens that scores existing candidates, generates cited evidence packets, writes JSON/Markdown outputs, and leaves humans only with review decisions.

**Architecture:** Add one focused pure-Python module for scoring and packet generation, then add a thin CLI wrapper that loads CSV/JSON inputs and writes deterministic artifacts. Keep persistence file-based in v1 so the feature can run against existing candidate pools without schema churn; later phases can import outputs into shadow review read models.

**Tech Stack:** Python 3.11+, pandas, argparse CLI, pytest, existing `stock_research` package conventions.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_discovery.py`
  - Owns score dimensions, candidate state transitions, evidence tier validation, packet generation, markdown rendering, and artifact writing.
- Modify `src/stock_research/cli.py`
  - Adds a `tech-bottleneck-discovery` command that loads candidates/evidence/context files and writes automated research packets.
- Create `tests/test_tech_bottleneck_discovery.py`
  - Unit tests for scoring, evidence promotion rules, packet content, markdown rendering, output writing, and CLI-facing behavior.
- Optional later, not in this plan: database schema, dashboard panel, LLM retrieval adapters, social-source ingestion.

## Data Contracts

### Candidate Input Columns

Required:

- `asset_id`
- `stock_name`
- `trade_date`
- `terminal_demand`
- `supply_chain_node`
- `company_exposure`

Optional numeric scores, all normalized to 0-5 if present:

- `terminal_demand_certainty`
- `single_point_importance`
- `supply_concentration`
- `capacity_expansion_difficulty`
- `technical_barrier`
- `qualification_or_customer_switching_cost`
- `substitution_difficulty`
- `value_capture_power`
- `market_cap_room`
- `low_sell_side_coverage`
- `low_institutional_attention`
- `old_business_mispricing`
- `new_business_not_in_numbers`
- `valuation_vs_peers`
- `price_not_overheated`
- `narrative_early_stage`
- `risk_penalty`

### Evidence Input Columns

Required:

- `asset_id`
- `evidence_tier`
- `source_type`
- `source_url_or_path`
- `source_date`
- `claim`
- `supports`

Optional:

- `contradicts`
- `confidence`
- `freshness`

### Output Artifacts

For a run with `--run-id tech-bottleneck-2026-06-05`:

- `outputs/tech_bottleneck_discovery/tech-bottleneck-2026-06-05/packets.json`
- `outputs/tech_bottleneck_discovery/tech-bottleneck-2026-06-05/packets.csv`
- `outputs/tech_bottleneck_discovery/tech-bottleneck-2026-06-05/<asset_id>.md`
- `outputs/tech_bottleneck_discovery/tech-bottleneck-2026-06-05/summary.md`

## Task 1: Core Scoring And Candidate States

**Files:**
- Create: `src/stock_research/tech_bottleneck_discovery.py`
- Test: `tests/test_tech_bottleneck_discovery.py`

- [ ] **Step 1: Write failing tests for deterministic score construction**

Add this to `tests/test_tech_bottleneck_discovery.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_discovery import (
    build_tech_bottleneck_packets,
    render_tech_bottleneck_markdown,
    write_tech_bottleneck_artifacts,
)


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例光电",
                "trade_date": "2026-06-05",
                "terminal_demand": "AI 数据中心光互连",
                "supply_chain_node": "高速光模块上游关键材料",
                "company_exposure": "公司提供关键衬底材料，客户验证周期长。",
                "terminal_demand_certainty": 5,
                "single_point_importance": 5,
                "supply_concentration": 4,
                "capacity_expansion_difficulty": 4,
                "technical_barrier": 5,
                "qualification_or_customer_switching_cost": 4,
                "substitution_difficulty": 4,
                "value_capture_power": 3,
                "market_cap_room": 4,
                "low_sell_side_coverage": 5,
                "low_institutional_attention": 4,
                "old_business_mispricing": 4,
                "new_business_not_in_numbers": 5,
                "valuation_vs_peers": 3,
                "price_not_overheated": 4,
                "narrative_early_stage": 5,
                "risk_penalty": 1,
            },
            {
                "asset_id": "CN:SZ:300001",
                "stock_name": "普通科技",
                "trade_date": "2026-06-05",
                "terminal_demand": "泛 AI 概念",
                "supply_chain_node": "下游应用软件",
                "company_exposure": "概念相关，未披露直接收入。",
                "terminal_demand_certainty": 2,
                "single_point_importance": 1,
                "supply_concentration": 1,
                "capacity_expansion_difficulty": 1,
                "technical_barrier": 1,
                "qualification_or_customer_switching_cost": 1,
                "substitution_difficulty": 1,
                "value_capture_power": 1,
                "market_cap_room": 2,
                "low_sell_side_coverage": 2,
                "low_institutional_attention": 2,
                "old_business_mispricing": 1,
                "new_business_not_in_numbers": 1,
                "valuation_vs_peers": 1,
                "price_not_overheated": 1,
                "narrative_early_stage": 1,
                "risk_penalty": 4,
            },
        ]
    )


def _evidence_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "evidence_tier": "tier1",
                "source_type": "annual_report",
                "source_url_or_path": "reports/example-annual-report.pdf",
                "source_date": "2026-04-30",
                "claim": "公司披露关键材料客户验证和扩产计划。",
                "supports": "客户验证周期长，供给扩张受产能约束。",
                "contradicts": "",
                "confidence": "high",
                "freshness": "fresh",
            },
            {
                "asset_id": "CN:SH:688001",
                "evidence_tier": "tier1",
                "source_type": "announcement",
                "source_url_or_path": "announcements/example-capacity.pdf",
                "source_date": "2026-05-20",
                "claim": "公司公告新产能建设周期超过 18 个月。",
                "supports": "扩产慢，短期供给不易快速释放。",
                "contradicts": "",
                "confidence": "high",
                "freshness": "fresh",
            },
            {
                "asset_id": "CN:SZ:300001",
                "evidence_tier": "tier3",
                "source_type": "social_media",
                "source_url_or_path": "https://example.com/social",
                "source_date": "2026-06-01",
                "claim": "社媒称公司可能受益 AI。",
                "supports": "概念相关。",
                "contradicts": "",
                "confidence": "low",
                "freshness": "fresh",
            },
        ]
    )


def test_build_tech_bottleneck_packets_scores_and_states() -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )

    rows = packets.set_index("asset_id")
    strong = rows.loc["CN:SH:688001"]
    weak = rows.loc["CN:SZ:300001"]

    assert strong["chokepoint_score"] == 34.0
    assert strong["underpricing_score"] == 34.0
    assert strong["evidence_score"] == 5.0
    assert strong["candidate_state"] == "conviction_candidate"
    assert "市场可能仍按旧业务或普通供应商定价" in strong["market_misconception"]
    assert len(strong["evidence_items"]) == 2

    assert weak["chokepoint_score"] == 9.0
    assert weak["underpricing_score"] == 11.0
    assert weak["evidence_score"] == 1.0
    assert weak["candidate_state"] == "reject"
    assert len(weak["evidence_items"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_build_tech_bottleneck_packets_scores_and_states -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.tech_bottleneck_discovery'`.

- [ ] **Step 3: Create scoring module**

Create `src/stock_research/tech_bottleneck_discovery.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


CHOKEPOINT_DIMENSIONS = [
    "terminal_demand_certainty",
    "single_point_importance",
    "supply_concentration",
    "capacity_expansion_difficulty",
    "technical_barrier",
    "qualification_or_customer_switching_cost",
    "substitution_difficulty",
    "value_capture_power",
]

UNDERPRICING_DIMENSIONS = [
    "market_cap_room",
    "low_sell_side_coverage",
    "low_institutional_attention",
    "old_business_mispricing",
    "new_business_not_in_numbers",
    "valuation_vs_peers",
    "price_not_overheated",
    "narrative_early_stage",
]

PACKET_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "trade_date",
    "terminal_demand",
    "supply_chain_node",
    "company_exposure",
    "chokepoint_score",
    "underpricing_score",
    "evidence_score",
    "trend_score",
    "catalyst_score",
    "risk_penalty",
    "tech_bottleneck_score",
    "candidate_state",
    "one_sentence_thesis",
    "market_misconception",
    "evidence_items",
    "review_decision",
    "review_reason",
]


def build_tech_bottleneck_packets(
    *,
    candidates: pd.DataFrame,
    evidence: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=PACKET_COLUMNS)

    evidence_lookup = _evidence_lookup(evidence)
    rows: list[dict[str, Any]] = []
    for candidate in candidates.to_dict("records"):
        asset_id = _safe_text(candidate.get("asset_id"))
        evidence_items = evidence_lookup.get(asset_id, [])
        chokepoint_score = _sum_dimensions(candidate, CHOKEPOINT_DIMENSIONS)
        underpricing_score = _sum_dimensions(candidate, UNDERPRICING_DIMENSIONS)
        evidence_score = _evidence_score(evidence_items)
        trend_score = _score_from_total(chokepoint_score, 40.0)
        catalyst_score = _default_catalyst_score(evidence_items)
        risk_penalty = _bounded_float(candidate.get("risk_penalty"), default=0.0, lower=0.0, upper=5.0)
        tech_bottleneck_score = round(
            0.25 * trend_score
            + 0.25 * _score_from_total(chokepoint_score, 40.0)
            + 0.20 * evidence_score
            + 0.15 * _score_from_total(underpricing_score, 40.0)
            + 0.10 * catalyst_score
            - 0.15 * risk_penalty,
            4,
        )
        state = _candidate_state(
            chokepoint_score=chokepoint_score,
            evidence_items=evidence_items,
            tech_bottleneck_score=tech_bottleneck_score,
            risk_penalty=risk_penalty,
        )
        stock_name = _safe_text(candidate.get("stock_name"))
        terminal_demand = _safe_text(candidate.get("terminal_demand"))
        supply_chain_node = _safe_text(candidate.get("supply_chain_node"))
        exposure = _safe_text(candidate.get("company_exposure"))
        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "stock_name": stock_name,
                "trade_date": _safe_text(candidate.get("trade_date")),
                "terminal_demand": terminal_demand,
                "supply_chain_node": supply_chain_node,
                "company_exposure": exposure,
                "chokepoint_score": chokepoint_score,
                "underpricing_score": underpricing_score,
                "evidence_score": evidence_score,
                "trend_score": trend_score,
                "catalyst_score": catalyst_score,
                "risk_penalty": risk_penalty,
                "tech_bottleneck_score": tech_bottleneck_score,
                "candidate_state": state,
                "one_sentence_thesis": (
                    f"{stock_name} 可能处在 {terminal_demand} 的 {supply_chain_node} 咽喉点；"
                    f"{exposure}"
                ),
                "market_misconception": (
                    f"市场可能仍按旧业务或普通供应商定价，但证据显示公司可能暴露于 {supply_chain_node}。"
                ),
                "evidence_items": evidence_items,
                "review_decision": "pending_review",
                "review_reason": "",
            }
        )
    return pd.DataFrame(rows, columns=PACKET_COLUMNS).sort_values(
        ["candidate_state", "tech_bottleneck_score", "asset_id"],
        ascending=[True, False, True],
        kind="mergesort",
    )


def render_tech_bottleneck_markdown(packet: dict[str, Any]) -> str:
    evidence_lines = []
    for item in packet.get("evidence_items", []):
        evidence_lines.append(
            f"- [{item.get('evidence_tier')}] {item.get('claim')} "
            f"({item.get('source_type')}, {item.get('source_date')})"
        )
    if not evidence_lines:
        evidence_lines = ["- No evidence items supplied."]
    return "\n".join(
        [
            f"# {packet.get('stock_name')} tech-bottleneck-discovery Packet",
            "",
            f"- Asset: `{packet.get('asset_id')}`",
            f"- Trade date: `{packet.get('trade_date')}`",
            f"- State: `{packet.get('candidate_state')}`",
            f"- Score: `{packet.get('tech_bottleneck_score')}`",
            "",
            "## Thesis",
            "",
            str(packet.get("one_sentence_thesis", "")),
            "",
            "## Market Misconception",
            "",
            str(packet.get("market_misconception", "")),
            "",
            "## Evidence",
            "",
            *evidence_lines,
            "",
            "## Review",
            "",
            f"- Decision: `{packet.get('review_decision', 'pending_review')}`",
            f"- Reason: {packet.get('review_reason', '')}",
            "",
        ]
    )


def write_tech_bottleneck_artifacts(
    *,
    packets: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "packets.json"
    csv_path = output_dir / "packets.csv"
    summary_path = output_dir / "summary.md"
    records = packets.to_dict("records")
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    packets_for_csv = packets.copy()
    if "evidence_items" in packets_for_csv.columns:
        packets_for_csv["evidence_items"] = packets_for_csv["evidence_items"].map(
            lambda value: json.dumps(value, ensure_ascii=False)
        )
    packets_for_csv.to_csv(csv_path, index=False)
    summary_lines = ["# tech-bottleneck-discovery Summary", ""]
    for packet in records:
        asset_id = str(packet.get("asset_id", "")).replace(":", "_")
        markdown_path = output_dir / f"{asset_id}.md"
        markdown_path.write_text(render_tech_bottleneck_markdown(packet), encoding="utf-8")
        summary_lines.append(
            f"- `{packet.get('asset_id')}` {packet.get('stock_name')} "
            f"{packet.get('candidate_state')} score={packet.get('tech_bottleneck_score')}"
        )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "summary": summary_path}


def _evidence_lookup(evidence: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if evidence.empty:
        return {}
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in evidence.to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if not asset_id:
            continue
        lookup.setdefault(asset_id, []).append(
            {
                "evidence_tier": _normalize_tier(row.get("evidence_tier")),
                "source_type": _safe_text(row.get("source_type")),
                "source_url_or_path": _safe_text(row.get("source_url_or_path")),
                "source_date": _safe_text(row.get("source_date")),
                "claim": _safe_text(row.get("claim")),
                "supports": _safe_text(row.get("supports")),
                "contradicts": _safe_text(row.get("contradicts")),
                "confidence": _safe_text(row.get("confidence")) or "medium",
                "freshness": _safe_text(row.get("freshness")) or "unknown",
            }
        )
    return lookup


def _candidate_state(
    *,
    chokepoint_score: float,
    evidence_items: list[dict[str, Any]],
    tech_bottleneck_score: float,
    risk_penalty: float,
) -> str:
    tier1_count = sum(1 for item in evidence_items if item.get("evidence_tier") == "tier1")
    tier2_or_better = sum(
        1 for item in evidence_items if item.get("evidence_tier") in {"tier1", "tier2"}
    )
    if risk_penalty >= 4.5 or chokepoint_score < 16 or tier2_or_better == 0:
        return "reject"
    if tier1_count >= 2 and chokepoint_score >= 33 and tech_bottleneck_score >= 3.0:
        return "conviction_candidate"
    if tier1_count >= 2 and chokepoint_score >= 26:
        return "probe"
    if tier1_count >= 1 or tier2_or_better >= 2:
        return "research"
    return "watch"


def _evidence_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    score = 0.0
    for item in items:
        tier = item.get("evidence_tier")
        if tier == "tier1":
            score += 2.5
        elif tier == "tier2":
            score += 1.5
        else:
            score += 0.5
    return min(round(score, 2), 5.0)


def _default_catalyst_score(items: list[dict[str, Any]]) -> float:
    if any(item.get("source_type") in {"announcement", "earnings_call"} for item in items):
        return 4.0
    if any(item.get("evidence_tier") == "tier1" for item in items):
        return 3.0
    return 1.0 if items else 0.0


def _sum_dimensions(row: dict[str, Any], dimensions: list[str]) -> float:
    return round(sum(_bounded_float(row.get(column), default=0.0, lower=0.0, upper=5.0) for column in dimensions), 2)


def _score_from_total(total: float, max_total: float) -> float:
    if max_total <= 0:
        return 0.0
    return round(max(0.0, min(5.0, total / max_total * 5.0)), 4)


def _bounded_float(value: Any, *, default: float, lower: float, upper: float) -> float:
    try:
        if pd.isna(value):
            return default
        number = float(value)
    except Exception:
        return default
    return max(lower, min(upper, number))


def _normalize_tier(value: Any) -> str:
    normalized = _safe_text(value).lower().replace(" ", "")
    if normalized in {"1", "tier1", "t1"}:
        return "tier1"
    if normalized in {"2", "tier2", "t2"}:
        return "tier2"
    return "tier3"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
```

- [ ] **Step 4: Run scoring test**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_build_tech_bottleneck_packets_scores_and_states -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_discovery.py tests/test_tech_bottleneck_discovery.py
git commit -m "feat: add tech bottleneck discovery scoring"
```

## Task 2: Markdown And Artifact Outputs

**Files:**
- Modify: `tests/test_tech_bottleneck_discovery.py`
- Modify: `src/stock_research/tech_bottleneck_discovery.py`

- [ ] **Step 1: Write failing artifact tests**

Append to `tests/test_tech_bottleneck_discovery.py`:

```python
def test_render_tech_bottleneck_markdown_includes_review_and_evidence() -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )
    packet = packets.set_index("asset_id").loc["CN:SH:688001"].to_dict()

    markdown = render_tech_bottleneck_markdown(packet)

    assert "# 示例光电 tech-bottleneck-discovery Packet" in markdown
    assert "State: `conviction_candidate`" in markdown
    assert "## Evidence" in markdown
    assert "[tier1] 公司披露关键材料客户验证和扩产计划。" in markdown
    assert "Decision: `pending_review`" in markdown


def test_write_tech_bottleneck_artifacts_writes_json_csv_markdown(tmp_path: Path) -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )

    paths = write_tech_bottleneck_artifacts(packets=packets, output_dir=tmp_path)

    assert paths["json"].exists()
    assert paths["csv"].exists()
    assert paths["summary"].exists()
    assert (tmp_path / "CN_SH_688001.md").exists()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload[0]["run_id"] == "tech-bottleneck-2026-06-05"
    assert "tech-bottleneck-discovery Summary" in paths["summary"].read_text(encoding="utf-8")
```

- [ ] **Step 2: Run artifact tests**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_render_tech_bottleneck_markdown_includes_review_and_evidence tests/test_tech_bottleneck_discovery.py::test_write_tech_bottleneck_artifacts_writes_json_csv_markdown -q
```

Expected: PASS if Task 1 implementation included rendering and writing. If it fails, adjust only `render_tech_bottleneck_markdown` and `write_tech_bottleneck_artifacts` to match expected filenames and text.

- [ ] **Step 3: Run full module test**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/tech_bottleneck_discovery.py tests/test_tech_bottleneck_discovery.py
git commit -m "feat: write tech bottleneck research packets"
```

## Task 3: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_tech_bottleneck_discovery.py`

- [ ] **Step 1: Write failing CLI-runner test**

Append to `tests/test_tech_bottleneck_discovery.py`:

```python
from stock_research.tech_bottleneck_discovery import run_tech_bottleneck_discovery_from_files


def test_run_tech_bottleneck_discovery_from_files(tmp_path: Path) -> None:
    candidates_path = tmp_path / "candidates.csv"
    evidence_path = tmp_path / "evidence.csv"
    output_dir = tmp_path / "out"
    _candidate_frame().to_csv(candidates_path, index=False)
    _evidence_frame().to_csv(evidence_path, index=False)

    paths = run_tech_bottleneck_discovery_from_files(
        candidates_path=candidates_path,
        evidence_path=evidence_path,
        output_dir=output_dir,
        run_id="tech-bottleneck-2026-06-05",
    )

    assert paths["json"] == output_dir / "packets.json"
    assert paths["json"].exists()
    assert (output_dir / "CN_SH_688001.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_run_tech_bottleneck_discovery_from_files -q
```

Expected: FAIL with `ImportError` for `run_tech_bottleneck_discovery_from_files`.

- [ ] **Step 3: Add file runner**

Append to `src/stock_research/tech_bottleneck_discovery.py`:

```python
def run_tech_bottleneck_discovery_from_files(
    *,
    candidates_path: Path,
    evidence_path: Path,
    output_dir: Path,
    run_id: str,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_path)
    evidence = pd.read_csv(evidence_path)
    packets = build_tech_bottleneck_packets(
        candidates=candidates,
        evidence=evidence,
        run_id=run_id,
    )
    return write_tech_bottleneck_artifacts(packets=packets, output_dir=output_dir)
```

- [ ] **Step 4: Add CLI import and parser branch**

Modify `src/stock_research/cli.py`.

Add this import near the other feature imports:

```python
from stock_research.tech_bottleneck_discovery import run_tech_bottleneck_discovery_from_files
```

Add this parser setup inside `build_parser()` after the existing `report_delivery_openclaw_send` parser block and before `backtest_top20`:

```python
    tech_bottleneck_parser = subparsers.add_parser(
        "tech-bottleneck-discovery",
        help="Generate automated tech bottleneck discovery research packets.",
    )
    tech_bottleneck_parser.add_argument("--candidates-csv", required=True)
    tech_bottleneck_parser.add_argument("--evidence-csv", required=True)
    tech_bottleneck_parser.add_argument("--output-dir", required=True)
    tech_bottleneck_parser.add_argument("--run-id", required=True)
```

Add this dispatch branch inside `main_for_args()` after the existing `report-delivery-openclaw-send` branch and before `backtest-top20`:

```python
    elif args.command == "tech-bottleneck-discovery":
        paths = run_tech_bottleneck_discovery_from_files(
            candidates_path=Path(args.candidates_csv),
            evidence_path=Path(args.evidence_csv),
            output_dir=Path(args.output_dir),
            run_id=str(args.run_id),
        )
        print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 5: Run file-runner test**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_run_tech_bottleneck_discovery_from_files -q
```

Expected: PASS.

- [ ] **Step 6: Run CLI smoke with test fixtures**

Create temporary fixture files using the test helper is not available from shell, so use existing test through pytest as the CLI-facing smoke:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/tech_bottleneck_discovery.py src/stock_research/cli.py tests/test_tech_bottleneck_discovery.py
git commit -m "feat: add tech bottleneck discovery cli"
```

## Task 4: Review Decisions And Outcome-Ready Fields

**Files:**
- Modify: `src/stock_research/tech_bottleneck_discovery.py`
- Modify: `tests/test_tech_bottleneck_discovery.py`

- [ ] **Step 1: Write failing tests for review decisions**

Append to `tests/test_tech_bottleneck_discovery.py`:

```python
from stock_research.tech_bottleneck_discovery import apply_review_decisions


def test_apply_review_decisions_updates_decision_without_regenerating_packet() -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )
    decisions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "review_decision": "approve",
                "review_reason": "证据链完整，进入 shadow 跟踪。",
            },
            {
                "asset_id": "CN:SZ:300001",
                "review_decision": "reject",
                "review_reason": "只有弱证据，且不是上游咽喉点。",
            },
        ]
    )

    reviewed = apply_review_decisions(packets=packets, decisions=decisions)
    rows = reviewed.set_index("asset_id")

    assert rows.loc["CN:SH:688001", "review_decision"] == "approve"
    assert rows.loc["CN:SH:688001", "review_reason"] == "证据链完整，进入 shadow 跟踪。"
    assert rows.loc["CN:SZ:300001", "review_decision"] == "reject"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_apply_review_decisions_updates_decision_without_regenerating_packet -q
```

Expected: FAIL with `ImportError` for `apply_review_decisions`.

- [ ] **Step 3: Implement review decision merge**

Append to `src/stock_research/tech_bottleneck_discovery.py`:

```python
def apply_review_decisions(*, packets: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    if packets.empty or decisions.empty:
        return packets.copy()
    normalized = decisions.copy()
    for column in ["asset_id", "review_decision", "review_reason"]:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized = normalized.drop_duplicates(subset=["asset_id"], keep="last")
    decision_map = normalized.set_index("asset_id")[["review_decision", "review_reason"]].to_dict("index")
    reviewed = packets.copy()
    for index, row in reviewed.iterrows():
        asset_id = _safe_text(row.get("asset_id"))
        decision = decision_map.get(asset_id)
        if decision is None:
            continue
        reviewed.at[index, "review_decision"] = _safe_text(decision.get("review_decision")) or "pending_review"
        reviewed.at[index, "review_reason"] = _safe_text(decision.get("review_reason"))
    return reviewed
```

- [ ] **Step 4: Run review decision test**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py::test_apply_review_decisions_updates_decision_without_regenerating_packet -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_discovery.py tests/test_tech_bottleneck_discovery.py
git commit -m "feat: record tech bottleneck review decisions"
```

## Task 5: Documentation And Example Inputs

**Files:**
- Create: `docs/tech-bottleneck-discovery-runbook.md`
- Create: `data/manual/tech_bottleneck_candidates_example.csv`
- Create: `data/manual/tech_bottleneck_evidence_example.csv`

- [ ] **Step 1: Add example candidate CSV**

Create `data/manual/tech_bottleneck_candidates_example.csv`:

```csv
asset_id,stock_name,trade_date,terminal_demand,supply_chain_node,company_exposure,terminal_demand_certainty,single_point_importance,supply_concentration,capacity_expansion_difficulty,technical_barrier,qualification_or_customer_switching_cost,substitution_difficulty,value_capture_power,market_cap_room,low_sell_side_coverage,low_institutional_attention,old_business_mispricing,new_business_not_in_numbers,valuation_vs_peers,price_not_overheated,narrative_early_stage,risk_penalty
CN:SH:688001,示例光电,2026-06-05,AI 数据中心光互连,高速光模块上游关键材料,公司提供关键衬底材料，客户验证周期长。,5,5,4,4,5,4,4,3,4,5,4,4,5,3,4,5,1
```

- [ ] **Step 2: Add example evidence CSV**

Create `data/manual/tech_bottleneck_evidence_example.csv`:

```csv
asset_id,evidence_tier,source_type,source_url_or_path,source_date,claim,supports,contradicts,confidence,freshness
CN:SH:688001,tier1,annual_report,reports/example-annual-report.pdf,2026-04-30,公司披露关键材料客户验证和扩产计划。,客户验证周期长，供给扩张受产能约束。,,high,fresh
CN:SH:688001,tier1,announcement,announcements/example-capacity.pdf,2026-05-20,公司公告新产能建设周期超过 18 个月。,扩产慢，短期供给不易快速释放。,,high,fresh
```

- [ ] **Step 3: Add runbook**

Create `docs/tech-bottleneck-discovery-runbook.md`:

````markdown
# tech-bottleneck-discovery Runbook

`tech-bottleneck-discovery` is an automated research lens for hard-technology chokepoint candidates. The system generates research packets; humans review the generated evidence and record approve, reject, or needs-more-evidence.

## Inputs

- Candidate CSV: one row per existing candidate with trend, chokepoint, underpricing, and risk score dimensions.
- Evidence CSV: one row per cited evidence item with tier, source, date, claim, and support text.

## Command

```bash
stock-research tech-bottleneck-discovery \
  --candidates-csv data/manual/tech_bottleneck_candidates_example.csv \
  --evidence-csv data/manual/tech_bottleneck_evidence_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/example \
  --run-id tech-bottleneck-example
```

## Outputs

- `packets.json`: structured packet list.
- `packets.csv`: spreadsheet-friendly packet summary.
- `<asset_id>.md`: one markdown research packet per candidate.
- `summary.md`: run summary for review.

## Review Boundary

The command does not produce trading instructions, broker actions, or production watchlist promotion. Reviewers inspect the generated packet and record the review decision separately.
````

- [ ] **Step 4: Run documentation smoke**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/tech-bottleneck-discovery-runbook.md data/manual/tech_bottleneck_candidates_example.csv data/manual/tech_bottleneck_evidence_example.csv
git commit -m "docs: add tech bottleneck discovery runbook"
```

## Task 6: Final Verification

**Files:**
- Verify all files from prior tasks.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_tech_bottleneck_discovery.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI help smoke**

Run:

```bash
.venv/bin/stock-research tech-bottleneck-discovery --help
```

Expected: command help prints options for `--candidates-csv`, `--evidence-csv`, `--output-dir`, and `--run-id`.

- [ ] **Step 3: Run example command**

Run:

```bash
.venv/bin/stock-research tech-bottleneck-discovery \
  --candidates-csv data/manual/tech_bottleneck_candidates_example.csv \
  --evidence-csv data/manual/tech_bottleneck_evidence_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/example \
  --run-id tech-bottleneck-example
```

Expected: JSON printed to stdout with `json`, `csv`, and `summary` paths; output files exist under `outputs/tech_bottleneck_discovery/example`.

- [ ] **Step 4: Inspect generated summary**

Run:

```bash
sed -n '1,120p' outputs/tech_bottleneck_discovery/example/summary.md
```

Expected: includes `tech-bottleneck-discovery Summary` and a row for `CN:SH:688001`.

- [ ] **Step 5: Commit final fixes if any**

If Step 1-4 required fixes:

```bash
git add src/stock_research/tech_bottleneck_discovery.py src/stock_research/cli.py tests/test_tech_bottleneck_discovery.py docs/tech-bottleneck-discovery-runbook.md data/manual/tech_bottleneck_candidates_example.csv data/manual/tech_bottleneck_evidence_example.csv
git commit -m "fix: complete tech bottleneck discovery verification"
```

If no fixes were required, do not create an empty commit.

## Self-Review Checklist

- Spec coverage: automated packet generation, human review boundary, scoring, evidence tiers, output artifacts, and outcome-ready review decisions are covered.
- No placeholders: every task gives exact files, commands, and expected outputs.
- Type consistency: `build_tech_bottleneck_packets`, `render_tech_bottleneck_markdown`, `write_tech_bottleneck_artifacts`, `run_tech_bottleneck_discovery_from_files`, and `apply_review_decisions` are introduced before use or in the same task where tested.
- Scope: v1 avoids database migration, dashboard UI, broker integration, and automatic production promotion.
