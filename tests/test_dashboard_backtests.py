import copy
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research.dashboard import backtests
from stock_research import mid_trend_v1, tech_bottleneck_eod, tech_bottleneck_v1
from stock_research.strategy_publication_contracts import build_publication_identity, get_publication_contract


def _official_result(strategy_id: str) -> dict:
    contract = get_publication_contract(strategy_id)
    summary = {
        "engine_version": contract.engine_version,
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "adjust_type": "hfq",
        "frequency": contract.normalized_run_config["rebalance_frequency"],
    }
    if strategy_id == "lhb_shortline":
        summary.update(
            {
                "phase18c_strategy": "auction_enhanced_rerank",
                "risk_profile": "balanced",
                **contract.publication_policy,
            }
        )
    elif strategy_id == "mid_trend":
        summary["benchmark_variant"] = contract.normalized_run_config["benchmark_variant"]
    else:
        summary.update(
            {
                "universe": contract.normalized_run_config["universe"],
                "protection_name": contract.normalized_run_config["protection_name"],
            }
        )
    return {
        "strategy_id": strategy_id,
        "config": dict(contract.normalized_run_config),
        "summary": summary,
        "payload": {"preserve": True},
    }


def test_mid_trend_engine_effective_config_records_weekly_frequency():
    config = mid_trend_v1.MidTrendV1Config(
        start_date="2026-01-01",
        end_date="2026-07-24",
        top_n=5,
        transaction_cost_bps=10.0,
        max_position_weight=0.2,
        benchmark_variant=get_publication_contract("mid_trend").variant,
    )
    payload = mid_trend_v1._effective_config_payload(config, report_start_date=None)
    assert payload["rebalance_frequency"] == "weekly"


def test_tech_engine_effective_config_records_universe_and_protection():
    config = tech_bottleneck_v1.TechBottleneckV1Config(
        start_date="2026-01-01",
        end_date="2026-07-24",
        top_n=5,
        rebalance_frequency="biweekly",
        transaction_cost_bps=10.0,
        max_position_weight=0.2,
    )
    payload = tech_bottleneck_v1._effective_config_payload(config, report_start_date=None)
    assert payload["universe"] == "strict_153_st_only_financial_state"
    assert payload["protection_name"] == "rank_exit_top10_1d"


def test_tech_eod_engine_result_config_records_full_official_contract():
    payload = tech_bottleneck_eod._effective_strategy_config(
        start_date="2026-01-01", end_date="2026-07-24"
    )
    contract = get_publication_contract("tech_bottleneck")
    for field, expected in contract.normalized_run_config.items():
        assert payload[field] == expected


def test_attach_publication_identity_succeeds_for_mid_and_lhb_with_detached_copies():
    for strategy_id in ("mid_trend", "lhb_shortline"):
        result = _official_result(strategy_id)
        attached = backtests.attach_publication_identity(result, profile="balanced")
        expected = build_publication_identity(get_publication_contract(strategy_id))

        assert attached["publication_identity"] == expected
        assert attached["summary"]["publication_identity"] == expected
        assert attached["publication_identity"] is not attached["summary"]["publication_identity"]
        attached["publication_identity"]["publication_policy"]["changed"] = True
        assert "changed" not in attached["summary"]["publication_identity"]["publication_policy"]
        assert attached["payload"] == {"preserve": True}


def test_attach_publication_identity_rejects_wrong_lhb_policy():
    result = _official_result("lhb_shortline")
    result["summary"]["market_regime_policy"] = "legacy_overlay"

    with pytest.raises(ValueError, match="market_regime_policy"):
        backtests.attach_publication_identity(result, profile="balanced")


@pytest.mark.parametrize(
    "field",
    ["strategy_version", "selection_policy", "market_regime_policy"],
)
def test_validate_official_strategy_result_rejects_missing_lhb_policy(field):
    result = _official_result("lhb_shortline")
    del result["summary"][field]

    with pytest.raises(ValueError, match=field):
        backtests.validate_official_strategy_result(result, profile="balanced")


