from pathlib import Path

import pandas as pd

from stock_research import trend_factor_profile


def _factors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.12},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.01},
            {"trade_date": "2024-06-03", "asset_id": "C", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.03},
            {"trade_date": "2024-06-03", "asset_id": "A", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.06},
            {"trade_date": "2024-06-03", "asset_id": "B", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.02},
            {"trade_date": "2024-06-03", "asset_id": "C", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.04},
            {"trade_date": "2024-10-01", "asset_id": "A", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.11},
            {"trade_date": "2024-10-01", "asset_id": "B", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.00},
            {"trade_date": "2024-10-01", "asset_id": "C", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.02},
            {"trade_date": "2024-10-01", "asset_id": "A", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.01},
            {"trade_date": "2024-10-01", "asset_id": "B", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.02},
            {"trade_date": "2024-10-01", "asset_id": "C", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.03},
            {"trade_date": "2024-10-01", "asset_id": "L", "factor_name": "ret_20", "factor_group": "momentum", "factor_value": 0.30},
            {"trade_date": "2024-10-01", "asset_id": "L", "factor_name": "distance_ma20", "factor_group": "risk", "factor_value": 0.25},
        ]
    )


def _lifecycle_samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-06-03", "asset_id": "A", "trend_label": "mid_trend", "stage": "early"},
            {"trade_date": "2024-10-01", "asset_id": "A", "trend_label": "mid_trend", "stage": "early_mid"},
            {"trade_date": "2024-10-01", "asset_id": "L", "trend_label": "mid_trend", "stage": "late"},
            {"trade_date": "2024-10-01", "asset_id": "X", "trend_label": "large_trend", "stage": "early"},
        ]
    )


def test_build_factor_stage_profile_compares_mid_trend_stage_to_control():
    profile = trend_factor_profile.build_factor_stage_profile(
        _factors(),
        _lifecycle_samples(),
    )

    row = profile[
        (profile["factor_name"] == "ret_20")
        & (profile["trend_label"] == "mid_trend")
        & (profile["stage"] == "early")
    ].iloc[0]
    assert row["factor_group"] == "momentum"
    assert row["n"] == 1
    assert row["median"] == 0.12
    assert row["control_median"] == 0.03
    assert row["median_minus_control"] == 0.09


def test_build_factor_stability_reports_period_sign_consistency():
    profile = trend_factor_profile.build_factor_stage_profile(
        _factors(),
        _lifecycle_samples(),
        period="Q",
    )
    stability = trend_factor_profile.build_factor_stability(profile)

    ret_row = stability[
        (stability["factor_name"] == "ret_20")
        & (stability["stage"] == "early_mid")
    ].iloc[0]
    assert ret_row["periods"] == 1
    assert ret_row["sign_match_rate"] == 1.0
    assert ret_row["stable"] is True


def test_rank_candidate_factors_prefers_stable_focus_stage_separation():
    profile = trend_factor_profile.build_factor_stage_profile(
        _factors(),
        _lifecycle_samples(),
        period="Q",
    )
    stability = trend_factor_profile.build_factor_stability(profile)

    ranked = trend_factor_profile.rank_candidate_factors(
        profile,
        stability,
        factor_directions={"ret_20": "higher", "distance_ma20": "lower"},
    )

    assert list(ranked["factor_name"])[:2] == ["ret_20", "distance_ma20"]
    assert ranked.iloc[0]["focus_stages"] == "early,early_mid"
    assert ranked.iloc[0]["candidate_score"] > ranked.iloc[1]["candidate_score"]
    assert ranked.iloc[0]["direction"] == "higher"


def test_build_stage_signatures_reports_stable_stage_characteristics():
    profile = trend_factor_profile.build_factor_stage_profile(
        _factors(),
        _lifecycle_samples(),
        period="Q",
    )
    stability = trend_factor_profile.build_factor_stability(profile)

    signatures = trend_factor_profile.build_stage_signatures(
        profile,
        stability,
        factor_directions={"ret_20": "higher", "distance_ma20": "lower"},
    )

    early = signatures[
        (signatures["stage"] == "early")
        & (signatures["factor_name"] == "ret_20")
    ].iloc[0]
    assert early["signature_type"] == "positive"
    assert early["oriented_mean_diff"] > 0
    assert early["sign_match_rate"] == 1.0
    assert early["stable"] is True


def test_write_factor_profile_outputs_required_files(tmp_path: Path):
    profile = trend_factor_profile.build_factor_stage_profile(_factors(), _lifecycle_samples())
    stability = trend_factor_profile.build_factor_stability(profile)
    ranked = trend_factor_profile.rank_candidate_factors(
        profile,
        stability,
        factor_directions={"ret_20": "higher", "distance_ma20": "lower"},
    )
    signatures = trend_factor_profile.build_stage_signatures(
        profile,
        stability,
        factor_directions={"ret_20": "higher", "distance_ma20": "lower"},
    )

    paths = trend_factor_profile.write_factor_profile_outputs(
        output_dir=tmp_path,
        start_date="2024-05-27",
        end_date="2025-05-08",
        profile=profile,
        stability=stability,
        candidate_rank=ranked,
        stage_signatures=signatures,
        diagnostics=["factor coverage ok"],
    )

    assert Path(paths["factor_profile"]).exists()
    assert Path(paths["stage_stability"]).exists()
    assert Path(paths["candidate_rank"]).exists()
    assert Path(paths["stage_signatures"]).exists()
    report = Path(paths["markdown_report"]).read_text(encoding="utf-8")
    assert "mid_trend early / early_mid factor candidates" in report
    assert "Lifecycle Stage Signatures" in report
    assert "factor coverage ok" in report
