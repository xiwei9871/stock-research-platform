import copy
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from stock_research.dashboard import backtests
from stock_research.strategy_publication_contracts import build_publication_identity, get_publication_contract


def _official_result(strategy_id: str) -> dict[str, Any]:
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


def test_attach_publication_identity_succeeds_for_tech_bottleneck():
    attached = backtests.attach_publication_identity(
        _official_result("tech_bottleneck"),
        profile="balanced",
    )

    assert attached["publication_identity"] == build_publication_identity(
        get_publication_contract("tech_bottleneck")
    )


@pytest.mark.parametrize("missing_location", ["result", "summary"])
def test_validate_official_strategy_result_requires_attached_identities(missing_location):
    attached = backtests.attach_publication_identity(
        _official_result("mid_trend"),
        profile="balanced",
    )
    if missing_location == "result":
        del attached["publication_identity"]
    else:
        del attached["summary"]["publication_identity"]

    with pytest.raises(ValueError, match="publication identity missing"):
        backtests.validate_official_strategy_result(attached, profile="balanced")


def test_validate_official_strategy_result_accepts_attached_identity():
    attached = backtests.attach_publication_identity(
        _official_result("mid_trend"),
        profile="balanced",
    )

    assert backtests.validate_official_strategy_result(
        attached,
        profile="balanced",
    ) is attached


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
        "adjust_type": "hfq",
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


@pytest.mark.parametrize(
    ("strategy_id", "specific_defaults"),
    [
        ("lhb_shortline", {"risk_profile": "balanced"}),
        (
            "mid_trend",
            {
                "benchmark_variant": (
                    "top5_weekly_max2_selective_trend_holding_protection_v1"
                )
            },
        ),
        (
            "tech_bottleneck",
            {
                "protection_name": "rank_exit_top10_1d",
                "universe": "strict_153_st_only_financial_state",
            },
        ),
    ],
)
def test_official_replay_minimal_request_passes_official_defaults_to_adapter(
    monkeypatch,
    strategy_id,
    specific_defaults,
):
    received: dict[str, Any] = {}

    def run_replay(params, config):
        received.update(config)
        return copy.deepcopy(_official_result(strategy_id))

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        strategy_id,
        SimpleNamespace(run_replay=run_replay),
    )

    attached = backtests.run_replay_backtest(
        {
            "strategy_id": strategy_id,
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
        }
    )

    contract = get_publication_contract(strategy_id)
    assert received == {
        "score_version": "manual_v1",
        "top_n": 5,
        "rebalance_frequency": contract.normalized_run_config["rebalance_frequency"],
        "transaction_cost_bps": 10.0,
        "max_positions": None,
        "max_position_weight": 0.2,
        "risk_profile": "balanced",
        "adjust_type": "hfq",
        "contract_id": contract.contract_id,
        "contract_profile": "balanced",
        "contract_variant": contract.variant,
        **specific_defaults,
    }
    assert attached["publication_identity"]["strategy_id"] == strategy_id


def test_official_replay_backfills_missing_canonical_result_config(monkeypatch):
    def run_replay(params, config):
        result = _official_result("mid_trend")
        result.pop("config")
        return result

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "mid_trend",
        SimpleNamespace(run_replay=run_replay),
    )

    attached = backtests.run_replay_backtest(
        {
            "strategy_id": "mid_trend",
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
        }
    )

    contract = get_publication_contract("mid_trend")
    assert {
        key: attached["config"][key]
        for key in contract.normalized_run_config
    } == dict(contract.normalized_run_config)


def test_official_replay_preserves_conflicting_returned_config_for_validation(monkeypatch):
    def run_replay(params, config):
        result = _official_result("mid_trend")
        result["config"] = {"max_position_weight": 0.5}
        return result

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "mid_trend",
        SimpleNamespace(run_replay=run_replay),
    )

    with pytest.raises(ValueError, match="max_position_weight"):
        backtests.run_replay_backtest(
            {
                "strategy_id": "mid_trend",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_id", "legacy:contract"),
        ("contract_profile", "legacy_profile"),
        ("contract_variant", "legacy_variant"),
    ],
)
def test_official_replay_preserves_conflicting_returned_contract_metadata(
    monkeypatch,
    field,
    value,
):
    def run_replay(params, config):
        result = _official_result("mid_trend")
        result["config"] = {field: value}
        return result

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "mid_trend",
        SimpleNamespace(run_replay=run_replay),
    )

    with pytest.raises(ValueError, match=field):
        backtests.run_replay_backtest(
            {
                "strategy_id": "mid_trend",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            }
        )


