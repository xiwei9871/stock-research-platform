from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame


def _detail() -> pd.DataFrame:
    rows = []
    specs = [
        ("electronics_a", "计算机、通信和其他电子设备制造业", "stable_trend_watch", 100, 88, 80),
        ("electronics_b", "计算机、通信和其他电子设备制造业", "mainline_momentum_watch", 99, 86, 78),
        ("auto_high", "汽车制造业", "stable_trend_watch", 98, 87, 75),
        ("internet_high", "互联网和相关服务", "stable_trend_watch", 97, 88, 74),
        ("equipment", "专用设备制造业", "stable_trend_watch", 96, 84, 72),
        ("elasticity", "计算机、通信和其他电子设备制造业", "high_elasticity_watch", 95, 83, 50),
        ("chemical", "化学原料和化学制品制造业", "stable_trend_watch", 94, 82, 70),
    ]
    for asset_id, industry, layer, score, trend, drawdown_score in specs:
        rows.append(
            {
                "trade_date": "2025-01-02",
                "asset_id": asset_id,
                "ts_code": "",
                "stock_name": asset_id,
                "mid_trend_layer": layer,
                "mid_trend_funnel_score": score,
                "score_rank": 100 - score,
                "volatility_20_score": 20,
                "trend_r2_20_score": trend,
                "max_drawdown_20_score": drawdown_score,
                "ret_20_score": 90,
                "market_regime": "mainline",
                "industry_name": industry,
                "mainline_status": "sustained_mainline",
                "mainline_context": "mainline",
                "industry_mainline_score_v1": 0.8,
            }
        )
    return pd.DataFrame(rows)


def test_build_mid_trend_shadow_top10_outputs_structured_shadow_rows():
    result = build_mid_trend_shadow_top10_from_frame(_detail(), top_n=5)

    top10 = result["top10"]
    weak_industries = {"汽车制造业", "互联网和相关服务", "化学原料和化学制品制造业"}
    assert len(top10) == 5
    assert set(top10["shadow_rule_version"]) == {"context_v2_structured_top10"}
    assert int(top10["industry_name"].isin(weak_industries).sum()) <= 1
    assert "structure_slot" in top10.columns
    assert "shadow_note" in top10.columns
    assert "交易" not in " ".join(top10["shadow_note"].astype(str))


def test_mid_trend_shadow_top10_preserves_structured_rank_order():
    result = build_mid_trend_shadow_top10_from_frame(_detail(), top_n=5)

    top10 = result["top10"].sort_values("shadow_top10_rank")
    assert top10.iloc[0]["asset_id"] == "electronics_a"
    assert top10["shadow_top10_rank"].tolist() == [1, 2, 3, 4, 5]


def test_mid_trend_shadow_top10_derives_ts_code_from_asset_id_when_missing():
    frame = _detail()
    frame.loc[0, "asset_id"] = "CN:SZ:000001"
    frame.loc[0, "ts_code"] = pd.NA

    result = build_mid_trend_shadow_top10_from_frame(frame, top_n=5)

    row = result["top10"][result["top10"]["asset_id"].eq("CN:SZ:000001")].iloc[0]
    assert row["ts_code"] == "000001.SZ"


def test_mid_trend_shadow_top10_excludes_risk_layer_and_st_names():
    frame = _detail()
    frame.loc[0, "asset_id"] = "risk_layer"
    frame.loc[0, "stock_name"] = "RiskLayer"
    frame.loc[0, "mid_trend_layer"] = "risk_exclusion_watch"
    frame.loc[0, "mid_trend_funnel_score"] = 200
    frame.loc[0, "trend_r2_20_score"] = 99
    frame.loc[1, "asset_id"] = "st_name"
    frame.loc[1, "stock_name"] = "*ST测试"
    frame.loc[1, "mid_trend_funnel_score"] = 199
    frame.loc[1, "trend_r2_20_score"] = 99
    frame["is_st"] = False
    frame.loc[2, "asset_id"] = "status_st"
    frame.loc[2, "stock_name"] = "状态ST"
    frame.loc[2, "mid_trend_funnel_score"] = 198
    frame.loc[2, "trend_r2_20_score"] = 99
    frame.loc[2, "is_st"] = True

    result = build_mid_trend_shadow_top10_from_frame(frame, top_n=5)

    assert {"risk_layer", "st_name", "status_st"}.isdisjoint(set(result["top10"]["asset_id"]))


def test_mid_trend_shadow_top10_writes_outputs(tmp_path: Path):
    result = build_mid_trend_shadow_top10_from_frame(_detail(), top_n=5, output_dir=tmp_path)

    assert Path(result["paths"]["top10"]).exists()
    assert Path(result["paths"]["daily_summary"]).exists()
    assert Path(result["paths"]["industry_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_shadow_top10(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "top10": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "top10": str(tmp_path / "top10.csv"),
                "daily_summary": str(tmp_path / "daily.csv"),
                "industry_summary": str(tmp_path / "industry.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_top10", fake_run)

    cli.main_for_args(
        [
            "build-mid-trend-shadow-top10",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--top-n",
            "10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top_n"] == 10
    out = capsys.readouterr().out
    assert "mid_trend_shadow_top10|top10|" in out
    assert "mid_trend_shadow_top10|rows|1" in out