def test_attach_publication_identity_rejects_explicit_config_conflict():
    result = _official_result("mid_trend")
    result["config"]["benchmark_variant"] = "legacy_variant"

    with pytest.raises(ValueError, match="benchmark_variant"):
        backtests.attach_publication_identity(result, profile="balanced")


def test_attach_publication_identity_rejects_explicit_config_policy_conflict():
    result = _official_result("lhb_shortline")
    result["config"]["selection_policy"] = "legacy_selection"

    with pytest.raises(ValueError, match="selection_policy"):
        backtests.attach_publication_identity(result, profile="balanced")


def test_attach_publication_identity_rejects_predeclared_identity_mismatch():
    result = _official_result("mid_trend")
    result["publication_identity"] = {
        **build_publication_identity(get_publication_contract("mid_trend")),
        "variant": "legacy_variant",
    }

    with pytest.raises(ValueError, match="publication identity mismatch"):
        backtests.attach_publication_identity(result, profile="balanced")


def test_attach_publication_identity_rejects_config_identity_mismatch():
    result = _official_result("mid_trend")
    result["config"]["publication_identity"] = {
        **build_publication_identity(get_publication_contract("mid_trend")),
        "config_fingerprint": "legacy-fingerprint",
    }

    with pytest.raises(ValueError, match="publication identity mismatch"):
        backtests.attach_publication_identity(result, profile="balanced")


def test_validate_official_strategy_result_rejects_missing_engine_evidence():
    result = _official_result("mid_trend")
    del result["summary"]["engine_version"]

    with pytest.raises(ValueError, match="engine"):
        backtests.validate_official_strategy_result(result, profile="balanced")


def test_validate_official_strategy_result_rejects_empty_official_config_evidence():
    contract = get_publication_contract("mid_trend")
    result = {
        "strategy_id": "mid_trend",
        "config": {},
        "summary": {"benchmark_variant": contract.variant},
    }

    with pytest.raises(ValueError, match="official config evidence"):
        backtests.validate_official_strategy_result(result, profile="balanced")


@pytest.mark.parametrize("strategy_id", ["lhb_shortline", "mid_trend", "tech_bottleneck"])
def test_summary_labels_cannot_replace_complete_engine_config(strategy_id):
    result = _official_result(strategy_id)
    result["config"] = {}

    with pytest.raises(ValueError, match="official config evidence missing"):
        backtests.attach_publication_identity(result, profile="balanced")


def test_validate_official_strategy_result_rejects_partial_normalized_config_evidence():
    result = _official_result("mid_trend")
    del result["config"]["max_position_weight"]

    with pytest.raises(ValueError, match="max_position_weight"):
        backtests.validate_official_strategy_result(result, profile="balanced")


def test_official_fresh_path_attaches_identity_after_contract_config(monkeypatch):
    result = _official_result("mid_trend")
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")
    run_config = {
        "top_n": 5,
        "rebalance_frequency": "weekly",
        "transaction_cost_bps": 10.0,
        "max_position_weight": 0.2,
        "adjust_type": "hfq",
        "benchmark_variant": get_publication_contract("mid_trend").variant,
        "contract_id": get_publication_contract("mid_trend").contract_id,
        "contract_profile": "balanced",
        "contract_variant": get_publication_contract("mid_trend").variant,
    }
    monkeypatch.setattr(backtests, "_parse_backtest_request", lambda payload: ("mid_trend", params, run_config, None))
    monkeypatch.setattr(backtests, "_apply_strategy_contract_run_config", lambda strategy_id, config, payload: config)
    monkeypatch.setattr(backtests, "run_mid_trend_v1_backtest_for_dashboard", lambda payload: copy.deepcopy(result))

    attached = backtests.run_fresh_backtest({"strategy_id": "mid_trend", "start_date": "2026-01-01", "end_date": "2026-01-02"})

    assert attached["publication_identity"]["strategy_id"] == "mid_trend"
    assert attached["summary"]["publication_identity"] == attached["publication_identity"]


