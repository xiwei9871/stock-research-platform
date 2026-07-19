from __future__ import annotations

from copy import deepcopy
import json
import os
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest

from stock_research.data_run_manifest import apply_data_run_manifest_schema
from stock_research.strategy_publication_contracts import (
    OFFICIAL_STRATEGY_IDS,
    build_publication_identity,
    get_publication_contract,
    iter_publication_contracts,
)
from stock_research.strategy_publication_store import (
    STRATEGY_MODULE_BY_ID,
    STRATEGY_PUBLICATION_SQLSTATE,
    apply_strategy_publication_schema,
    verify_strategy_publication_db_contracts,
)


pytestmark = pytest.mark.skipif(
    os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST") != "1"
    or not os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE"),
    reason=(
        "set STRATEGY_PUBLICATION_POSTGRES_TEST=1 and "
        "STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE to a dedicated test database"
    ),
)

TEST_SERVICE = os.getenv("STRATEGY_PUBLICATION_POSTGRES_TEST_SERVICE", "")


def _connect():
    connection = psycopg.connect(f"service={TEST_SERVICE}")
    database_name = connection.execute("SELECT current_database()").fetchone()[0]
    if not database_name.endswith("_test"):
        connection.close()
        pytest.fail(f"refusing to run integration tests against {database_name}")
    return connection


@pytest.fixture(scope="module", autouse=True)
def publication_schema():
    connection = _connect()
    connection.close()
    apply_data_run_manifest_schema(service=TEST_SERVICE)


