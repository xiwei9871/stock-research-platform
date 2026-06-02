from pathlib import Path

import pandas as pd
import pytest

from stock_research import trend_candidate_enrichment


def _candidate_rank() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "direction": "higher",
                "candidate_score": 0.6,
            },
            {
                "factor_name": "distance_ma20",
                "factor_group": "risk",
                "direction": "lower",
                "candidate_score": 0.4,
            },
            {
                "factor_name": "ma20_slope",
                "factor_group": "trend",
                "direction": "higher",
                "candidate_score": 0.0,
            },
        ]
    )


def _factor_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "ret_20", "factor_value": 0.20},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "ret_20", "factor_value": 0.10},
            {"trade_date": "2024-06-03", "asset_id": "C", "factor_name": "ret_20", "factor_value": -0.05},
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "distance_ma20", "factor_value": 0.01},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "distance_ma20", "factor_value": 0.04},
            {"trade_date": "2024-06-03", "asset_id": "C", "factor_name": "distance_ma20", "factor_value": 0.12},
            {"trade_date": "2024-10-08", "asset_id": "A", "factor_name": "ret_20", "factor_value": 0.18},
            {"trade_date": "2024-10-08", "asset_id": "B", "factor_name": "ret_20", "factor_value": 0.05},
            {"trade_date": "2024-10-08", "asset_id": "C", "factor_name": "ret_20", "factor_value": -0.03},
            {"trade_date": "2024-10-08", "asset_id": "A", "factor_name": "distance_ma20", "factor_value": 0.02},
            {"trade_date": "2024-10-08", "asset_id": "B", "factor_name": "distance_ma20", "factor_value": 0.05},
            {"trade_date": "2024-10-08", "asset_id": "C", "factor_name": "distance_ma20", "factor_value": 0.15},
        ]
    )


def _entry_success() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "entry_success_20d": True, "entry_success_20d_covered": True, "entry_success_40d": True, "entry_success_40d_covered": True, "entry_success_60d": False, "entry_success_60d_covered": True},
            {"trade_date": "2024-06-03", "asset_id": "B", "entry_success_20d": False, "entry_success_20d_covered": True, "entry_success_40d": False, "entry_success_40d_covered": True, "entry_success_60d": False, "entry_success_60d_covered": True},
            {"trade_date": "2024-06-03", "asset_id": "C", "entry_success_20d": False, "entry_success_20d_covered": True, "entry_success_40d": False, "entry_success_40d_covered": True, "entry_success_60d": False, "entry_success_60d_covered": True},
            {"trade_date": "2024-10-08", "asset_id": "A", "entry_success_20d": True, "entry_success_20d_covered": True, "entry_success_40d": True, "entry_success_40d_covered": True, "entry_success_60d": True, "entry_success_60d_covered": True},
            {"trade_date": "2024-10-08", "asset_id": "B", "entry_success_20d": False, "entry_success_20d_covered": True, "entry_success_40d": False, "entry_success_40d_covered": True, "entry_success_60d": False, "entry_success_60d_covered": True},
            {"trade_date": "2024-10-08", "asset_id": "C", "entry_success_20d": False, "entry_success_20d_covered": True, "entry_success_40d": False, "entry_success_40d_covered": True, "entry_success_60d": False, "entry_success_60d_covered": True},
        ]
    )


def _reverse_profile_factor_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.20},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.02},
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.01},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.09},
            {"trade_date": "2024-10-08", "asset_id": "A", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.18},
            {"trade_date": "2024-10-08", "asset_id": "B", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.01},
            {"trade_date": "2024-10-08", "asset_id": "A", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.02},
            {"trade_date": "2024-10-08", "asset_id": "B", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.10},
        ]
    )


def _reverse_profile_labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "entry_success_20d": True, "entry_success_20d_covered": True},
            {"trade_date": "2024-06-03", "asset_id": "B", "entry_success_20d": False, "entry_success_20d_covered": True},
            {"trade_date": "2024-10-08", "asset_id": "A", "entry_success_20d": True, "entry_success_20d_covered": True},
            {"trade_date": "2024-10-08", "asset_id": "B", "entry_success_20d": False, "entry_success_20d_covered": True},
        ]
    )