@pytest.mark.parametrize("strategy_id", ["lhb_shortline", "mid_trend", "tech_bottleneck"])
def test_official_fresh_records_the_complete_config_passed_to_engine(monkeypatch, strategy_id):
    result = _official_result(strategy_id)
    contract = get_publication_contract(strategy_id)
    run_config = dict(contract.normalized_run_config)
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")
    received = {}

    def engine(payload):
        received.update(payload)
        returned = copy.deepcopy(result)
        returned["config"] = dict(run_config)
        return returned

    monkeypatch.setattr(
        backtests,
        "_parse_backtest_request",
        lambda payload: (strategy_id, params, dict(run_config), None),
    )
    monkeypatch.setattr(
        backtests,
        "_apply_strategy_contract_run_config",
        lambda strategy_id, config, payload: config,
    )
    monkeypatch.setattr(
        backtests,
        {
            "lhb_shortline": "run_lhb_shortline_v1_backtest_for_dashboard",
            "mid_trend": "run_mid_trend_v1_backtest_for_dashboard",
            "tech_bottleneck": "run_tech_bottleneck_v1_backtest_for_dashboard",
        }[strategy_id],
        engine,
    )

    attached = backtests.run_fresh_backtest({"strategy_id": strategy_id})

    assert {key: received[key] for key in run_config} == run_config
    assert {key: attached["config"][key] for key in run_config} == run_config


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda config: None, "engine result config must be a mapping"),
        (lambda config: config.pop("max_position_weight"), "engine config missing"),
        (lambda config: config.__setitem__("top_n", 999), "engine config mismatch"),
    ],
)
def test_official_fresh_rejects_missing_or_conflicting_engine_config(
    monkeypatch, mutation, message
):
    strategy_id = "mid_trend"
    contract = get_publication_contract(strategy_id)
    run_config = dict(contract.normalized_run_config)
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")

    def engine(payload):
        returned = _official_result(strategy_id)
        config = dict(run_config)
        if message == "engine result config must be a mapping":
            returned["config"] = None
        else:
            mutation(config)
            returned["config"] = config
        return returned

    monkeypatch.setattr(
        backtests,
        "_parse_backtest_request",
        lambda payload: (strategy_id, params, dict(run_config), None),
    )
    monkeypatch.setattr(
        backtests,
        "_apply_strategy_contract_run_config",
        lambda strategy_id, config, payload: config,
    )
    monkeypatch.setattr(backtests, "run_mid_trend_v1_backtest_for_dashboard", engine)

    with pytest.raises(ValueError, match=message):
        backtests.run_fresh_backtest({"strategy_id": strategy_id})


def test_official_fresh_rejects_engine_config_that_disagrees_with_official_run_config(
    monkeypatch,
):
    strategy_id = "tech_bottleneck"
    contract = get_publication_contract(strategy_id)
    run_config = dict(contract.normalized_run_config)
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")

    def engine(payload):
        returned = _official_result(strategy_id)
        returned["config"] = {**run_config, "top_n": 999}
        return returned

    monkeypatch.setattr(
        backtests,
        "_parse_backtest_request",
        lambda payload: (strategy_id, params, dict(run_config), None),
    )
    monkeypatch.setattr(
        backtests,
        "_apply_strategy_contract_run_config",
        lambda strategy_id, config, payload: config,
    )
    monkeypatch.setattr(backtests, "run_tech_bottleneck_v1_backtest_for_dashboard", engine)

    with pytest.raises(ValueError, match="engine config mismatch"):
        backtests.run_fresh_backtest({"strategy_id": strategy_id})


