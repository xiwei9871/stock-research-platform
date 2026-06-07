import pandas as pd

from stock_research.market_style_switch_v1 import (
    build_anchor_diagnostics,
    build_defensive_yield_proxy_candidates,
    build_growth_momentum_candidates,
    build_rotation_balanced_candidates,
    build_style_state_daily,
    run_style_switch_backtest_from_frames,
    write_market_style_switch_outputs,
)


def test_build_style_state_daily_maps_emotion_and_risk_to_style() -> None:
    emotion = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "emotion_state": "euphoria",
                "risk_state": "low",
                "emotion_score": 85.0,
            },
            {
                "trade_date": "2026-01-03",
                "emotion_state": "hot",
                "risk_state": "medium",
                "emotion_score": 70.0,
            },
            {
                "trade_date": "2026-01-04",
                "emotion_state": "neutral",
                "risk_state": "high",
                "emotion_score": 50.0,
            },
            {
                "trade_date": "2026-01-05",
                "emotion_state": "panic",
                "risk_state": "high",
                "emotion_score": 25.0,
            },
        ]
    )

    result = build_style_state_daily(emotion)

    assert result[["trade_date", "style_state"]].to_dict("records") == [
        {"trade_date": "2026-01-02", "style_state": "growth_momentum"},
        {"trade_date": "2026-01-03", "style_state": "rotation_balanced"},
        {"trade_date": "2026-01-04", "style_state": "defensive_yield_proxy"},
        {"trade_date": "2026-01-05", "style_state": "cash_or_wait"},
    ]
    assert set(result["position_budget_hint"]) <= {"full", "reduced", "light"}


def test_build_style_state_daily_normalizes_mixed_trade_dates_and_drops_invalid() -> None:
    emotion = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "emotion_state": "neutral",
                "risk_state": "medium",
                "emotion_score": 50.0,
            },
            {
                "trade_date": "2026/01/03",
                "emotion_state": "hot",
                "risk_state": "low",
                "emotion_score": 75.0,
            },
            {
                "trade_date": "not-a-date",
                "emotion_state": "panic",
                "risk_state": "high",
                "emotion_score": 20.0,
            },
        ]
    )

    result = build_style_state_daily(emotion)

    assert result["trade_date"].tolist() == ["2026-01-02", "2026-01-03"]


def _funnel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "G1",
                "stock_name": "科技A",
                "mid_trend_funnel_score": 95,
                "shadow_top10_rank": 1,
                "industry_name": "软件和信息技术服务业",
                "volatility_20_score": 30,
                "max_drawdown_20_score": 60,
                "ma60_slope_score": 90,
                "score_total": 95,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D1",
                "stock_name": "长江电力",
                "mid_trend_funnel_score": 80,
                "shadow_top10_rank": 5,
                "industry_name": "电力、热力生产和供应业",
                "volatility_20_score": 95,
                "max_drawdown_20_score": 95,
                "ma60_slope_score": 70,
                "score_total": 80,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D2",
                "stock_name": "农业银行",
                "mid_trend_funnel_score": 75,
                "shadow_top10_rank": 7,
                "industry_name": "货币金融服务",
                "volatility_20_score": 90,
                "max_drawdown_20_score": 90,
                "ma60_slope_score": 65,
                "score_total": 75,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "X1",
                "stock_name": "地产弱势",
                "mid_trend_funnel_score": 70,
                "shadow_top10_rank": 9,
                "industry_name": "房地产业",
                "volatility_20_score": 20,
                "max_drawdown_20_score": 30,
                "ma60_slope_score": 20,
                "score_total": 70,
            },
        ]
    )


def test_candidate_sleeves_rank_growth_and_defensive_separately() -> None:
    growth = build_growth_momentum_candidates(_funnel(), top_n=2)
    defensive = build_defensive_yield_proxy_candidates(_funnel(), top_n=2)
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)

    assert growth.iloc[0]["asset_id"] == "G1"
    assert defensive["asset_id"].tolist() == ["D1", "D2"]
    assert rotation["asset_id"].tolist() == ["G1", "D1", "D2"]
    assert rotation["style_sleeve"].tolist() == [
        "growth_momentum",
        "defensive_yield_proxy",
        "defensive_yield_proxy",
    ]


