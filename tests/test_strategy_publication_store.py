from __future__ import annotations

from dataclasses import replace
import json

import psycopg
import pytest

from stock_research import strategy_publication_store as store
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
)


EXPECTED_MODULES = {
    "lhb_shortline": "strategy_lhb_shortline",
    "mid_trend": "strategy_mid_trend",
    "tech_bottleneck": "strategy_tech_bottleneck",
}


class RecordingCursor:
    def __init__(
        self,
        *,
        reject_invalid_manifests: bool = False,
        reject_all_manifests: bool = False,
        invalid_error_message: str = "strategy publication identity mismatch",
        invalid_sqlstate: str | None = "P5100",
        invalid_is_database_error: bool = True,
    ):
        self.calls = []
        self.reject_invalid_manifests = reject_invalid_manifests
        self.reject_all_manifests = reject_all_manifests
        self.invalid_error_message = invalid_error_message
        self.invalid_sqlstate = invalid_sqlstate
        self.invalid_is_database_error = invalid_is_database_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "INSERT INTO ops.data_run_manifest" not in sql:
            return
        if self.reject_all_manifests:
            raise RuntimeError("valid manifest rejected")
        if self.reject_invalid_manifests:
            metadata = json.loads(params["metadata"])
            identity = metadata.get("publication_identity")
            expected_by_contract_id = {
                contract.contract_id: build_publication_identity(contract)
                for contract in store.iter_publication_contracts()
            }
            expected = expected_by_contract_id.get((identity or {}).get("contract_id"))
            if identity != expected:
                if not self.invalid_is_database_error:
                    raise RuntimeError(self.invalid_error_message)
                error = psycopg.Error(self.invalid_error_message)
                error.sqlstate = self.invalid_sqlstate
                raise error


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.rollback_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rollback_calls += 1


def test_schema_sql_is_generic_and_installs_table_indexes_function_and_trigger():
    sql = store.CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL
    normalized = " ".join(sql.lower().split())

    assert "create table if not exists ops.strategy_publication_contract" in normalized
    assert "primary key" in normalized
    assert "where active" in normalized
    assert "create or replace function ops.enforce_strategy_publication_contract" in normalized
    assert "before insert or update" in normalized
    assert "on ops.data_run_manifest" in normalized
    assert "new.source = 'strategy_daily_eod'" in normalized
    assert "new.status = 'success'" in normalized
    assert "new.module like 'strategy" in normalized
    assert "actual_identity is distinct from matched_contract.expected_identity" in normalized
    assert store.STRATEGY_PUBLICATION_SQLSTATE == "P5100"
    assert normalized.count("errcode = 'p5100'") == 5

    forbidden_policy_values = {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "lhb_shortline_v1",
        "mid_trend_v1",
        "tech_bottleneck_v1",
        "phase18c_top5_then_eligibility_no_refill",
        "strict_153_st_only_financial_state",
    }
    assert not forbidden_policy_values.intersection(normalized)