def _reverse_profile_rank() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "horizon": 20,
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "direction": "higher",
                "periods": 5,
                "mean_median_diff": 0.01,
                "median_abs_diff": 0.02,
                "sign_match_rate": 1.0,
                "candidate_score": 0.02,
                "success_median": 0.10,
                "failure_median": 0.09,
            },
            {
                "horizon": 40,
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "direction": "higher",
                "periods": 5,
                "mean_median_diff": 0.03,
                "median_abs_diff": 0.05,
                "sign_match_rate": 1.0,
                "candidate_score": 0.05,
                "success_median": 0.12,
                "failure_median": 0.09,
            },
            {
                "horizon": 40,
                "factor_name": "max_drawdown_20",
                "factor_group": "risk",
                "direction": "lower",
                "periods": 5,
                "mean_median_diff": -0.02,
                "median_abs_diff": 0.04,
                "sign_match_rate": 0.8,
                "candidate_score": 0.04,
                "success_median": -0.12,
                "failure_median": -0.10,
            },
            {
                "horizon": 40,
                "factor_name": "close_above_ma20",
                "factor_group": "trend",
                "direction": "higher",
                "periods": 5,
                "mean_median_diff": 0.0,
                "median_abs_diff": 0.0,
                "sign_match_rate": 0.2,
                "candidate_score": 0.0,
                "success_median": 0.0,
                "failure_median": 0.0,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "amount": 1000},
            {"trade_date": "2024-06-04", "asset_id": "A", "open": 11.6, "high": 11.6, "low": 11.6, "close": 11.6, "amount": 1000},
            {"trade_date": "2024-06-03", "asset_id": "B", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "amount": 1000},
            {"trade_date": "2024-06-04", "asset_id": "B", "open": 9.1, "high": 9.1, "low": 9.1, "close": 9.1, "amount": 1000},
            {"trade_date": "2024-10-08", "asset_id": "A", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "amount": 1000},
            {"trade_date": "2024-10-09", "asset_id": "A", "open": 11.6, "high": 11.6, "low": 11.6, "close": 11.6, "amount": 1000},
        ]
    )


def test_build_candidate_scores_uses_directional_weighted_ranks():
    scores = trend_candidate_enrichment.build_candidate_scores(
        _factor_rows(),
        _candidate_rank(),
    )

    day_scores = scores[scores["trade_date"] == "2024-06-03"].sort_values("candidate_score", ascending=False)
    assert list(day_scores["asset_id"]) == ["A", "B", "C"]
    assert day_scores.iloc[0]["factor_count"] == 2
    assert day_scores.iloc[0]["weight_sum"] == 1.0
    assert day_scores.iloc[0]["candidate_score"] > day_scores.iloc[-1]["candidate_score"]


def test_enrichment_reports_quantile_topn_and_period_lift():
    scores = trend_candidate_enrichment.build_candidate_scores(
        _factor_rows(),
        _candidate_rank(),
    )
    joined = trend_candidate_enrichment.join_entry_success(scores, _entry_success())

    quantile = trend_candidate_enrichment.build_enrichment_by_quantile(joined, quantiles=2)
    topn = trend_candidate_enrichment.build_enrichment_by_topn(joined, top_ns=(1, 2))
    period = trend_candidate_enrichment.build_enrichment_by_period(joined, quantiles=2, period="Q")

    top_quantile = quantile[quantile["quantile"] == "Q2"].iloc[0]
    assert top_quantile["entry_success_20d_rate"] == 1.0
    assert top_quantile["entry_success_20d_lift"] > 1.0

    top1 = topn[topn["top_n"] == 1].iloc[0]
    assert top1["rows"] == 2
    assert top1["entry_success_40d_rate"] == 1.0

    assert set(period["period"]) == {"2024Q2", "2024Q4"}
    assert (period["entry_success_20d_lift"] > 1.0).all()


def test_write_candidate_enrichment_outputs_creates_report(tmp_path: Path):
    scores = trend_candidate_enrichment.build_candidate_scores(_factor_rows(), _candidate_rank())
    joined = trend_candidate_enrichment.join_entry_success(scores, _entry_success())
    quantile = trend_candidate_enrichment.build_enrichment_by_quantile(joined, quantiles=2)
    topn = trend_candidate_enrichment.build_enrichment_by_topn(joined, top_ns=(1, 2))
    period = trend_candidate_enrichment.build_enrichment_by_period(joined, quantiles=2)

    paths = trend_candidate_enrichment.write_candidate_enrichment_outputs(
        output_dir=tmp_path,
        start_date="2024-05-27",
        end_date="2025-05-08",
        candidate_scores=scores,
        enrichment_by_quantile=quantile,
        enrichment_by_topn=topn,
        enrichment_by_period=period,
        diagnostics=["research only"],
    )

    assert Path(paths["candidate_scores"]).exists()
    assert Path(paths["enrichment_by_quantile"]).exists()
    assert Path(paths["enrichment_by_topn"]).exists()
    assert Path(paths["enrichment_by_period"]).exists()
    report = Path(paths["markdown_report"]).read_text(encoding="utf-8")
    assert "Candidate Enrichment Validation V1" in report
    assert "research only" in report


