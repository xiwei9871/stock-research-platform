from pathlib import Path

import pandas as pd
import pytest

from stock_research import industry_focus_score


def test_rank_by_date_computes_cross_sectional_percentiles():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "value": 10.0},
            {"trade_date": "2026-01-01", "industry_name": "B", "value": 20.0},
            {"trade_date": "2026-01-01", "industry_name": "C", "value": 30.0},
            {"trade_date": "2026-01-02", "industry_name": "A", "value": 5.0},
            {"trade_date": "2026-01-02", "industry_name": "B", "value": 15.0},
        ]
    )

    ranked = industry_focus_score.rank_by_date(
        frame,
        value_col="value",
        output_col="value_rank",
        ascending=True,
    )

    day1 = ranked[ranked["trade_date"] == "2026-01-01"].sort_values("industry_name")
    day2 = ranked[ranked["trade_date"] == "2026-01-02"].sort_values("industry_name")
    assert list(day1["value_rank"]) == pytest.approx([1 / 3, 2 / 3, 1.0])
    assert list(day2["value_rank"]) == pytest.approx([0.5, 1.0])


def test_select_dynamic_topk_keeps_only_top_ranked_industries():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-01", "industry_name": "B", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-01", "industry_name": "C", "industry_focus_score": 0.1},
            {"trade_date": "2026-01-02", "industry_name": "A", "industry_focus_score": 0.4},
            {"trade_date": "2026-01-02", "industry_name": "B", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-02", "industry_name": "C", "industry_focus_score": 0.6},
        ]
    )

    selected = industry_focus_score.select_dynamic_topk_focus(scores, top_k=2)

    assert selected[["trade_date", "industry_name"]].to_dict("records") == [
        {"trade_date": "2026-01-01", "industry_name": "A"},
        {"trade_date": "2026-01-01", "industry_name": "B"},
        {"trade_date": "2026-01-02", "industry_name": "B"},
        {"trade_date": "2026-01-02", "industry_name": "C"},
    ]
    assert set(selected["selection_mode"]) == {"dynamic_topk"}


def _industry_prices() -> pd.DataFrame:
    rows = []
    values = [
        ("2026-01-01", 10.0, 20.0, 30.0, 40.0),
        ("2026-01-02", 11.0, 21.0, 29.0, 39.0),
        ("2026-01-05", 12.0, 22.0, 28.0, 38.0),
        ("2026-01-06", 13.0, 23.0, 27.0, 37.0),
    ]
    for trade_date, a1_close, a2_close, b1_close, b2_close in values:
        for asset_id, close in [
            ("A1", a1_close),
            ("A2", a2_close),
            ("B1", b1_close),
            ("B2", b2_close),
        ]:
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "close": close,
                    "amount": close * 1000,
                }
            )
    return pd.DataFrame(rows)


def _industry_memberships() -> pd.DataFrame:
    rows = []
    for trade_date in ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]:
        rows.extend(
            [
                {"trade_date": trade_date, "asset_id": "A1", "industry_name": "强行业"},
                {"trade_date": trade_date, "asset_id": "A2", "industry_name": "强行业"},
                {"trade_date": trade_date, "asset_id": "B1", "industry_name": "弱行业"},
                {"trade_date": trade_date, "asset_id": "B2", "industry_name": "弱行业"},
            ]
        )
    return pd.DataFrame(rows)


def _stock_scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A1", "score_total": 95.0, "rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "A2", "score_total": 90.0, "rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "B1", "score_total": 50.0, "rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "B2", "score_total": 40.0, "rank": 4},
        ]
    )


def test_build_industry_scores_uses_only_dates_up_to_score_date():
    scores = industry_focus_score.build_industry_scores(
        prices=_industry_prices(),
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=2,
        top_candidate_count=2,
        short_window=2,
        long_window=3,
    )

    scored_day = scores[scores["trade_date"] == "2026-01-05"].set_index("industry_name")
    assert scored_day.loc["强行业", "industry_focus_score"] > scored_day.loc["弱行业", "industry_focus_score"]

    changed_future = _industry_prices()
    changed_future.loc[
        (changed_future["trade_date"] == "2026-01-06")
        & (changed_future["asset_id"].isin(["B1", "B2"])),
        "close",
    ] = 1000.0
    future_changed_scores = industry_focus_score.build_industry_scores(
        prices=changed_future,
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=2,
        top_candidate_count=2,
        short_window=2,
        long_window=3,
    )
    original = scores[scores["trade_date"] == "2026-01-05"].sort_values("industry_name")
    revised = future_changed_scores[
        future_changed_scores["trade_date"] == "2026-01-05"
    ].sort_values("industry_name")
    assert list(original["industry_focus_score"]) == pytest.approx(
        list(revised["industry_focus_score"])
    )