def test_official_replay_path_attaches_identity_after_contract_config(monkeypatch):
    result = _official_result("lhb_shortline")
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")
    contract = get_publication_contract("lhb_shortline")
    run_config = {
        "top_n": 5,
        "rebalance_frequency": "daily",
        "transaction_cost_bps": 10.0,
        "max_position_weight": 0.2,
        "adjust_type": "hfq",
        "risk_profile": "balanced",
        "contract_id": contract.contract_id,
        "contract_profile": "balanced",
        "contract_variant": contract.variant,
    }
    adapter = SimpleNamespace(run_replay=lambda params, config: copy.deepcopy(result))
    monkeypatch.setattr(backtests, "_parse_backtest_request", lambda payload: ("lhb_shortline", params, run_config, None))
    monkeypatch.setattr(backtests, "_apply_strategy_contract_run_config", lambda strategy_id, config, payload: config)
    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "lhb_shortline", adapter)

    attached = backtests.run_replay_backtest({"strategy_id": "lhb_shortline", "start_date": "2026-01-01", "end_date": "2026-01-02"})

    assert attached["publication_identity"]["strategy_id"] == "lhb_shortline"
    assert attached["summary"]["publication_identity"] == attached["publication_identity"]


def test_official_replay_preserves_raw_adapter_config_and_rejects_nonofficial_result(monkeypatch):
    params = SimpleNamespace(start_date="2026-01-01", end_date="2026-01-02")
    raw_config = {
        "top_n": 20,
        "rebalance_frequency": "weekly",
        "transaction_cost_bps": 0.0,
        "max_position_weight": None,
        "adjust_type": "hfq",
        "benchmark_variant": get_publication_contract("mid_trend").variant,
    }
    received = {}

    def run_replay(params, config):
        received.update(config)
        result = _official_result("mid_trend")
        result["config"].update(config)
        return result

    monkeypatch.setattr(
        backtests,
        "_parse_backtest_request",
        lambda payload: ("mid_trend", params, raw_config, None),
    )
    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "mid_trend",
        SimpleNamespace(run_replay=run_replay),
    )

    with pytest.raises(ValueError, match="official config mismatch"):
        backtests.run_replay_backtest(
            {
                "strategy_id": "mid_trend",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            }
        )

    assert received == raw_config


def test_latest_eod_strategy_module_uses_recent_manifest_by_module(monkeypatch):
    monkeypatch.setattr(
        backtests,
        "load_recent_data_run_manifest",
        lambda: [
            {"module": "generated_reports", "latest_trade_date": "2026-07-02", "status": "success"},
            {"module": "strategy_lhb_shortline", "latest_trade_date": "2026-06-05", "status": "success"},
            {"module": "strategy_lhb_shortline", "latest_trade_date": "2026-07-02", "status": "success"},
        ],
        raising=False,
    )

    module = backtests._latest_eod_strategy_module("lhb_shortline")

    assert module["latest_trade_date"] == "2026-07-02"


def test_lhb_stale_performance_does_not_publish_latest_day_zero_return(monkeypatch):
    monkeypatch.setattr(backtests, "_read_eod_strategy_rows", lambda module, latest_trade_date, strategy_id: [])
    monkeypatch.setattr(backtests, "_validate_eod_summary_contract", lambda strategy_id, summary: ("success", "ok"))
    monkeypatch.setattr(backtests, "_metrics_from_eod_equity_path", lambda module, strategy: {})
    monkeypatch.setattr(
        backtests,
        "_latest_eod_strategy_module",
        lambda strategy_id: {
            "module": "strategy_lhb_shortline",
            "status": "success",
            "row_count": 4,
            "latest_trade_date": "2026-06-29",
            "metadata": {
                "summary": {
                    "total_return": 1.6241,
                    "max_drawdown": -0.0842,
                    "latest_day_return": 0.0,
                    "latest_period_return": 0.0,
                    "latest_period_label": "最近交易日",
                    "performance_effective_date": "2026-06-26",
                }
            },
        },
    )

    strategy = backtests._with_latest_eod_strategy_metrics(
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline",
            "latest_metrics": {},
        }
    )

    metrics = strategy["latest_metrics"]
    assert metrics["as_of_date"] == "2026-06-26"
    assert metrics["signal_as_of_date"] == "2026-06-29"
    assert metrics["performance_status"] == "stale"
    assert "latest_day_return_pct" not in metrics
    assert "latest_period_return_pct" not in metrics
    assert metrics["latest_period_label"] == "收益估值截止 2026-06-26"


