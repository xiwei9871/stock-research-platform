from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.contracts import RollingOversoldConfig


ANCHOR = date(2026, 7, 31)
SECTOR_COUNT = 302


def _representative_inputs() -> SimpleNamespace:
    """Build a deterministic full-sector fixture without provider access."""

    sector_codes = [f"C{index:03d}" for index in range(SECTOR_COUNT)]
    sector_names = [f"Concept {index:03d}" for index in range(SECTOR_COUNT)]
    dates = [ANCHOR - timedelta(days=offset) for offset in range(19, -1, -1)]
    bars: list[dict[str, object]] = []
    for sector_index, (code, name) in enumerate(zip(sector_codes, sector_names, strict=True)):
        # Keep one membership-only sector to assert full coverage plus a
        # structured sector_features gap rather than silently dropping it.
        if sector_index == SECTOR_COUNT - 1:
            continue
        for offset, trade_date in enumerate(dates):
            close = 100.0 - (12.0 if offset == 11 else 0.0) + max(0, offset - 11) * 1.2
            bars.append(
                {
                    "concept_system": "ths",
                    "concept_code": code,
                    "concept_name": name,
                    "trade_date": trade_date,
                    "close": close,
                    "preclose": close - 0.5,
                    "volume": 100.0 + offset * 5.0,
                    "amount": 1000.0 + offset * 50.0,
                }
            )
    membership = pd.DataFrame(
        {
            "asset_id": [f"A{index:03d}" for index in range(SECTOR_COUNT)],
            "concept_system": ["ths"] * SECTOR_COUNT,
            "concept_code": sector_codes,
            "concept_name": sector_names,
            "start_date": [date(2020, 1, 1)] * SECTOR_COUNT,
            "end_date": [pd.NaT] * SECTOR_COUNT,
        }
    )
    empty = pd.DataFrame()
    return SimpleNamespace(
        anchor_date=ANCHOR,
        data_cutoff_date=ANCHOR,
        trading_dates=pd.DataFrame({"trade_date": dates}),
        index_bars=empty,
        stock_bars=empty,
        stock_status=empty,
        industry_membership=empty,
        concept_membership=membership,
        industry_bars=empty,
        concept_bars=pd.DataFrame(bars),
        finance=empty,
        valuation=empty,
        index_ids=("SSE_COMPOSITE",),
        score_version="rolling_oversold_v1",
    )


def _representative_stock_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": f"A{index:03d}",
                "sector_system": "ths",
                "sector_code": f"C{index:03d}",
                "sector_name": f"Concept {index:03d}",
                "anchor_return": 0.02,
                "distance_to_252d_high": 0.25,
                "oversold_depth": 0.25,
                "stock_excess_return": 0.01,
                "activity": 100.0,
                "quality": 70.0,
                "valuation": 60.0,
                "size_elasticity": 10.0,
                "anchor_close": 10.0,
                "adjusted_close_source": "qfq",
            }
            for index in range(SECTOR_COUNT - 1)
        ]
    )


def test_full_sector_batch_reports_runtime_under_budget(monkeypatch, tmp_path):
    inputs = _representative_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR, runtime_budget_seconds=3600)
    calls = {"load": 0, "regime": 0, "stock_features": 0}

    def fake_load(**kwargs):
        calls["load"] += 1
        return inputs

    def fake_regime(*args, **kwargs):
        calls["regime"] += 1
        return {"market_regime": "risk_off"}

    def fake_stock_features(*args, **kwargs):
        calls["stock_features"] += 1
        return _representative_stock_features()

    monkeypatch.setattr(pipeline, "load_rolling_inputs", fake_load)
    monkeypatch.setattr(pipeline, "compute_market_regime_features", fake_regime)
    monkeypatch.setattr(pipeline, "_build_stock_features", fake_stock_features)

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert result["runtime_seconds"] <= 3600
    timings = result["runtime_metadata"]["stage_timings_seconds"]
    assert {"load", "regime", "sector", "stock", "publication"}.issubset(timings)
    assert all(float(value) >= 0.0 for value in timings.values())

    # A full-sector anchor must load and derive each shared dataset once; the
    # scorer then reuses those in-memory frames for all 302 sector rows.
    assert calls == {"load": 1, "regime": 1, "stock_features": 1}
    assert result["sector_count"] == SECTOR_COUNT
    assert len(result["sector_states"]) == SECTOR_COUNT

    board = result["sector_states"]
    blocked = board.loc[board["sector_code"].eq("C301")].iloc[0]
    assert blocked["sector_research_eligibility"] == "blocked_data"
    assert not result["stock_candidates"]["sector_code"].eq("C301").any()

    # Missing bars stay auditable as a structured gap rather than reducing the
    # published universe or silently triggering a provider fallback.
    gaps = result["snapshot"]["preflight"]["gaps"]
    assert any(
        gap["dataset"] == "sector_features"
        and gap["asset_id"] == "ths:C301"
        and gap["expected_rows"] == 1
        and gap["actual_rows"] == 0
        for gap in gaps
    )