def _manifest_values(*, module: str, metadata: dict) -> dict[str, str]:
    unique_id = uuid4().hex
    return {
        "manifest_id": f"strategy-publication-postgres-{unique_id}",
        "run_id": f"strategy-publication-postgres-{unique_id}",
        "module": module,
        "metadata": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def _insert_manifest(connection, params):
    connection.execute(
        """
        INSERT INTO ops.data_run_manifest (
            manifest_id, run_id, run_date, trade_date, module, source,
            tier, status, metadata
        ) VALUES (
            %(manifest_id)s, %(run_id)s, current_date, current_date, %(module)s,
            'strategy_daily_eod', 'tier1', 'success', %(metadata)s::jsonb
        )
        """,
        params,
    )


def _insert_contract(
    connection,
    *,
    strategy_id: str,
    module: str,
    profile: str,
    contract_id: str,
    expected_identity: dict,
):
    connection.execute(
        """
        INSERT INTO ops.strategy_publication_contract (
            strategy_id, module, profile, contract_id,
            identity_schema_version, expected_identity, acceptance_profile, active
        ) VALUES (
            %(strategy_id)s, %(module)s, %(profile)s, %(contract_id)s,
            'integration_probe_v1', %(expected_identity)s::jsonb, '{}'::jsonb, true
        )
        """,
        {
            "strategy_id": strategy_id,
            "module": module,
            "profile": profile,
            "contract_id": contract_id,
            "expected_identity": json.dumps(expected_identity, sort_keys=True),
        },
    )


def _assert_manifest_absent(manifest_id: str):
    connection = _connect()
    try:
        count = connection.execute(
            "SELECT count(*) FROM ops.data_run_manifest WHERE manifest_id = %s",
            (manifest_id,),
        ).fetchone()[0]
        assert count == 0
    finally:
        connection.rollback()
        connection.close()


def test_second_apply_is_idempotent():
    apply_strategy_publication_schema(service=TEST_SERVICE)
    apply_strategy_publication_schema(service=TEST_SERVICE)

    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT strategy_id, module, profile, contract_id, expected_identity
            FROM ops.strategy_publication_contract
            WHERE active AND strategy_id = ANY(%s)
            ORDER BY strategy_id
            """,
            (sorted(OFFICIAL_STRATEGY_IDS),),
        ).fetchall()
        assert len(rows) == len(iter_publication_contracts())
        for strategy_id, module, profile, contract_id, expected_identity in rows:
            contract = get_publication_contract(strategy_id, profile)
            assert module == STRATEGY_MODULE_BY_ID[strategy_id]
            assert contract_id == contract.contract_id
            assert expected_identity == build_publication_identity(contract)
    finally:
        connection.rollback()
        connection.close()


def test_verify_helper_probes_contracts_without_persisting_synthetic_rows():
    connection = _connect()
    try:
        before = connection.execute(
            """
            SELECT count(*)
            FROM ops.data_run_manifest
            WHERE run_id LIKE 'strategy-publication-contract-verify-%'
            """
        ).fetchone()[0]
    finally:
        connection.rollback()
        connection.close()

    assert before == 0
    assert verify_strategy_publication_db_contracts(service=TEST_SERVICE) == {
        f"{contract.strategy_id}:{contract.profile}": {
            "valid": "accepted",
            "invalid": "rejected",
        }
        for contract in iter_publication_contracts()
    }

    connection = _connect()
    try:
        after = connection.execute(
            """
            SELECT count(*)
            FROM ops.data_run_manifest
            WHERE run_id LIKE 'strategy-publication-contract-verify-%'
            """
        ).fetchone()[0]
        assert after == 0
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.parametrize(
    "contract",
    iter_publication_contracts(),
    ids=lambda contract: f"{contract.strategy_id}-{contract.profile}",
)
def test_valid_identity_is_accepted_inside_rollback(contract):
    strategy_id = contract.strategy_id
    identity = build_publication_identity(contract)
    params = _manifest_values(
        module=STRATEGY_MODULE_BY_ID[strategy_id],
        metadata={"publication_identity": identity},
    )
    connection = _connect()
    try:
        _insert_manifest(connection, params)
        assert connection.execute(
            "SELECT count(*) FROM ops.data_run_manifest WHERE manifest_id = %s",
            (params["manifest_id"],),
        ).fetchone()[0] == 1
    finally:
        connection.rollback()
        connection.close()

    _assert_manifest_absent(params["manifest_id"])


@pytest.mark.parametrize(
    "contract",
    iter_publication_contracts(),
    ids=lambda contract: f"{contract.strategy_id}-{contract.profile}",
)
@pytest.mark.parametrize("invalid_kind", ["missing", "stale", "nested_mismatch"])
def test_invalid_identity_is_rejected_and_does_not_persist(contract, invalid_kind):
    strategy_id = contract.strategy_id
    identity = build_publication_identity(contract)
    if invalid_kind == "missing":
        metadata = {}
        expected_message = "identity missing"
    elif invalid_kind == "stale":
        identity["contract_id"] = f"{identity['contract_id']}:stale"
        metadata = {"publication_identity": identity}
        expected_message = "stale strategy publication contract"
    else:
        identity = deepcopy(identity)
        identity["publication_policy"]["integration_probe"] = "altered"
        metadata = {"publication_identity": identity}
        expected_message = "identity mismatch"

    params = _manifest_values(
        module=STRATEGY_MODULE_BY_ID[strategy_id],
        metadata=metadata,
    )
    connection = _connect()
    try:
        with pytest.raises(psycopg.Error, match=expected_message) as exc_info:
            _insert_manifest(connection, params)
        assert exc_info.value.sqlstate == STRATEGY_PUBLICATION_SQLSTATE
    finally:
        connection.rollback()
        connection.close()

    _assert_manifest_absent(params["manifest_id"])


def test_unregistered_strategy_module_is_rejected_and_does_not_persist():
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    params = _manifest_values(
        module="strategy_unregistered_contract_probe",
        metadata={"publication_identity": identity},
    )
    connection = _connect()
    try:
        with pytest.raises(
            psycopg.Error,
            match="unregistered strategy publication module",
        ) as exc_info:
            _insert_manifest(connection, params)
        assert exc_info.value.sqlstate == STRATEGY_PUBLICATION_SQLSTATE
    finally:
        connection.rollback()
        connection.close()

    _assert_manifest_absent(params["manifest_id"])


def test_apply_retires_removed_tuple_sharing_current_contract_id_and_blocks_publication():
    strategy_id = "retired_contract_probe"
    module = "strategy_retired_contract_probe"
    profile = "integration"
    contract_id = get_publication_contract("mid_trend").contract_id
    identity = {
        "strategy_id": strategy_id,
        "contract_id": contract_id,
        "publication_policy": {"version": "retired"},
    }
    connection = _connect()
    try:
        connection.execute(
            "DELETE FROM ops.strategy_publication_contract WHERE strategy_id = %s",
            (strategy_id,),
        )
        _insert_contract(
            connection,
            strategy_id=strategy_id,
            module=module,
            profile=profile,
            contract_id=contract_id,
            expected_identity=identity,
        )
        connection.commit()
    finally:
        connection.close()

    before_params = _manifest_values(
        module=module,
        metadata={"publication_identity": identity},
    )
    connection = _connect()
    try:
        _insert_manifest(connection, before_params)
    finally:
        connection.rollback()
        connection.close()

    apply_strategy_publication_schema(service=TEST_SERVICE)

    after_params = _manifest_values(
        module=module,
        metadata={"publication_identity": identity},
    )
    connection = _connect()
    try:
        assert connection.execute(
            """
            SELECT active
            FROM ops.strategy_publication_contract
            WHERE strategy_id = %s AND profile = %s AND contract_id = %s
            """,
            (strategy_id, profile, contract_id),
        ).fetchone() == (False,)
        with pytest.raises(
            psycopg.Error,
            match="unregistered strategy publication module",
        ) as exc_info:
            _insert_manifest(connection, after_params)
        assert exc_info.value.sqlstate == STRATEGY_PUBLICATION_SQLSTATE
    finally:
        connection.rollback()
        connection.close()

    connection = _connect()
    try:
        connection.execute(
            "DELETE FROM ops.strategy_publication_contract WHERE strategy_id = %s",
            (strategy_id,),
        )
        connection.commit()
    finally:
        connection.close()


def test_publication_lock_serializes_promotion_and_rejects_stale_identity_afterward():
    strategy_id = "serialization_contract_probe"
    module = "strategy_serialization_contract_probe"
    profile = "integration"
    old_contract_id = "serialization_contract_probe:integration:old"
    new_contract_id = "serialization_contract_probe:integration:new"
    old_identity = {
        "strategy_id": strategy_id,
        "contract_id": old_contract_id,
        "publication_policy": {"version": "old"},
    }
    new_identity = {
        "strategy_id": strategy_id,
        "contract_id": new_contract_id,
        "publication_policy": {"version": "new"},
    }
    setup = _connect()
    try:
        setup.execute("DELETE FROM ops.data_run_manifest WHERE module = %s", (module,))
        setup.execute(
            "DELETE FROM ops.strategy_publication_contract WHERE strategy_id = %s",
            (strategy_id,),
        )
        _insert_contract(
            setup,
            strategy_id=strategy_id,
            module=module,
            profile=profile,
            contract_id=old_contract_id,
            expected_identity=old_identity,
        )
        setup.commit()
    finally:
        setup.close()

    publication_connection = _connect()
    publication_params = _manifest_values(
        module=module,
        metadata={"publication_identity": old_identity},
    )
    _insert_manifest(publication_connection, publication_params)

    promotion_started = Event()
    promotion_done = Event()
    promotion_errors = []
    promotion_application_name = f"strategy-publication-promotion-{uuid4().hex}"

    def promote_contract():
        connection = _connect()
        try:
            connection.execute(
                "SELECT set_config('application_name', %s, false)",
                (promotion_application_name,),
            )
            promotion_started.set()
            connection.execute(
                """
                UPDATE ops.strategy_publication_contract
                SET active = false, updated_at = now()
                WHERE strategy_id = %s AND profile = %s AND contract_id = %s AND active
                """,
                (strategy_id, profile, old_contract_id),
            )
            _insert_contract(
                connection,
                strategy_id=strategy_id,
                module=module,
                profile=profile,
                contract_id=new_contract_id,
                expected_identity=new_identity,
            )
            connection.commit()
        except Exception as exc:
            promotion_errors.append(exc)
            connection.rollback()
        finally:
            connection.close()
            promotion_done.set()

    promotion_thread = Thread(target=promote_contract, daemon=True)
    promotion_thread.start()
    promotion_started_in_time = promotion_started.wait(timeout=5)
    observer = _connect()
    try:
        deadline = monotonic() + 5
        promotion_waited_on_lock = False
        while monotonic() < deadline:
            wait_event = observer.execute(
                """
                SELECT wait_event_type
                FROM pg_stat_activity
                WHERE application_name = %s
                """,
                (promotion_application_name,),
            ).fetchone()
            if wait_event == ("Lock",):
                promotion_waited_on_lock = True
                break
            sleep(0.05)
    finally:
        observer.rollback()
        observer.close()

    publication_connection.commit()
    publication_connection.close()
    promotion_finished_in_time = promotion_done.wait(timeout=5)
    promotion_thread.join(timeout=5)
    assert promotion_started_in_time
    assert promotion_waited_on_lock
    assert promotion_finished_in_time
    assert promotion_errors == []

    stale_params = _manifest_values(
        module=module,
        metadata={"publication_identity": old_identity},
    )
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT contract_id, active
            FROM ops.strategy_publication_contract
            WHERE strategy_id = %s
            ORDER BY contract_id
            """,
            (strategy_id,),
        ).fetchall()
        assert rows == [(new_contract_id, True), (old_contract_id, False)]
        with pytest.raises(psycopg.Error, match="stale strategy publication contract") as exc_info:
            _insert_manifest(connection, stale_params)
        assert exc_info.value.sqlstate == STRATEGY_PUBLICATION_SQLSTATE
    finally:
        connection.rollback()
        connection.close()

    cleanup = _connect()
    try:
        cleanup.execute("DELETE FROM ops.data_run_manifest WHERE module = %s", (module,))
        cleanup.execute(
            "DELETE FROM ops.strategy_publication_contract WHERE strategy_id = %s",
            (strategy_id,),
        )
        cleanup.commit()
    finally:
        cleanup.close()
