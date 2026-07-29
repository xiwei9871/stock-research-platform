from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig, OUTPUT_FILENAMES
from stock_research.consumer_oversold.evidence import EVIDENCE_COLUMNS, OUTPUT_COLUMNS
from stock_research.consumer_oversold.pipeline import (
    build_consumer_oversold_weekly_from_frames,
    run_consumer_oversold_weekly,
)


TRADE_DATE = "2026-07-29"


def _bars(asset_id: str, ending: float) -> pd.DataFrame:
    closes = np.linspace(100.0, ending, 252)
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "trade_date": pd.bdate_range(end=TRADE_DATE, periods=252),
            "close": closes,
        }
    )


def _finance(asset_id: str) -> list[dict[str, object]]:
    rows = []
    for index, period in enumerate(pd.date_range("2024-03-31", periods=5, freq="QE")):
        latest = index == 4
        rows.append(
            {
                "asset_id": asset_id,
                "report_period": period.date().isoformat(),
                "announcement_date": (period + pd.Timedelta(days=25)).date().isoformat(),
                "revenue_ttm": 100.0,
                "revenue_growth": -0.10 if latest else 0.10,
                "np_parent_ttm": 8.0,
                "profit_growth": -0.10 if latest else 0.10,
                "gross_margin": 0.30,
                "net_margin": 0.03 if latest else 0.10,
                "roe": 0.04 if latest else 0.12,
                "ocf_to_np": 1.0,
                "debt_ratio": 0.30 + 0.01 * index,
                "equity_parent": 50.0,
                "operating_cash_flow": 8.0 + index,
            }
        )
    return rows


def _evidence(asset_id: str, stock_code: str, bucket: str) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "stock_code": stock_code,
        "evidence_as_of_date": "2026-07-20",
        "repair_bucket": bucket,
        "repair_thesis": f"{asset_id} repair thesis",
        "leading_indicator": "monthly sell-through",
        "unrepaired_metrics": "margin",
        "expected_validation_date": "2026-09-30",
        "main_risks": "competition",
        "invalidation_conditions": "demand weakens",
        "source_title": "company filing",
        "source_url": "https://example.com/filing",
        "source_publish_date": "2026-07-18",
        "forecast_revision_state": "improving",
        "audit_review_status": "clear",
        "pledge_debt_review_status": "clear",
        "permanent_impairment_status": "clear",
        "catalyst_verifiability_score": 80.0,
        "expected_improvement_score": 85.0,
        "operator_notes": "",
    }