def test_eod_equity_path_relocates_synced_local_output_root(monkeypatch, tmp_path):
    output_root = tmp_path / "outputs"
    equity_path = (
        output_root
        / "research"
        / "strategy_daily_eod"
        / "2026-07-03"
        / "strategy_tech_bottleneck_equity.csv"
    )
    equity_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {"trade_date": "2026-07-02", "equity": 1.10, "drawdown": -0.02, "daily_return": 0.01},
            {"trade_date": "2026-07-03", "equity": 1.21, "drawdown": -0.01, "daily_return": 0.10},
        ]
    ).to_csv(equity_path, index=False)
    monkeypatch.setattr(backtests, "SETTINGS", SimpleNamespace(output_root=output_root), raising=False)

    metrics = backtests._metrics_from_eod_equity_path(
        {
            "metadata": {
                "output_paths": {
                    "equity_path": "/mnt/internal/stock_research/outputs/research/strategy_daily_eod/2026-07-03/strategy_tech_bottleneck_equity.csv"
                }
            }
        },
        {"strategy_id": "tech_bottleneck", "default_parameters": {"rebalance_frequency": "daily"}},
    )

    assert metrics["latest_day_return_pct"] == 10.0


def test_eod_summary_exposes_lhb_strategy_version_and_selection_policy():
    metrics = backtests._metrics_from_eod_summary(
        {
            "total_return": 1.23,
            "strategy_version": "lhb_v1_stable_safe_top5",
            "selection_policy": "phase18c_top5_then_eligibility_no_refill",
            "market_regime_policy": "disabled_for_stable_strategy",
            "cash_slot_count": 9,
        }
    )

    assert metrics["strategy_version"] == "lhb_v1_stable_safe_top5"
    assert metrics["selection_policy"] == "phase18c_top5_then_eligibility_no_refill"
    assert metrics["market_regime_policy"] == "disabled_for_stable_strategy"
    assert metrics["cash_slot_count"] == 9


def test_eod_summary_projects_generic_publication_identity_fields_and_artifact_version():
    metrics = backtests._metrics_from_eod_summary(
        {
            "publication_identity": {
                "contract_id": "mid_trend:balanced:v1",
                "identity_schema_version": "strategy_publication_identity_v1",
                "config_fingerprint": "abc123",
                "publication_policy": {"benchmark_variant": "v1"},
            },
            "artifact_version": "artifact_v2",
        }
    )

    assert metrics == {
        "contract_id": "mid_trend:balanced:v1",
        "identity_schema_version": "strategy_publication_identity_v1",
        "config_fingerprint": "abc123",
        "publication_policy": {"benchmark_variant": "v1"},
        "artifact_version": "artifact_v2",
    }


def test_eod_summary_projects_lhb_metrics_from_generic_publication_policy():
    policy = {
        "strategy_version": "lhb_v1_stable_safe_top5",
        "selection_policy": "phase18c_top5_then_eligibility_no_refill",
        "market_regime_policy": "disabled_for_stable_strategy",
    }

    metrics = backtests._metrics_from_eod_summary(
        {"publication_identity": {"publication_policy": policy}}
    )

    assert metrics["publication_policy"] == policy
    assert metrics["strategy_version"] == policy["strategy_version"]
    assert metrics["selection_policy"] == policy["selection_policy"]
    assert metrics["market_regime_policy"] == policy["market_regime_policy"]