def test_run_candidate_enrichment_report_loads_inputs_and_writes_outputs(tmp_path: Path, monkeypatch):
    candidate_path = tmp_path / "candidate_rank.csv"
    entry_path = tmp_path / "entry_success_labels.csv"
    _candidate_rank().to_csv(candidate_path, index=False)
    _entry_success().to_csv(entry_path, index=False)
    calls = []

    def fake_load_candidate_factor_values_from_db(**kwargs):
        calls.append(kwargs)
        return _factor_rows()

    monkeypatch.setattr(
        trend_candidate_enrichment,
        "load_candidate_factor_values_from_db",
        fake_load_candidate_factor_values_from_db,
    )

    result = trend_candidate_enrichment.run_candidate_enrichment_report(
        start_date="2024-05-27",
        end_date="2025-05-08",
        candidate_rank_path=candidate_path,
        entry_success_labels_path=entry_path,
        reports_dir=tmp_path,
        quantiles=2,
        top_ns=(1, 2),
    )

    assert calls[0]["factor_names"] == ["ret_20", "distance_ma20"]
    assert Path(result["paths"]["candidate_scores"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    assert len(result["candidate_scores"]) == 6
    assert len(result["enrichment_by_topn"]) == 2


def test_build_candidate_entry_success_labels_uses_candidate_score_universe():
    scores = pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "candidate_score": 90.0},
            {"trade_date": "2024-06-03", "asset_id": "B", "candidate_score": 10.0},
        ]
    )

    labels = trend_candidate_enrichment.build_candidate_entry_success_labels(
        bars=_bars(),
        candidate_scores=scores,
    )

    assert len(labels) == 2
    assert labels.set_index("asset_id").loc["A", "entry_success_20d"] is True
    assert labels.set_index("asset_id").loc["B", "entry_success_20d"] is False