def _frames() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, ConsumerOversoldConfig]:
    ids = ["A", "B", "C", "D"]
    codes = ["000001", "000002", "000003", "000004"]
    assets = pd.DataFrame(
        {
            "asset_id": ids + ["AUTO"],
            "stock_code": codes + ["000005"],
            "name": ["Alpha", "Beta", "Gamma", "Delta", "Auto Parts"],
            "list_date": ["2020-01-01"] * 5,
        }
    )
    statuses = pd.DataFrame(
        {
            "asset_id": assets["asset_id"],
            "is_st": False,
            "is_delisting_risk": False,
            "is_suspended": False,
        }
    )
    liquidity = pd.DataFrame(
        {"asset_id": assets["asset_id"], "avg_turnover_amount": 100_000_000.0}
    )
    industries = pd.DataFrame(
        {
            "asset_id": assets["asset_id"],
            "industry_system": "sw",
            "industry_name": ["food"] * 4 + ["auto parts"],
        }
    )
    rules = pd.DataFrame(
        [
            [1, "sw", "^food$", "food", "include", "terminal_consumer"],
            [2, "sw", "autoparts", "", "exclude", "auto_parts_excluded"],
        ],
        columns=[
            "priority",
            "industry_system",
            "industry_name_pattern",
            "consumer_subindustry",
            "action",
            "reason",
        ],
    )
    overrides = pd.DataFrame(
        columns=[
            "stock_code",
            "action",
            "consumer_subindustry",
            "reason",
            "effective_from",
            "effective_to",
        ]
    )
    bars = pd.concat(
        [_bars(asset_id, ending) for asset_id, ending in zip(ids, [55, 60, 65, 70], strict=True)],
        ignore_index=True,
    )
    finance = pd.DataFrame([row for asset_id in ids for row in _finance(asset_id)])
    current = pd.DataFrame(
        {
            "asset_id": ids,
            "as_of_date": TRADE_DATE,
            "consumer_subindustry": "wrong_external_value",
            "current_market_cap": 100.0,
            "net_debt": 5.0,
            "pe_ttm": 10.0,
            "ps_ttm": 1.0,
            "ev_ebitda": 8.0,
            "revenue_ttm": 100.0,
            "np_parent_ttm": 8.0,
            "ebitda_ttm": 12.0,
        }
    )
    history_rows = []
    for asset_id in ids:
        for date in pd.date_range("2024-01-31", periods=30, freq="ME"):
            history_rows.append(
                {
                    "asset_id": asset_id,
                    "valuation_date": date,
                    "consumer_subindustry": "wrong_external_value",
                    "pe_ttm": 20.0,
                    "ps_ttm": 2.0,
                    "ev_ebitda": 10.0,
                }
            )
    frames = {
        "assets": assets,
        "statuses": statuses,
        "liquidity": liquidity,
        "industries": industries,
        "industry_rules": rules,
        "asset_overrides": overrides,
        "bars": bars,
        "finance": finance,
        "current_valuation": current,
        "valuation_history": pd.DataFrame(history_rows),
    }
    evidence = pd.DataFrame(
        [
            _evidence("A", "000001", "expected_repair"),
            _evidence("B", "000002", "early_validation"),
        ],
        columns=EVIDENCE_COLUMNS,
    )
    config = ConsumerOversoldConfig(
        trade_date=TRADE_DATE,
        min_6m_return=0.0,
        min_12m_drawdown=0.0,
        min_relative_return=1.0,
        min_oversold_score=0.0,
        min_base_upside=-1.0,
    )
    return frames, evidence, config


def test_builds_two_buckets_keeps_scores_and_universe_exclusions():
    frames, evidence, config = _frames()

    result = build_consumer_oversold_weekly_from_frames(
        frames=frames, evidence=evidence, config=config
    )

    assert result["expected"]["asset_id"].tolist() == ["A"]
    assert result["early"]["asset_id"].tolist() == ["B"]
    assert set(result["scores"]["asset_id"]) == {"A", "B", "C", "D"}
    missing = result["scores"].set_index("asset_id").loc["C"]
    assert not missing["evidence_complete"]
    assert missing["hard_risk_review_unknown"]
    assert missing["repair_bucket"] == ""
    assert pd.isna(missing["expected_improvement_score"])
    assert "repair thesis" not in str(missing.get("repair_thesis", "")).lower()
    auto = result["exclusions"].set_index("asset_id").loc["AUTO"]
    assert auto["exclusion_stage"] == "universe"
    assert auto["exclusion_reasons"] == "auto_parts_excluded"
    assert result["paths"] == {}
    assert result["coverage"]["funnel"] == {
        "raw_assets": 5,
        "consumer_universe": 4,
        "market_eligible": 4,
        "oversold_eligible": 4,
        "hard_risk_clear": 2,
        "evidence_complete": 2,
        "valuation_eligible": 2,
        "selected_expected": 1,
        "selected_early": 1,
    }
    values = list(result["coverage"]["funnel"].values())[:7]
    assert values == sorted(values, reverse=True)
    assert result["coverage"]["data_date_maxima"] == {
        "market": TRADE_DATE,
        "finance": "2025-04-25",
        "evidence": "2026-07-20",
        "valuation": "2026-06-30",
    }