def test_build_industry_scores_excludes_industries_below_min_stock_count():
    scores = industry_focus_score.build_industry_scores(
        prices=_industry_prices(),
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=3,
        top_candidate_count=2,
        short_window=2,
        long_window=3,
    )

    assert scores.empty


def test_select_dynamic_hysteresis_retains_until_exit_rank():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-01", "industry_name": "B", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-01", "industry_name": "C", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-02", "industry_name": "B", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-02", "industry_name": "C", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-02", "industry_name": "A", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-03", "industry_name": "B", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-03", "industry_name": "C", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-03", "industry_name": "D", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-03", "industry_name": "A", "industry_focus_score": 0.1},
        ]
    )

    selected = industry_focus_score.select_dynamic_hysteresis_focus(
        scores,
        enter_top_n=2,
        exit_top_n=3,
        max_focus_industries=3,
        min_focus_industries=1,
    )

    by_date = selected.groupby("trade_date")["industry_name"].apply(list).to_dict()
    assert by_date["2026-01-01"] == ["A", "B"]
    assert by_date["2026-01-02"] == ["B", "C", "A"]
    assert by_date["2026-01-03"] == ["B", "C"]
    assert set(selected["selection_mode"]) == {"dynamic_hysteresis"}


def test_select_fixed_focus_labels_mode_as_ex_post():
    selected = industry_focus_score.select_fixed_focus(
        trade_dates=["2026-01-01", "2026-01-02"],
        focus_industries=("行业A", "行业B"),
    )

    assert len(selected) == 4
    assert set(selected["selection_mode"]) == {"fixed_ex_post"}


def test_filter_scores_to_focus_industries_keeps_scores_inside_selected_industries():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "rank": 2, "score_total": 80.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "行业B"},
        ]
    )
    focus = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "industry_name": "行业A",
                "selection_mode": "dynamic_topk",
                "focus_rank": 1,
                "industry_focus_score": 0.9,
            }
        ]
    )

    filtered = industry_focus_score.filter_scores_to_focus_industries(scores, memberships, focus)

    assert filtered[["trade_date", "asset_id", "industry_name"]].to_dict("records") == [
        {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"}
    ]


def test_summarize_backtest_result_includes_cost_and_variant():
    row = industry_focus_score.summarize_variant_result(
        variant="base_top20",
        transaction_cost_bps=20.0,
        score_rows=10,
        result_summary={"cumulative_return": 0.1, "annual_return": 0.2, "max_drawdown": -0.05},
    )

    assert row["variant"] == "base_top20"
    assert row["transaction_cost_bps"] == 20.0
    assert row["score_rows"] == 10
    assert row["cumulative_return"] == 0.1


def test_run_industry_focus_backtest_report_writes_outputs(tmp_path: Path, monkeypatch):
    scored = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "score_total": 90.0, "rank": 1},
            {"trade_date": "2026-01-01", "asset_id": "B1", "score_total": 80.0, "rank": 2},
            {"trade_date": "2026-01-02", "asset_id": "A1", "score_total": 91.0, "rank": 1},
            {"trade_date": "2026-01-02", "asset_id": "B1", "score_total": 79.0, "rank": 2},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "close": 10.0, "amount": 1000.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "close": 20.0, "amount": 2000.0},
            {"trade_date": "2026-01-02", "asset_id": "A1", "close": 11.0, "amount": 1100.0},
            {"trade_date": "2026-01-02", "asset_id": "B1", "close": 19.0, "amount": 1900.0},
            {"trade_date": "2026-01-05", "asset_id": "A1", "close": 12.0, "amount": 1200.0},
            {"trade_date": "2026-01-05", "asset_id": "B1", "close": 18.0, "amount": 1800.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "行业B"},
            {"trade_date": "2026-01-02", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-02", "asset_id": "B1", "industry_name": "行业B"},
            {"trade_date": "2026-01-05", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-05", "asset_id": "B1", "industry_name": "行业B"},
        ]
    )
    monkeypatch.setattr(industry_focus_score, "load_stock_scores", lambda **kwargs: scored)
    monkeypatch.setattr(industry_focus_score, "load_prices", lambda **kwargs: prices)
    monkeypatch.setattr(industry_focus_score, "load_industry_memberships", lambda **kwargs: memberships)

    result = industry_focus_score.run_industry_focus_backtest_report(
        start_date="2026-01-01",
        end_date="2026-01-05",
        top_n=1,
        dynamic_top_k=1,
        min_industry_stocks=1,
        transaction_cost_bps=(0.0, 20.0),
        reports_dir=tmp_path,
    )

    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["industry_scores"]).exists()
    assert Path(result["paths"]["focus_industries_daily"]).exists()
    report_text = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert report_text.startswith("# Industry Focus Score V1")
    assert set(result["summary"]["transaction_cost_bps"]) == {0.0, 20.0}