def test_official_replay_preserves_explicit_conflict_and_rejects_result(monkeypatch):
    received: dict[str, Any] = {}

    def run_replay(params, config):
        received.update(config)
        return _official_result("mid_trend")

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
                "top_n": 7,
            }
        )

    assert received == {}


@pytest.mark.parametrize(
    ("strategy_id", "field", "value"),
    [
        ("lhb_shortline", "rebalance_frequency", "weekly"),
        ("mid_trend", "benchmark_variant", "legacy_variant"),
        ("tech_bottleneck", "protection_name", "legacy_protection"),
        ("tech_bottleneck", "universe", "legacy_universe"),
    ],
)
def test_official_replay_preserves_strategy_specific_conflicts(
    monkeypatch,
    strategy_id,
    field,
    value,
):
    received: dict[str, Any] = {}

    def run_replay(params, config):
        received.update(config)
        return _official_result(strategy_id)

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        strategy_id,
        SimpleNamespace(run_replay=run_replay),
    )

    with pytest.raises(ValueError, match="official config mismatch"):
        backtests.run_replay_backtest(
            {
                "strategy_id": strategy_id,
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
                field: value,
            }
        )

    assert received == {}


def test_nonofficial_parse_ignores_official_strategy_fields():
    _strategy_id, _params, run_config, _vector_config = backtests._parse_backtest_request(
        {
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
            "rebalance_frequency": "daily",
            "benchmark_variant": "legacy_variant",
            "protection_name": "legacy_protection",
            "universe": "legacy_universe",
        }
    )

    assert run_config["rebalance_frequency"] == "weekly"
    assert "benchmark_variant" not in run_config
    assert "protection_name" not in run_config
    assert "universe" not in run_config


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


def test_registered_strategy_without_versioned_eod_evidence_fails_closed(monkeypatch):
    monkeypatch.setattr(backtests, "_latest_eod_strategy_module", lambda strategy_id: None)

    strategy = backtests._with_latest_eod_strategy_metrics(
        {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "latest_metrics": {
                "as_of_date": "2026-07-18",
                "total_return_pct": 88.8,
                "max_drawdown_pct": -12.3,
            },
        }
    )

    expected = build_publication_identity(get_publication_contract("mid_trend"))
    assert strategy["latest_metrics"] == {
        "as_of_date": "2026-07-18",
        "performance_as_of_date": "2026-07-18",
        "signal_as_of_date": "2026-07-18",
        "signal_status": "contract_mismatch",
        "signal_count": 0,
        "contract_status": "contract_mismatch",
        "contract_reason": "versioned official publication missing",
        "contract_id": expected["contract_id"],
        "identity_schema_version": expected["identity_schema_version"],
        "config_fingerprint": expected["config_fingerprint"],
        "publication_policy": expected["publication_policy"],
        "publish_id": None,
        "artifact_version": None,
        "publication_manifest_path": None,
    }


def test_publication_metadata_metrics_preserves_explicit_publish_id():
    metrics = backtests._publication_metadata_metrics(
        {
            "metadata": {
                "publish_id": "lhb-shortline-20260719",
                "artifact_version": "strategy_artifact_v1",
                "publication_manifest_path": "/ignored/identity/path/publication_manifest.json",
            }
        },
        {},
    )

    assert metrics["publish_id"] == "lhb-shortline-20260719"


def test_failed_official_eod_has_complete_fail_closed_contract_shape(monkeypatch):
    monkeypatch.setattr(
        backtests,
        "_latest_eod_strategy_module",
        lambda strategy_id: {
            "module": "strategy_tech_bottleneck",
            "status": "failed",
            "trade_date": "2026-07-18",
            "latest_trade_date": "2026-07-18",
            "error_message": "publisher failed",
        },
    )
    expected = build_publication_identity(get_publication_contract("tech_bottleneck"))

    result = backtests._with_latest_eod_strategy_metrics(
        {"strategy_id": "tech_bottleneck", "strategy_name": "Tech", "latest_metrics": {}}
    )

    assert result["latest_metrics"] == {
        "as_of_date": "2026-07-18",
        "performance_as_of_date": "2026-07-18",
        "signal_as_of_date": "2026-07-18",
        "signal_status": "contract_mismatch",
        "signal_count": 0,
        "error_message": "publisher failed",
        "contract_status": "contract_mismatch",
        "contract_reason": "official publication status failed",
        "contract_id": expected["contract_id"],
        "identity_schema_version": expected["identity_schema_version"],
        "config_fingerprint": expected["config_fingerprint"],
        "publication_policy": expected["publication_policy"],
        "publish_id": None,
        "artifact_version": None,
        "publication_manifest_path": None,
    }