def test_empty_evidence_has_zero_selected_but_quantitative_exclusions_and_no_mutation():
    frames, _, config = _frames()
    originals = {key: value.copy(deep=True) for key, value in frames.items()}
    empty = pd.DataFrame(columns=EVIDENCE_COLUMNS)

    result = build_consumer_oversold_weekly_from_frames(
        frames=frames, evidence=empty, config=config
    )

    assert result["expected"].empty and result["early"].empty
    assert len(result["scores"]) == 4
    assert set(result["exclusions"].query("exclusion_stage == 'gate'")["asset_id"]) == {
        "A",
        "B",
        "C",
        "D",
    }
    assert result["coverage"]["funnel"]["hard_risk_clear"] == 0
    assert result["coverage"]["funnel"]["evidence_complete"] == 0
    for key, original in originals.items():
        pd.testing.assert_frame_equal(frames[key], original)


def test_rejects_missing_keys_duplicate_merge_and_future_evidence():
    frames, evidence, config = _frames()
    with pytest.raises(ValueError, match="missing required frame keys.*bars"):
        build_consumer_oversold_weekly_from_frames(
            frames={key: value for key, value in frames.items() if key != "bars"},
            evidence=evidence,
            config=config,
        )

    duplicate = deepcopy(frames)
    duplicate["current_valuation"] = pd.concat(
        [duplicate["current_valuation"], duplicate["current_valuation"].iloc[[0]]]
    )
    with pytest.raises(ValueError, match="duplicate asset_id A"):
        build_consumer_oversold_weekly_from_frames(
            frames=duplicate, evidence=evidence, config=config
        )

    future = evidence.copy(deep=True)
    future.loc[0, "evidence_as_of_date"] = "2026-08-01"
    with pytest.raises(ValueError, match="future evidence_as_of_date"):
        build_consumer_oversold_weekly_from_frames(
            frames=frames, evidence=future, config=config
        )


def test_explicit_completed_repair_is_excluded():
    frames, evidence, config = _frames()
    evidence["repair_already_completed"] = [True, False]

    result = build_consumer_oversold_weekly_from_frames(
        frames=frames, evidence=evidence, config=config
    )

    row = result["scores"].set_index("asset_id").loc["A"]
    assert row["repair_already_completed"]
    assert "repair_already_completed" in row["exclusion_reasons"]


def test_output_dir_publishes_validated_evidence_and_seven_absolute_current_paths(tmp_path):
    frames, evidence, config = _frames()
    result = build_consumer_oversold_weekly_from_frames(
        frames=frames, evidence=evidence, config=config, output_dir=tmp_path
    )

    assert set(result["paths"]) == set(OUTPUT_FILENAMES)
    assert all(Path(path).is_absolute() and "/current/" in path for path in result["paths"].values())
    assert result["evidence"].columns.tolist() == OUTPUT_COLUMNS
    published_evidence = pd.read_csv(result["paths"]["evidence"])
    assert published_evidence.columns.tolist() == OUTPUT_COLUMNS
    assert published_evidence["asset_id"].tolist() == ["A", "B"]
    assert published_evidence["evidence_complete"].tolist() == [True, True]
    assert published_evidence["hard_risk_manual_trigger"].tolist() == [False, False]
    assert "消费超跌修复候选周报" in result["report"]