def test_rotation_balanced_candidates_drop_duplicate_assets_per_date() -> None:
    growth = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "DUP",
                "stock_name": "重叠资产",
                "industry_name": "电力",
                "style_sleeve": "growth_momentum",
                "style_rank": 1,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "G2",
                "stock_name": "成长二号",
                "industry_name": "软件",
                "style_sleeve": "growth_momentum",
                "style_rank": 2,
            },
        ]
    )
    defensive = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "DUP",
                "stock_name": "重叠资产",
                "industry_name": "电力",
                "style_sleeve": "defensive_yield_proxy",
                "style_rank": 1,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D2",
                "stock_name": "防御二号",
                "industry_name": "银行",
                "style_sleeve": "defensive_yield_proxy",
                "style_rank": 2,
            },
        ]
    )

    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)

    assert rotation["asset_id"].tolist() == ["DUP", "G2", "D2"]
    assert rotation["asset_id"].is_unique
    assert rotation.iloc[0]["style_sleeve"] == "growth_momentum"


def test_candidate_sleeves_handle_minimal_realish_funnel_columns() -> None:
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "G1",
                "industry_name": "软件服务",
                "mid_trend_funnel_score": 88,
                "shadow_top10_rank": 1,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D1",
                "industry_name": "电力供应",
                "mid_trend_funnel_score": 72,
                "shadow_top10_rank": 6,
            },
        ]
    )

    growth = build_growth_momentum_candidates(funnel, top_n=2)
    defensive = build_defensive_yield_proxy_candidates(funnel, top_n=2)

    assert growth["asset_id"].tolist() == ["G1", "D1"]
    assert defensive["asset_id"].tolist() == ["D1"]


def test_defensive_candidates_with_no_keywords_do_not_match_empty_industries() -> None:
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A1",
                "industry_name": "",
                "mid_trend_funnel_score": 80,
                "shadow_top10_rank": 1,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A2",
                "industry_name": pd.NA,
                "mid_trend_funnel_score": 75,
                "shadow_top10_rank": 2,
            },
        ]
    )

    defensive = build_defensive_yield_proxy_candidates(funnel, defensive_industry_keywords=())

    assert defensive.empty


def test_equal_score_ties_are_ordered_by_asset_id() -> None:
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "B2",
                "industry_name": "电力",
                "mid_trend_funnel_score": 80,
                "shadow_top10_rank": 2,
                "volatility_20_score": 50,
                "max_drawdown_20_score": 50,
                "ma60_slope_score": 50,
                "score_total": 50,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A1",
                "industry_name": "电力",
                "mid_trend_funnel_score": 80,
                "shadow_top10_rank": 2,
                "volatility_20_score": 50,
                "max_drawdown_20_score": 50,
                "ma60_slope_score": 50,
                "score_total": 50,
            },
        ]
    )

    growth = build_growth_momentum_candidates(funnel, top_n=2)
    defensive = build_defensive_yield_proxy_candidates(funnel, top_n=2)

    assert growth["asset_id"].tolist() == ["A1", "B2"]
    assert defensive["asset_id"].tolist() == ["A1", "B2"]


def test_candidate_builders_return_empty_for_empty_frames_and_non_positive_top_n() -> None:
    empty = pd.DataFrame()
    funnel = _funnel()
    growth = build_growth_momentum_candidates(funnel, top_n=2)
    defensive = build_defensive_yield_proxy_candidates(funnel, top_n=2)

    assert build_growth_momentum_candidates(empty).empty
    assert build_defensive_yield_proxy_candidates(empty).empty
    assert build_rotation_balanced_candidates(empty, empty).empty
    assert build_growth_momentum_candidates(funnel, top_n=0).empty
    assert build_defensive_yield_proxy_candidates(funnel, top_n=0).empty
    assert build_rotation_balanced_candidates(growth, defensive, top_n=0).empty
    assert build_growth_momentum_candidates(funnel, top_n=-1).empty
    assert build_defensive_yield_proxy_candidates(funnel, top_n=-1).empty
    assert build_rotation_balanced_candidates(growth, defensive, top_n=-1).empty


