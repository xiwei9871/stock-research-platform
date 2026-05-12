from stock_research.factor_eval.gate import decide_factor_gate


def test_decide_factor_gate_approves_when_primary_horizon_passes_thresholds():
    report = {
        "reports": {
            5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}},
            10: {"ic_summary": {"mean_ic": 0.03, "icir": 0.5, "ic_count": 30}},
        }
    }

    result = decide_factor_gate(
        factor_name="alpha101_demo",
        multi_horizon_report=report,
        primary_horizon=5,
        min_abs_mean_ic=0.02,
        min_icir=0.3,
        min_ic_count=20,
    )

    assert result["status"] == "approved"
    assert result["reason"] == "passed_thresholds"


def test_decide_factor_gate_rejects_low_sample_count():
    report = {"reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 3}}}}

    result = decide_factor_gate("alpha101_demo", report, min_ic_count=20)

    assert result["status"] == "rejected"
    assert result["reason"] == "insufficient_ic_count"
