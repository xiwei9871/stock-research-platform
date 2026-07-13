from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_announcement_source_ingestion.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_announcement_source_ingestion", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_source_inventory_detects_announcement_disclosure_cninfo() -> None:
    module = _load_module()
    inventory = module.build_announcement_source_inventory(project_root=Path("/tmp/nonexistent"), source_paths=[Path("cninfo_announcement.csv")])

    text = " ".join(inventory["source_name"].astype(str).tolist()).lower()

    assert "announcement" in text or "disclosure" in text or "cninfo" in text


def test_structured_output_has_required_fields_and_pit_dates() -> None:
    module = _load_module()
    watchlist = pd.DataFrame(
        {
            "asset_id": ["CN:SZ:000001"],
            "symbol": ["000001"],
            "name": ["样本"],
            "first_admission_date": ["2026-01-10"],
        }
    )
    raw = pd.DataFrame(
        {
            "source_event_id": ["ann-1"],
            "asset_id": ["CN:SZ:000001"],
            "ts_code": ["000001.SZ"],
            "stock_name": ["样本"],
            "title": ["样本重大合同公告"],
            "content": [""],
            "published_at": ["2026-01-09"],
            "url": ["https://example.com/ann-1"],
            "source_name": ["cninfo_disclosure_announcement"],
            "event_family": ["disclosure_notice"],
        }
    )

    matches = module.match_raw_announcements_to_watchlist(raw, watchlist)
    structured = module.build_structured_announcements(matches, watchlist)

    required = {
        "trade_date",
        "asset_id",
        "announcement_id",
        "source_type",
        "announcement_date",
        "as_of_date",
        "order_contract",
        "risk_disclosure",
        "performance_forecast",
        "lookahead_violation",
    }
    assert required.issubset(structured.columns)
    assert not structured["lookahead_violation"].astype(bool).any()
    assert pd.to_datetime(structured["announcement_date"]).le(pd.to_datetime(structured["trade_date"])).all()
    assert pd.to_datetime(structured["as_of_date"]).le(pd.to_datetime(structured["trade_date"])).all()


def test_keyword_classification_covers_core_types() -> None:
    module = _load_module()

    contract = module.classify_announcement("关于签订重大合同的公告", "")
    risk = module.classify_announcement("关于诉讼及风险提示公告", "")
    forecast = module.classify_announcement("2025年度业绩预告", "")

    assert contract["order_contract"] is True
    assert risk["risk_disclosure"] is True
    assert forecast["performance_forecast"] is True


def test_watchlist_patch_uses_review_only_actions() -> None:
    module = _load_module()
    watchlist = pd.DataFrame({"asset_id": ["A"], "symbol": ["A"], "name": ["甲"]})
    coverage = pd.DataFrame(
        {
            "asset_id": ["A"],
            "symbol": ["A"],
            "name": ["甲"],
            "announcement_count": [1],
            "has_order_contract": [True],
            "has_risk_disclosure": [False],
        }
    )

    patch = module.build_watchlist_announcement_gap_patch(watchlist, coverage)

    assert not patch.empty
    assert set(patch["recommended_report_update"]).issubset(module.ALLOWED_REVIEW_ACTIONS)
    assert not module.contains_actionable_trading_language(" ".join(patch.astype(str).agg(" ".join, axis=1).tolist()))


def test_empty_source_still_outputs_degraded_tables() -> None:
    module = _load_module()
    watchlist = pd.DataFrame({"asset_id": ["A"], "symbol": ["A"], "name": ["甲"], "first_admission_date": ["2026-01-10"]})

    matches = module.match_raw_announcements_to_watchlist(pd.DataFrame(), watchlist)
    structured = module.build_structured_announcements(matches, watchlist)
    audit = module.build_quality_audit(pd.DataFrame(), matches, structured, watchlist)

    assert matches.empty
    assert structured.empty
    lookup = dict(zip(audit["metric"], audit["value"]))
    assert int(float(lookup["lookahead_violation_rows"])) == 0
