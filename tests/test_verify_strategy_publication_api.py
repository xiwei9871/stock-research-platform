import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from stock_research.strategy_publication_artifacts import ARTIFACT_VERSION
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_strategy_publication_api.py"
SPEC = importlib.util.spec_from_file_location("verify_strategy_publication_api", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _valid_item(strategy_id: str) -> dict:
    identity = build_publication_identity(get_publication_contract(strategy_id))
    return {
        "strategy_id": strategy_id,
        "status": "runnable",
        "latest_metrics": {
            "contract_status": "success",
            "contract_id": identity["contract_id"],
            "identity_schema_version": identity["identity_schema_version"],
            "config_fingerprint": identity["config_fingerprint"],
            "publication_policy": identity["publication_policy"],
            "artifact_version": ARTIFACT_VERSION,
            "publication_manifest_path": (
                f"/srv/outputs/strategy_daily_eod/2026-07-18/strategy_runs/"
                f"{strategy_id}/publish-1/publication_manifest.json"
            ),
            "performance_as_of_date": "2026-07-18",
            "total_return_pct": 12.3,
        },
    }


def _payload() -> dict:
    return {
        "items": [
            _valid_item("lhb_shortline"),
            _valid_item("mid_trend"),
            _valid_item("tech_bottleneck"),
        ]
    }


def test_verify_payload_accepts_every_registered_runnable_strategy():
    result = MODULE.verify_payload(_payload())

    assert result == {
        "status": "success",
        "checked": ["lhb_shortline", "mid_trend", "tech_bottleneck"],
        "failures": [],
    }


def test_verify_payload_isolates_one_contract_mismatch():
    payload = _payload()
    payload["items"][2]["latest_metrics"]["contract_status"] = "contract_mismatch"

    result = MODULE.verify_payload(payload)

    assert result["status"] == "failed"
    assert result["failures"] == ["tech_bottleneck: contract_mismatch"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["items"][1]["latest_metrics"].pop("config_fingerprint"),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {"config_fingerprint": "wrong"}
        ),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {"publication_policy": {"unexpected": True}}
        ),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {"artifact_version": "strategy_artifact_v999"}
        ),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {"performance_as_of_date": ""}
        ),
        lambda payload: payload["items"][1].update({"status": "replay_only"}),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {
                "publication_manifest_path": (
                    "/srv/outputs/strategy_runs/lhb_shortline/publish-1/"
                    "publication_manifest.json"
                )
            }
        ),
        lambda payload: payload["items"][1]["latest_metrics"].update(
            {
                "publication_manifest_path": (
                    "/srv/outputs/strategy_runs/mid_trend/../tech_bottleneck/"
                    "publication_manifest.json"
                )
            }
        ),
    ],
)
def test_verify_payload_fails_closed_for_malformed_or_mixed_evidence(mutate):
    payload = _payload()
    mutate(payload)

    result = MODULE.verify_payload(payload)

    assert result["failures"] == ["mid_trend: contract_mismatch"]


def test_verify_payload_rejects_missing_and_duplicate_registered_items():
    missing = _payload()
    missing["items"] = missing["items"][:-1]
    duplicate = deepcopy(_payload())
    duplicate["items"].append(deepcopy(duplicate["items"][0]))

    assert MODULE.verify_payload(missing)["failures"] == [
        "tech_bottleneck: contract_mismatch"
    ]
    assert MODULE.verify_payload(duplicate)["failures"] == [
        "lhb_shortline: contract_mismatch"
    ]