def test_anchor_diagnostics_and_writer(tmp_path) -> None:
    style = build_style_state_daily(
        pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-02",
                    "emotion_state": "neutral",
                    "risk_state": "high",
                    "emotion_score": 40,
                }
            ]
        )
    )
    growth = build_growth_momentum_candidates(_funnel(), top_n=2)
    defensive = build_defensive_yield_proxy_candidates(_funnel(), top_n=3)
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)
    anchors = build_anchor_diagnostics(defensive)

    paths = write_market_style_switch_outputs(
        style_state=style,
        growth_candidates=growth,
        defensive_candidates=defensive,
        rotation_candidates=rotation,
        anchor_diagnostics=anchors,
        summary=pd.DataFrame([{"strategy_family": "fixed_mid_trend", "total_return": 0.0}]),
        year_breakdown=pd.DataFrame(
            [{"year": "2026", "strategy_family": "fixed_mid_trend", "total_return": 0.0}]
        ),
        emotion_breakdown=pd.DataFrame(
            [
                {
                    "emotion_state": "neutral",
                    "risk_state": "high",
                    "strategy_family": "fixed_mid_trend",
                    "total_return": 0.0,
                }
            ]
        ),
        output_dir=tmp_path,
    )

    expected_files = {
        "style_state_path": "market_style_state_daily.csv",
        "growth_candidates_path": "growth_momentum_candidates.csv",
        "defensive_candidates_path": "defensive_yield_proxy_candidates.csv",
        "rotation_candidates_path": "rotation_balanced_candidates.csv",
        "anchor_diagnostics_path": "anchor_diagnostics.csv",
        "summary_path": "style_switch_backtest_summary.csv",
        "year_breakdown_path": "style_switch_year_breakdown.csv",
        "emotion_breakdown_path": "style_switch_emotion_breakdown.csv",
        "report_path": "market_style_switch_v1_report.md",
    }
    assert {key: path.name for key, path in paths.items()} == expected_files
    assert all(path.exists() for path in paths.values())
    report = paths["report_path"].read_text(encoding="utf-8")
    assert "# Market Style Switch V1 Report" in report
    assert "fixed_mid_trend" in report
    assert "neutral" in report
    assert anchors["anchor_present"].any()
    assert set(anchors.loc[anchors["anchor_present"], "anchor_name"]) & {"长江电力", "农业银行"}


def test_anchor_diagnostics_match_canonical_asset_id_without_stock_name() -> None:
    defensive = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "CN:SH:600900",
                "stock_name": pd.NA,
                "industry_name": "电力",
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "601088",
                "industry_name": "煤炭",
            },
        ]
    )

    anchors = build_anchor_diagnostics(defensive)

    present = anchors.loc[anchors["anchor_present"], ["anchor_name", "anchor_asset_id"]]
    assert present.to_dict("records") == [
        {"anchor_name": "长江电力", "anchor_asset_id": "CN:SH:600900"},
        {"anchor_name": "中国神华", "anchor_asset_id": "CN:SH:601088"},
    ]


def test_anchor_diagnostics_strip_whitespace_from_chinese_name_and_asset_id() -> None:
    defensive = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": " CN:SH:601288 ",
                "stock_name": " 农业银行 ",
                "industry_name": "银行",
            }
        ]
    )

    anchors = build_anchor_diagnostics(defensive)

    row = anchors.loc[anchors["anchor_name"] == "农业银行"].iloc[0]
    assert row["anchor_asset_id"] == "CN:SH:601288"
    assert bool(row["anchor_present"])


