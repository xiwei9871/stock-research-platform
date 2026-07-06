from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_a_share_doubled_tech_stocks_since_20250101.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1"
SPECIAL_NAMES = {
    "胜宏科技",
    "中际旭创",
    "新易盛",
    "天孚通信",
    "寒武纪",
    "源杰科技",
    "联特科技",
    "生益电子",
    "生益科技",
    "沪电股份",
    "工业富联",
    "江波龙",
    "佰维存储",
    "德明利",
    "长川科技",
    "中科飞测",
    "精测电子",
    "北方华创",
    "中微公司",
    "华海清科",
    "安集科技",
}
REQUIRED_COLUMNS = {
    "stock_code",
    "stock_name",
    "exchange",
    "listing_date",
    "start_date_used",
    "start_close_qfq",
    "latest_date",
    "latest_close_qfq",
    "return_since_20250101",
    "max_return_since_20250101",
    "is_doubled",
    "is_ipo_after_20250101",
    "industry",
    "concept_tags",
    "tech_theme",
    "hard_tech_relevance",
    "include_decision",
    "exclusion_reason",
    "evidence_source",
    "source_url",
    "notes",
}


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_doubled_tech_stock_outputs_have_required_contract() -> None:
    _run_generator()
    expected_files = {
        "doubled_tech_stocks.csv",
        "doubled_tech_stocks_summary.json",
        "all_doubled_a_share_stocks.csv",
        "excluded_non_tech_doubled_stocks.csv",
        "ipo_after_20250101_doubled_stocks.csv",
        "price_return_audit.csv",
        "tech_classification_audit.csv",
        "source_evidence_matrix.csv",
        "a_share_doubled_tech_stocks_since_20250101_v1_report.md",
    }
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "doubled_tech_stocks_summary.json").read_text(encoding="utf-8"))
    price_audit = pd.read_csv(OUTPUT_DIR / "price_return_audit.csv", dtype={"stock_code": str})
    doubled_tech = pd.read_csv(OUTPUT_DIR / "doubled_tech_stocks.csv", dtype={"stock_code": str})
    all_doubled = pd.read_csv(OUTPUT_DIR / "all_doubled_a_share_stocks.csv", dtype={"stock_code": str})
    ipo = pd.read_csv(OUTPUT_DIR / "ipo_after_20250101_doubled_stocks.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "a_share_doubled_tech_stocks_since_20250101_v1"
    assert summary["research_only"] is True
    assert summary["price_source"] in {"local_db_market_daily_bar_qfq", "akshare_qfq"}
    assert summary["a_share_universe_count"] >= 5000
    assert summary["latest_trading_day"] >= "2026-07-01"
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert REQUIRED_COLUMNS.issubset(set(doubled_tech.columns))
    assert REQUIRED_COLUMNS.issubset(set(price_audit.columns))
    assert price_audit["stock_code"].nunique() >= 5000
    assert set(SPECIAL_NAMES).issubset(set(price_audit["stock_name"]))
    assert doubled_tech["return_since_20250101"].ge(1.0).all()
    assert doubled_tech["is_doubled"].eq(True).all()
    assert set(doubled_tech["include_decision"]).issubset({"included_hard_tech", "included_tech_candidate"})
    assert all_doubled["return_since_20250101"].ge(1.0).all()
    if not ipo.empty:
        assert ipo["is_ipo_after_20250101"].eq(True).all()
        assert ipo["listing_date"].gt("2025-01-01").all()


def test_doubled_tech_stock_audits_separate_non_tech_and_sources() -> None:
    _run_generator()
    excluded = pd.read_csv(OUTPUT_DIR / "excluded_non_tech_doubled_stocks.csv", dtype={"stock_code": str})
    classification = pd.read_csv(OUTPUT_DIR / "tech_classification_audit.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "source_evidence_matrix.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "a_share_doubled_tech_stocks_since_20250101_v1_report.md").read_text(encoding="utf-8")

    assert not classification.empty
    assert {"stock_code", "stock_name", "include_decision", "hard_tech_relevance", "evidence_source"}.issubset(classification.columns)
    assert {"stock_code", "stock_name", "evidence_source", "source_url", "evidence_note"}.issubset(evidence.columns)
    assert set(SPECIAL_NAMES).issubset(set(evidence["stock_name"]))
    assert "confirmed doubled hard-tech stocks" in report
    assert "doubled but non-tech stocks" in report
    assert "tech stocks close to doubling" in report
    assert "IPO cohort" in report
    assert "买入" not in report
    assert "卖出" not in report
    assert "目标价" not in report
    if not excluded.empty:
        assert excluded["include_decision"].isin({"excluded_non_tech", "excluded_concept_only", "excluded_operator_financial"}).all()
