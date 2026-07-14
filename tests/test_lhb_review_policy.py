import pandas as pd

from stock_research.lhb_review_policy import apply_lhb_top5_gate, classify_price_limit


def test_classify_price_limit_regimes_and_boundaries():
    cases = [
        ("CN:SZ:001399", "惠科股份", -9.50, "main_board", -9.50, True),
        ("CN:SZ:001399", "惠科股份", -9.49, "main_board", -9.50, False),
        ("CN:SZ:000078", "ST海王", -4.80, "st", -4.80, True),
        ("CN:SZ:300001", "特锐德", -19.00, "chinext", -19.00, True),
        ("CN:SH:688001", "华兴源创", -19.00, "star", -19.00, True),
        ("CN:BJ:920001", "北交样本", -29.00, "beijing", -29.00, True),
    ]

    for asset_id, name, pct_chg, regime, threshold, gated in cases:
        decision = classify_price_limit(asset_id=asset_id, stock_name=name, pct_chg=pct_chg)

        assert decision.regime == regime
        assert decision.threshold == threshold
        assert decision.near_limit_down is gated


def test_missing_pct_change_is_not_gated_but_is_auditable():
    decision = classify_price_limit(asset_id="CN:SZ:001399", stock_name="惠科股份", pct_chg=None)

    assert decision.near_limit_down is False
    assert decision.data_status == "pct_chg_missing"


def test_gate_downgrades_limit_down_candidate_and_refills_top5():
    frame = pd.DataFrame(
        [
            {
                "asset_id": f"CN:SZ:00000{i}",
                "stock_name": f"股票{i}",
                "score_total": 80 - i,
                "pct_chg": 1.0,
            }
            for i in range(1, 7)
        ]
    )
    frame.loc[3, ["asset_id", "stock_name", "pct_chg"]] = ["CN:SZ:001399", "惠科股份", -9.99]

    result = apply_lhb_top5_gate(frame)

    gated = result.loc[result["asset_id"].eq("CN:SZ:001399")].iloc[0]
    assert gated["raw_score"] == gated["score_total"]
    assert bool(gated["top5_eligible"]) is False
    assert gated["review_tier"] == "risk_watch"
    assert gated["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert len(result.loc[result["review_tier"].eq("top5_focus")]) == 5
    assert "CN:SZ:000006" in set(result.loc[result["review_tier"].eq("top5_focus"), "asset_id"])


def test_gate_does_not_fill_top5_with_ineligible_rows():
    frame = pd.DataFrame(
        [
            {
                "asset_id": f"CN:SZ:00139{i}",
                "stock_name": f"样本{i}",
                "score_total": 80 - i,
                "pct_chg": -9.8 if i >= 3 else 1.0,
            }
            for i in range(1, 6)
        ]
    )

    result = apply_lhb_top5_gate(frame)

    assert len(result.loc[result["review_tier"].eq("top5_focus")]) == 2
    assert len(result.loc[result["review_tier"].eq("risk_watch")]) == 3