def test_report_renders_when_to_markdown_dependency_is_unavailable(tmp_path, monkeypatch) -> None:
    def raise_import_error(self, *args, **kwargs):
        raise ImportError("tabulate is not installed")

    monkeypatch.setattr(pd.DataFrame, "to_markdown", raise_import_error)

    paths = write_market_style_switch_outputs(
        style_state=pd.DataFrame(),
        growth_candidates=pd.DataFrame(),
        defensive_candidates=pd.DataFrame(),
        rotation_candidates=pd.DataFrame(),
        anchor_diagnostics=pd.DataFrame(),
        summary=pd.DataFrame([{"strategy_family": "fixed_mid_trend", "total_return": 0.0}]),
        year_breakdown=pd.DataFrame([{"year": "2026", "strategy_family": "fixed_mid_trend"}]),
        emotion_breakdown=pd.DataFrame([{"emotion_state": "neutral", "strategy_family": "fixed_mid_trend"}]),
        output_dir=tmp_path,
    )

    report = paths["report_path"].read_text(encoding="utf-8")
    assert "# Market Style Switch V1 Report" in report
    assert "fixed_mid_trend" in report


def test_writer_accepts_empty_frames_and_still_writes_all_files(tmp_path) -> None:
    paths = write_market_style_switch_outputs(
        style_state=pd.DataFrame(),
        growth_candidates=pd.DataFrame(),
        defensive_candidates=pd.DataFrame(),
        rotation_candidates=pd.DataFrame(),
        anchor_diagnostics=pd.DataFrame(),
        summary=pd.DataFrame(),
        year_breakdown=pd.DataFrame(),
        emotion_breakdown=pd.DataFrame(),
        output_dir=tmp_path,
    )

    assert all(path.exists() for path in paths.values())
    assert paths["report_path"].read_text(encoding="utf-8").startswith("# Market Style Switch V1 Report")
    csv_paths = {key: path for key, path in paths.items() if key != "report_path"}
    read_back = {key: pd.read_csv(path) for key, path in csv_paths.items()}
    assert read_back["style_state_path"].columns.tolist() == [
        "trade_date",
        "emotion_state",
        "risk_state",
        "emotion_score",
        "style_state",
        "style_reason",
        "position_budget_hint",
    ]
    assert read_back["growth_candidates_path"].columns.tolist() == [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "style_sleeve",
        "style_rank",
        "growth_rank_score",
    ]
    assert read_back["defensive_candidates_path"].columns.tolist() == [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "style_sleeve",
        "style_rank",
        "defensive_rank_score",
    ]
    assert read_back["rotation_candidates_path"].columns.tolist() == [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "style_sleeve",
        "style_rank",
        "growth_rank_score",
        "defensive_rank_score",
    ]
    assert read_back["anchor_diagnostics_path"].columns.tolist() == [
        "trade_date",
        "anchor_name",
        "anchor_asset_id",
        "anchor_present",
    ]
    assert read_back["summary_path"].columns.tolist() == [
        "strategy_family",
        "total_return",
        "annualized_return",
        "max_drawdown",
        "days",
    ]
    assert read_back["year_breakdown_path"].columns.tolist() == [
        "year",
        "strategy_family",
        "total_return",
        "max_drawdown",
        "days",
    ]
    assert read_back["emotion_breakdown_path"].columns.tolist() == [
        "emotion_state",
        "risk_state",
        "style_state",
        "strategy_family",
        "total_return",
        "max_drawdown",
        "days",
    ]


def test_run_style_switch_backtest_from_frames_returns_three_strategy_families(tmp_path) -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "emotion_state": "euphoria", "risk_state": "low", "emotion_score": 85},
            {"trade_date": "2026-01-03", "emotion_state": "neutral", "risk_state": "high", "emotion_score": 40},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "G1", "close": 10.0},
            {"trade_date": "2026-01-03", "asset_id": "G1", "close": 9.0},
            {"trade_date": "2026-01-02", "asset_id": "D1", "close": 10.0},
            {"trade_date": "2026-01-03", "asset_id": "D1", "close": 10.2},
        ]
    )

    result = run_style_switch_backtest_from_frames(
        emotion=emotion,
        funnel=_funnel(),
        prices=prices,
        start_date="2026-01-02",
        end_date="2026-01-03",
        output_dir=tmp_path,
        top_n=1,
    )

    assert set(result["summary"]["strategy_family"]) == {
        "fixed_mid_trend",
        "emotion_budget_only",
        "emotion_style_switch",
    }
    assert result["paths"]["summary_path"].exists()