def test_run_full_universe_candidate_enrichment_report_writes_labels_and_enrichment(
    tmp_path: Path,
    monkeypatch,
):
    scores_path = tmp_path / "candidate_scores.csv"
    scores = trend_candidate_enrichment.build_candidate_scores(_factor_rows(), _candidate_rank())
    scores.to_csv(scores_path, index=False)
    calls = []

    def fake_load_trend_lifecycle_bars(**kwargs):
        calls.append(kwargs)
        return _bars()

    monkeypatch.setattr(
        trend_candidate_enrichment,
        "load_trend_lifecycle_bars",
        fake_load_trend_lifecycle_bars,
    )

    result = trend_candidate_enrichment.run_full_universe_candidate_enrichment_report(
        start_date="2024-05-27",
        end_date="2025-05-08",
        candidate_scores_path=scores_path,
        reports_dir=tmp_path,
        quantiles=2,
        top_ns=(1, 2),
    )

    assert calls[0]["adjust_type"] == "hfq"
    assert Path(result["paths"]["candidate_entry_success_labels"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    assert len(result["candidate_entry_success_labels"]) == 6
    assert len(result["enrichment_by_quantile"]) == 2


def test_build_entry_success_factor_profile_compares_success_to_failure_by_period():
    profile = trend_candidate_enrichment.build_entry_success_factor_profile(
        _reverse_profile_factor_rows(),
        _reverse_profile_labels(),
        horizon=20,
        period="Q",
    )

    ret_q2 = profile[
        (profile["period"] == "2024Q2") & (profile["factor_name"] == "ret_20")
    ].iloc[0]
    assert ret_q2["success_n"] == 1
    assert ret_q2["failure_n"] == 1
    assert ret_q2["success_median"] == 0.20
    assert ret_q2["failure_median"] == 0.02
    assert ret_q2["median_diff"] == pytest.approx(0.18)


def test_rank_entry_success_factors_detects_direction_and_stability():
    profile = trend_candidate_enrichment.build_entry_success_factor_profile(
        _reverse_profile_factor_rows(),
        _reverse_profile_labels(),
        horizon=20,
        period="Q",
    )

    ranked = trend_candidate_enrichment.rank_entry_success_factors(profile)

    ret_row = ranked[ranked["factor_name"] == "ret_20"].iloc[0]
    distance_row = ranked[ranked["factor_name"] == "distance_ma20"].iloc[0]
    assert ret_row["direction"] == "higher"
    assert ret_row["sign_match_rate"] == 1.0
    assert ret_row["candidate_score"] > 0
    assert distance_row["direction"] == "lower"
    assert distance_row["sign_match_rate"] == 1.0


def test_run_entry_success_reverse_profile_report_writes_profile_and_rank(tmp_path: Path, monkeypatch):
    labels_path = tmp_path / "candidate_entry_success_labels.csv"
    _reverse_profile_labels().to_csv(labels_path, index=False)
    profile = trend_candidate_enrichment.build_entry_success_factor_profile(
        _reverse_profile_factor_rows(),
        _reverse_profile_labels(),
        horizon=20,
        period="Q",
    )
    calls = []

    def fake_load_entry_success_factor_profile_from_db(**kwargs):
        calls.append(kwargs)
        return profile

    monkeypatch.setattr(
        trend_candidate_enrichment,
        "load_entry_success_factor_profile_from_db",
        fake_load_entry_success_factor_profile_from_db,
    )

    result = trend_candidate_enrichment.run_entry_success_reverse_profile_report(
        start_date="2024-05-27",
        end_date="2025-05-08",
        entry_success_labels_path=labels_path,
        factor_names=["ret_20", "distance_ma20"],
        horizons=(20,),
        reports_dir=tmp_path,
    )

    assert calls[0]["factor_names"] == ["ret_20", "distance_ma20"]
    assert Path(result["paths"]["entry_success_factor_profile"]).exists()
    assert Path(result["paths"]["entry_success_factor_rank"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "Entry Success Reverse Factor Profile V1" in report
    assert len(result["factor_rank"]) == 2


def test_build_entry_success_candidate_v2_rank_filters_to_stable_horizon_rows():
    candidate_rank = trend_candidate_enrichment.build_entry_success_candidate_v2_rank(
        _reverse_profile_rank(),
        horizon=40,
        min_sign_match_rate=0.6,
        min_candidate_score=0.01,
    )

    assert list(candidate_rank["factor_name"]) == ["ret_20", "max_drawdown_20"]
    assert set(candidate_rank["horizon"]) == {40}
    assert candidate_rank.iloc[0]["candidate_score"] > candidate_rank.iloc[1]["candidate_score"]
    assert candidate_rank["candidate_score"].sum() == pytest.approx(0.09)


def test_run_entry_success_candidate_v2_report_writes_outputs(tmp_path: Path, monkeypatch):
    factor_rank_path = tmp_path / "entry_success_factor_rank.csv"
    _reverse_profile_rank().to_csv(factor_rank_path, index=False)
    candidate_rank = trend_candidate_enrichment.build_entry_success_candidate_v2_rank(
        _reverse_profile_rank(),
        horizon=40,
        min_sign_match_rate=0.6,
        min_candidate_score=0.01,
    )
    calls = []

    def fake_load_candidate_factor_values_from_db(**kwargs):
        calls.append(kwargs)
        return _factor_rows()

    def fake_load_trend_lifecycle_bars(**kwargs):
        return _bars()

    monkeypatch.setattr(
        trend_candidate_enrichment,
        "load_candidate_factor_values_from_db",
        fake_load_candidate_factor_values_from_db,
    )
    monkeypatch.setattr(
        trend_candidate_enrichment,
        "load_trend_lifecycle_bars",
        fake_load_trend_lifecycle_bars,
    )

    result = trend_candidate_enrichment.run_entry_success_candidate_v2_report(
        start_date="2024-05-27",
        end_date="2025-05-08",
        factor_rank_path=factor_rank_path,
        horizon=40,
        min_sign_match_rate=0.6,
        min_candidate_score=0.01,
        reports_dir=tmp_path,
    )

    assert calls[0]["factor_names"] == candidate_rank["factor_name"].tolist()
    assert Path(result["paths"]["candidate_rank"]).exists()
    assert Path(result["paths"]["candidate_scores"]).exists()
    assert Path(result["paths"]["candidate_entry_success_labels"]).exists()
    assert "Entry Success Candidate V2" in Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert len(result["candidate_rank"]) == 2
    assert len(result["candidate_scores"]) == 6