def test_seed_rows_cover_every_official_contract_with_exact_identity_and_module():
    rows = store.build_strategy_publication_seed_rows()

    assert len(rows) == len(store.iter_publication_contracts())
    assert {(row["strategy_id"], row["profile"]) for row in rows} == {
        (contract.strategy_id, contract.profile)
        for contract in store.iter_publication_contracts()
    }
    for row in rows:
        contract = get_publication_contract(row["strategy_id"], row["profile"])
        assert row["module"] == EXPECTED_MODULES[row["strategy_id"]]
        assert json.loads(row["expected_identity"]) == build_publication_identity(contract)
        assert row["contract_id"] == contract.contract_id
        assert row["identity_schema_version"] == contract.identity_schema_version
        assert json.loads(row["acceptance_profile"]) == {"name": contract.acceptance_profile}
        assert row["expected_identity"] == json.dumps(
            build_publication_identity(contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def test_apply_schema_and_seed_is_idempotent_with_one_transaction(monkeypatch):
    cursor = RecordingCursor()
    connections = []

    def fake_connect(service):
        assert service == "publication-test"
        connection = RecordingConnection(cursor)
        connections.append(connection)
        return connection

    monkeypatch.setattr(store, "connect", fake_connect)

    store.apply_strategy_publication_schema(service="publication-test")
    first_calls = list(cursor.calls)
    store.apply_strategy_publication_schema(service="publication-test")
    second_calls = cursor.calls[len(first_calls) :]

    assert len(connections) == 2
    assert first_calls == second_calls
    assert first_calls[0] == (store.CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL, None)
    assert len(first_calls) == 1 + 2 * len(store.iter_publication_contracts())
    for offset in range(1, len(first_calls), 2):
        deactivate_sql, deactivate_params = first_calls[offset]
        upsert_sql, upsert_params = first_calls[offset + 1]
        assert deactivate_sql == store.DEACTIVATE_SUPERSEDED_STRATEGY_PUBLICATION_SQL
        assert upsert_sql == store.UPSERT_STRATEGY_PUBLICATION_CONTRACT_SQL
        assert deactivate_params is upsert_params


def test_verify_contracts_accepts_valid_rejects_invalid_and_always_rolls_back(monkeypatch):
    cursor = RecordingCursor(reject_invalid_manifests=True)
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(store, "connect", lambda service: connection)

    result = store.verify_strategy_publication_db_contracts(service="publication-test")

    assert result == {
        f"{contract.strategy_id}:{contract.profile}": {
            "valid": "accepted",
            "invalid": "rejected",
        }
        for contract in store.iter_publication_contracts()
    }
    assert connection.rollback_calls == 1
    manifest_calls = [
        params
        for sql, params in cursor.calls
        if "INSERT INTO ops.data_run_manifest" in sql
    ]
    assert len(manifest_calls) == 2 * len(store.iter_publication_contracts())
    assert len({params["manifest_id"] for params in manifest_calls}) == len(manifest_calls)
    assert any("ROLLBACK TO SAVEPOINT" in sql for sql, _params in cursor.calls)


def test_verify_contracts_rolls_back_when_valid_manifest_is_unexpectedly_rejected(monkeypatch):
    cursor = RecordingCursor(reject_all_manifests=True)
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(store, "connect", lambda service: connection)

    with pytest.raises(RuntimeError, match="valid strategy publication manifest rejected"):
        store.verify_strategy_publication_db_contracts(service="publication-test")

    assert connection.rollback_calls == 1


def test_verify_contracts_raises_when_invalid_write_fails_for_an_unexpected_reason(monkeypatch):
    cursor = RecordingCursor(
        reject_invalid_manifests=True,
        invalid_error_message="strategy publication identity mismatch",
        invalid_is_database_error=False,
    )
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(store, "connect", lambda service: connection)

    with pytest.raises(RuntimeError, match="invalid strategy publication probe failed unexpectedly"):
        store.verify_strategy_publication_db_contracts(service="publication-test")

    assert connection.rollback_calls == 1


@pytest.mark.parametrize("sqlstate", [None, "P5101"])
def test_verify_contracts_rejects_matching_message_with_wrong_or_missing_sqlstate(
    monkeypatch,
    sqlstate,
):
    cursor = RecordingCursor(
        reject_invalid_manifests=True,
        invalid_error_message="strategy publication identity mismatch",
        invalid_sqlstate=sqlstate,
    )
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(store, "connect", lambda service: connection)

    with pytest.raises(RuntimeError, match="invalid strategy publication probe failed unexpectedly"):
        store.verify_strategy_publication_db_contracts(service="publication-test")

    assert connection.rollback_calls == 1


def test_seed_and_verify_iterate_every_profile_for_a_strategy(monkeypatch):
    balanced = get_publication_contract("mid_trend")
    second_profile = replace(
        balanced,
        profile="growth",
        contract_id=f"mid_trend:growth:{balanced.variant}",
    )
    contracts = (*store.iter_publication_contracts(), second_profile)
    contracts = tuple(sorted(contracts, key=lambda item: (item.strategy_id, item.profile)))
    monkeypatch.setattr(store, "iter_publication_contracts", lambda: contracts)

    rows = store.build_strategy_publication_seed_rows()
    mid_rows = [row for row in rows if row["strategy_id"] == "mid_trend"]
    assert [(row["strategy_id"], row["profile"]) for row in mid_rows] == [
        ("mid_trend", "balanced"),
        ("mid_trend", "growth"),
    ]
    assert json.loads(mid_rows[1]["expected_identity"]) == build_publication_identity(
        second_profile
    )

    seed_cursor = RecordingCursor()
    seed_connection = RecordingConnection(seed_cursor)
    monkeypatch.setattr(store, "connect", lambda service: seed_connection)
    store.apply_strategy_publication_schema(service="publication-test")
    seeded_mid_profiles = [
        params["profile"]
        for sql, params in seed_cursor.calls
        if sql == store.UPSERT_STRATEGY_PUBLICATION_CONTRACT_SQL
        and params["strategy_id"] == "mid_trend"
    ]
    assert seeded_mid_profiles == ["balanced", "growth"]

    cursor = RecordingCursor(reject_invalid_manifests=True)
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(store, "connect", lambda service: connection)

    result = store.verify_strategy_publication_db_contracts(service="publication-test")

    assert result["mid_trend:balanced"] == {
        "valid": "accepted",
        "invalid": "rejected",
    }
    assert result["mid_trend:growth"] == {
        "valid": "accepted",
        "invalid": "rejected",
    }
    assert len(result) == len(contracts)