def test_lhb_stale_performance_does_not_publish_latest_day_zero_return(monkeypatch):
    identity = build_publication_identity(get_publication_contract("lhb_shortline"))
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
            "trade_date": "2026-06-29",
            "latest_trade_date": "2026-06-29",
            "metadata": {
                "publication_identity": identity,
                "identity_schema_version": "strategy_publication_identity_v1",
                "artifact_version": "strategy_artifact_v1",
                "publish_id": "publish-1",
                "publication_manifest_path": (
                    "/srv/outputs/research/strategy_daily_eod/2026-06-29/strategy_runs/"
                    "lhb_shortline/publish-1/publication_manifest.json"
                ),
                "output_paths": {
                    "publication_manifest_path": (
                        "/srv/outputs/research/strategy_daily_eod/2026-06-29/strategy_runs/"
                        "lhb_shortline/publish-1/publication_manifest.json"
                    )
                },
                "summary": {
                    "total_return": 1.6241,
                    "max_drawdown": -0.0842,
                    "latest_day_return": 0.0,
                    "latest_period_return": 0.0,
                    "latest_period_label": "最近交易日",
                    "performance_effective_date": "2026-06-26",
                    "publication_identity": identity,
                    "artifact_version": "strategy_artifact_v1",
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


def test_latest_eod_metrics_fail_closed_per_strategy_for_publication_identity(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    strategies = []
    modules = {}
    for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck"):
        identity = build_publication_identity(get_publication_contract(strategy_id))
        summary = backtests.attach_publication_identity(
            _official_result(strategy_id), profile="balanced"
        )["summary"]
        summary.update(
            {
                "total_return": 0.25,
                "max_drawdown": -0.05,
                "latest_period_return": 0.02,
                "performance_effective_date": "2026-07-18",
                "artifact_version": "strategy_artifact_v1",
            }
        )
        version_dir = (
            output_root
            / "research"
            / "strategy_daily_eod"
            / "2026-07-18"
            / "strategy_runs"
            / strategy_id
            / "publish-1"
        )
        version_dir.mkdir(parents=True)
        manifest_path = version_dir / "publication_manifest.json"
        manifest_path.write_text("{}\n", encoding="utf-8")
        modules[strategy_id] = {
            "module": f"strategy_{strategy_id}",
            "status": "success",
            "trade_date": "2026-07-18",
            "latest_trade_date": "2026-07-18",
            "row_count": 5,
            "metadata": {
                "publication_identity": identity,
                "identity_schema_version": identity["identity_schema_version"],
                "artifact_version": "strategy_artifact_v1",
                "publish_id": "publish-1",
                "publication_manifest_path": str(manifest_path),
                "output_paths": {"publication_manifest_path": str(manifest_path)},
                "summary": summary,
            },
        }
        strategies.append(
            {
                "strategy_id": strategy_id,
                "strategy_name": strategy_id,
                "status": "runnable",
                "latest_metrics": {},
            }
        )
    modules["tech_bottleneck"]["metadata"]["publication_identity"] = {
        **modules["tech_bottleneck"]["metadata"]["publication_identity"],
        "config_fingerprint": "wrong",
    }

    monkeypatch.setattr(backtests, "SETTINGS", SimpleNamespace(output_root=output_root))
    monkeypatch.setattr(backtests, "list_strategy_catalog", lambda: strategies)
    monkeypatch.setattr(
        backtests, "_enrich_strategies_with_latest_db_metrics", lambda items: items
    )
    monkeypatch.setattr(
        backtests, "_latest_eod_strategy_module", lambda strategy_id: modules[strategy_id]
    )
    monkeypatch.setattr(backtests, "_read_eod_strategy_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(backtests, "_metrics_from_eod_equity_path", lambda *args, **kwargs: {})

    items = {item["strategy_id"]: item for item in backtests.list_backtest_strategies()}

    for strategy_id in ("lhb_shortline", "mid_trend"):
        metrics = items[strategy_id]["latest_metrics"]
        assert metrics["contract_status"] == "success"
        assert metrics["contract_id"] == build_publication_identity(
            get_publication_contract(strategy_id)
        )["contract_id"]
        assert metrics["artifact_version"] == "strategy_artifact_v1"
        assert metrics["publish_id"] == "publish-1"
        assert metrics["publication_manifest_path"].endswith(
            f"/strategy_runs/{strategy_id}/publish-1/publication_manifest.json"
        )
        assert metrics["total_return_pct"] == 25.0

    invalid = items["tech_bottleneck"]["latest_metrics"]
    assert invalid["contract_status"] == "contract_mismatch"
    assert invalid["signal_count"] == 0
    assert "total_return_pct" not in invalid
    assert "max_drawdown_pct" not in invalid
    assert "latest_period_return_pct" not in invalid

    missing_versioned_paths = copy.deepcopy(modules["mid_trend"])
    del missing_versioned_paths["metadata"]["output_paths"]
    assert backtests._validate_eod_publication_contract(
        "mid_trend",
        missing_versioned_paths,
        missing_versioned_paths["metadata"]["summary"],
    )[0] == "contract_mismatch"

    mixed_identity = copy.deepcopy(modules["mid_trend"])
    mixed_identity["metadata"]["config"] = {
        "publication_identity": {
            **build_publication_identity(get_publication_contract("mid_trend")),
            "contract_id": "mid_trend:balanced:legacy",
        }
    }
    assert backtests._validate_eod_publication_contract(
        "mid_trend", mixed_identity, mixed_identity["metadata"]["summary"]
    )[0] == "contract_mismatch"

    malformed_trade_date = copy.deepcopy(modules["mid_trend"])
    malformed_trade_date["trade_date"] = "2026-7-18"
    assert backtests._validate_eod_publication_contract(
        "mid_trend",
        malformed_trade_date,
        malformed_trade_date["metadata"]["summary"],
    )[0] == "contract_mismatch"

    mismatched_trade_dates = copy.deepcopy(modules["mid_trend"])
    mismatched_trade_dates["latest_trade_date"] = "2026-07-17"
    assert backtests._validate_eod_publication_contract(
        "mid_trend",
        mismatched_trade_dates,
        mismatched_trade_dates["metadata"]["summary"],
    )[0] == "contract_mismatch"

    for performance_date in ("not-a-date", "2026-07-19"):
        invalid_performance_date = copy.deepcopy(modules["mid_trend"])
        invalid_performance_date["metadata"]["summary"][
            "performance_effective_date"
        ] = performance_date
        assert backtests._validate_eod_publication_contract(
            "mid_trend",
            invalid_performance_date,
            invalid_performance_date["metadata"]["summary"],
        )[0] == "contract_mismatch"

    original_mid_trend = modules["mid_trend"]
    for label, publish_id, reason_fragment in (
        ("missing", None, "missing or invalid"),
        ("unsafe", "../publish-1", "missing or invalid"),
        ("reserved", "..", "missing or invalid"),
        ("path_mismatch", "publish-2", "does not match"),
    ):
        invalid_publish_id = copy.deepcopy(original_mid_trend)
        if publish_id is None:
            del invalid_publish_id["metadata"]["publish_id"]
        else:
            invalid_publish_id["metadata"]["publish_id"] = publish_id
        status, reason = backtests._validate_eod_publication_contract(
            "mid_trend",
            invalid_publish_id,
            invalid_publish_id["metadata"]["summary"],
        )
        assert status == "contract_mismatch", label
        assert reason_fragment in reason, label

        modules["mid_trend"] = invalid_publish_id
        failed_closed = backtests._with_latest_eod_strategy_metrics(
            {
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "latest_metrics": {},
            }
        )["latest_metrics"]
        assert failed_closed["contract_status"] == "contract_mismatch", label
        assert failed_closed["signal_count"] == 0, label
        assert failed_closed["publish_id"] is None, label
        assert "total_return_pct" not in failed_closed, label
    modules["mid_trend"] = original_mid_trend

    conflicting_publish_identity = copy.deepcopy(original_mid_trend)
    conflicting_publish_identity["metadata"]["summary"]["publish_id"] = "publish-2"
    status, reason = backtests._validate_eod_publication_contract(
        "mid_trend",
        conflicting_publish_identity,
        conflicting_publish_identity["metadata"]["summary"],
    )
    assert status == "contract_mismatch"
    assert "publish" in reason