def test_runner_uses_latest_close_times_shares_not_pe_or_ps(monkeypatch, tmp_path):
    from stock_research.consumer_oversold import pipeline

    frames, evidence, _ = _frames()
    evidence_path = tmp_path / "evidence.csv"
    evidence.to_csv(evidence_path, index=False)
    rules_path = tmp_path / "rules.csv"
    frames["industry_rules"].to_csv(rules_path, index=False)
    overrides_path = tmp_path / "overrides.csv"
    frames["asset_overrides"].to_csv(overrides_path, index=False)
    monkeypatch.setattr(pipeline, "INDUSTRY_RULES_PATH", rules_path)
    monkeypatch.setattr(pipeline, "ASSET_OVERRIDES_PATH", overrides_path)
    monkeypatch.setattr(
        pipeline,
        "load_consumer_universe_frames",
        lambda trade_date, service: {key: frames[key] for key in ("assets", "statuses", "liquidity", "industries")},
    )
    market_calls = []
    market = frames["bars"].copy()
    market["raw_close"] = market["close"]
    market.loc[market["asset_id"].eq("A") & market["trade_date"].eq(market.loc[market["asset_id"].eq("A"), "trade_date"].max()), ["close", "raw_close"]] = [200.0, 20.0]
    monkeypatch.setattr(
        pipeline,
        "load_consumer_market_history",
        lambda trade_date, service, asset_ids=None: market_calls.append(asset_ids) or market,
    )
    finance = frames["finance"].copy()
    finance["total_share"] = finance["asset_id"].map({"A": 10, "B": 20, "C": np.nan, "D": 40})
    monkeypatch.setattr(pipeline, "load_consumer_finance_history", lambda ids, trade_date, service: finance)
    raw_valuation = frames["valuation_history"].drop(columns="consumer_subindustry").copy()
    raw_valuation.loc[raw_valuation["asset_id"].eq("B"), "pe_ttm"] = np.nan
    raw_valuation.loc[raw_valuation["asset_id"].eq("C"), ["pe_ttm", "ps_ttm"]] = np.nan
    monkeypatch.setattr(pipeline, "load_consumer_valuation_history", lambda ids, trade_date, service: raw_valuation)

    captured = {}

    def fake_build(*, frames, evidence, config, output_dir):
        captured.update(frames=frames, evidence=evidence, config=config, output_dir=output_dir)
        return {"ok": True}

    monkeypatch.setattr(pipeline, "build_consumer_oversold_weekly_from_frames", fake_build)

    result = run_consumer_oversold_weekly(
        trade_date=TRADE_DATE,
        evidence_path=evidence_path,
        output_dir=tmp_path / "out",
        service="test-service",
    )

    assert result == {"ok": True}
    assert market_calls == [["A", "B", "C", "D"]]
    assert "earnings" not in captured["frames"]
    current = captured["frames"]["current_valuation"].set_index("asset_id")
    assert current.loc["A", "current_market_cap"] == pytest.approx(20.0 * 10.0)
    assert current.loc["B", "current_market_cap"] == pytest.approx(60.0 * 20.0)
    assert pd.isna(current.loc["C", "current_market_cap"])
    assert current["net_debt"].isna().all()
    assert current["ebitda_ttm"].isna().all()
    assert captured["evidence"]["stock_code"].dtype.name == "string"


def test_empty_consumer_pool_allows_schema_less_downstream_frames():
    frames, evidence, config = _frames()
    frames["industry_rules"] = frames["industry_rules"].assign(action="exclude", consumer_subindustry="")
    for key in ("bars", "finance", "current_valuation", "valuation_history"):
        frames[key] = pd.DataFrame()

    result = build_consumer_oversold_weekly_from_frames(
        frames=frames, evidence=evidence.iloc[0:0], config=config
    )

    assert result["expected"].empty and result["early"].empty and result["scores"].empty
    assert set(result["exclusions"]["asset_id"]) == {"A", "B", "C", "D", "AUTO"}
    assert all(value == 0 for value in list(result["coverage"]["funnel"].values())[1:])


@pytest.mark.parametrize(
    ("frame_name", "missing_column"),
    [
        ("bars", "close"),
        ("finance", "revenue_ttm"),
        ("current_valuation", "current_market_cap"),
        ("valuation_history", "valuation_date"),
    ],
)
def test_nonempty_consumer_pool_validates_downstream_frame_schema(frame_name, missing_column):
    frames, evidence, config = _frames()
    frames[frame_name] = frames[frame_name].drop(columns=[missing_column])

    with pytest.raises(ValueError, match=rf"{frame_name}.*{missing_column}"):
        build_consumer_oversold_weekly_from_frames(
            frames=frames, evidence=evidence, config=config
        )


def test_runner_rejects_missing_evidence_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="evidence"):
        run_consumer_oversold_weekly(
            trade_date=TRADE_DATE,
            evidence_path=tmp_path / "missing.csv",
            output_dir=tmp_path / "out",
        )
