from __future__ import annotations

import importlib
import json


def test_default_strategy_contract_path_uses_configured_output_root(monkeypatch, tmp_path):
    output_root = tmp_path / "outputs"
    contract_path = (
        output_root
        / "research"
        / "official_strategy_contract_rescan_20260101_20260617_fresh_all"
        / "official_strategy_contracts.json"
    )
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "selected_profile": "balanced",
                        "strategy_id": "tech_bottleneck",
                        "engine": "tech_bottleneck_v1",
                        "variant": "strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
                        "top_n": 5,
                        "transaction_cost_bps": 20,
                        "adjust_type": "hfq",
                        "frequency": "biweekly",
                        "protection_name": "rank_exit_top10_1d",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STOCK_RESEARCH_OUTPUT_ROOT", str(output_root))
    import stock_research.config as config
    import stock_research.strategy_contracts as strategy_contracts

    importlib.reload(config)
    strategy_contracts = importlib.reload(strategy_contracts)

    try:
        assert strategy_contracts.DEFAULT_STRATEGY_CONTRACT_PATH == contract_path
        contracts = strategy_contracts.load_strategy_contracts(profile="balanced")
        assert contracts["tech_bottleneck"].frequency == "biweekly"
    finally:
        monkeypatch.delenv("STOCK_RESEARCH_OUTPUT_ROOT", raising=False)
        importlib.reload(config)
        importlib.reload(strategy_contracts)
