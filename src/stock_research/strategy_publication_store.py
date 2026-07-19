"""PostgreSQL persistence and enforcement for strategy publication contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from types import MappingProxyType
from typing import Any
from uuid import uuid4

import psycopg

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    iter_publication_contracts,
)


STRATEGY_MODULE_BY_ID = MappingProxyType(
    {
        "lhb_shortline": "strategy_lhb_shortline",
        "mid_trend": "strategy_mid_trend",
        "tech_bottleneck": "strategy_tech_bottleneck",
    }
)

STRATEGY_PUBLICATION_SQLSTATE = "P5100"


CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL = fr"""
CREATE TABLE IF NOT EXISTS ops.strategy_publication_contract (
    strategy_id text NOT NULL,
    module text NOT NULL,
    profile text NOT NULL,
    contract_id text NOT NULL,
    identity_schema_version text NOT NULL,
    expected_identity jsonb NOT NULL,
    acceptance_profile jsonb NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_strategy_publication_contract
        PRIMARY KEY (strategy_id, profile, contract_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_publication_contract_active_strategy_profile
    ON ops.strategy_publication_contract (strategy_id, profile)
    WHERE active;

CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_publication_contract_active_module_contract
    ON ops.strategy_publication_contract (module, contract_id)
    WHERE active;

CREATE INDEX IF NOT EXISTS idx_strategy_publication_contract_module_lookup
    ON ops.strategy_publication_contract (module, contract_id, strategy_id, profile)
    WHERE active;

CREATE OR REPLACE FUNCTION ops.enforce_strategy_publication_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_identity jsonb;
    actual_contract_id text;
    actual_strategy_id text;
    matched_contract ops.strategy_publication_contract%ROWTYPE;
BEGIN
    IF NOT (
        NEW.status = 'success'
        AND NEW.source = 'strategy_daily_eod'
    ) THEN
        RETURN NEW;
    END IF;

    IF NOT (NEW.module LIKE 'strategy\_%' ESCAPE '\') THEN
        RETURN NEW;
    END IF;

    actual_identity := NEW.metadata -> 'publication_identity';
    IF actual_identity IS NULL OR jsonb_typeof(actual_identity) <> 'object' THEN
        RAISE EXCEPTION USING
            ERRCODE = '{STRATEGY_PUBLICATION_SQLSTATE}',
            MESSAGE = format(
                'strategy publication identity missing or not an object for module %s',
                NEW.module
            );
    END IF;

    actual_contract_id := NULLIF(actual_identity ->> 'contract_id', '');
    actual_strategy_id := NULLIF(actual_identity ->> 'strategy_id', '');
    IF actual_contract_id IS NULL OR actual_strategy_id IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '{STRATEGY_PUBLICATION_SQLSTATE}',
            MESSAGE = format(
                'strategy publication identity missing contract_id or strategy_id for module %s',
                NEW.module
            );
    END IF;

    SELECT contract.*
    INTO matched_contract
    FROM ops.strategy_publication_contract AS contract
    WHERE contract.active
      AND contract.module = NEW.module
      AND contract.contract_id = actual_contract_id
      AND contract.strategy_id = actual_strategy_id
    FOR SHARE;

    IF NOT FOUND THEN
        IF NOT EXISTS (
            SELECT 1
            FROM ops.strategy_publication_contract AS contract
            WHERE contract.active AND contract.module = NEW.module
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '{STRATEGY_PUBLICATION_SQLSTATE}',
                MESSAGE = format(
                    'unregistered strategy publication module: %s',
                    NEW.module
                );
        END IF;
        RAISE EXCEPTION USING
            ERRCODE = '{STRATEGY_PUBLICATION_SQLSTATE}',
            MESSAGE = format(
                'stale strategy publication contract for module %s, strategy_id %s, contract_id %s',
                NEW.module, actual_strategy_id, actual_contract_id
            );
    END IF;

    IF actual_identity IS DISTINCT FROM matched_contract.expected_identity THEN
        RAISE EXCEPTION USING
            ERRCODE = '{STRATEGY_PUBLICATION_SQLSTATE}',
            MESSAGE = format(
                'strategy publication identity mismatch for module %s, profile %s, contract_id %s',
                NEW.module, matched_contract.profile, matched_contract.contract_id
            );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_strategy_publication_contract
    ON ops.data_run_manifest;

CREATE TRIGGER trg_enforce_strategy_publication_contract
BEFORE INSERT OR UPDATE ON ops.data_run_manifest
FOR EACH ROW
EXECUTE FUNCTION ops.enforce_strategy_publication_contract();
"""


DEACTIVATE_SUPERSEDED_STRATEGY_PUBLICATION_SQL = """
UPDATE ops.strategy_publication_contract
SET active = false,
    updated_at = now()
WHERE strategy_id = %(strategy_id)s
  AND profile = %(profile)s
  AND contract_id <> %(contract_id)s
  AND active
"""


LOCK_ACTIVE_STRATEGY_PUBLICATION_CONTRACTS_SQL = """
SELECT strategy_id, profile, contract_id
FROM ops.strategy_publication_contract
WHERE active
ORDER BY strategy_id, profile, contract_id
FOR UPDATE
"""


RETIRE_ABSENT_STRATEGY_PUBLICATION_CONTRACTS_SQL = """
UPDATE ops.strategy_publication_contract
SET active = false,
    updated_at = now()
WHERE active
  AND NOT (contract_id = ANY(%(current_contract_ids)s::text[]))
"""


UPSERT_STRATEGY_PUBLICATION_CONTRACT_SQL = """
INSERT INTO ops.strategy_publication_contract (
    strategy_id,
    module,
    profile,
    contract_id,
    identity_schema_version,
    expected_identity,
    acceptance_profile,
    active
)
VALUES (
    %(strategy_id)s,
    %(module)s,
    %(profile)s,
    %(contract_id)s,
    %(identity_schema_version)s,
    %(expected_identity)s::jsonb,
    %(acceptance_profile)s::jsonb,
    true
)
ON CONFLICT (strategy_id, profile, contract_id)
DO UPDATE SET
    module = EXCLUDED.module,
    identity_schema_version = EXCLUDED.identity_schema_version,
    expected_identity = EXCLUDED.expected_identity,
    acceptance_profile = EXCLUDED.acceptance_profile,
    active = true,
    updated_at = now()
"""


VERIFY_STRATEGY_PUBLICATION_MANIFEST_SQL = """
INSERT INTO ops.data_run_manifest (
    manifest_id,
    run_id,
    run_date,
    trade_date,
    module,
    source,
    tier,
    status,
    metadata
)
VALUES (
    %(manifest_id)s,
    %(run_id)s,
    %(run_date)s,
    %(trade_date)s,
    %(module)s,
    'strategy_daily_eod',
    'tier1',
    'success',
    %(metadata)s::jsonb
)
"""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def build_strategy_publication_seed_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for contract in iter_publication_contracts():
        strategy_id = contract.strategy_id
        rows.append(
            {
                "strategy_id": strategy_id,
                "module": STRATEGY_MODULE_BY_ID[strategy_id],
                "profile": contract.profile,
                "contract_id": contract.contract_id,
                "identity_schema_version": contract.identity_schema_version,
                "expected_identity": _canonical_json(build_publication_identity(contract)),
                "acceptance_profile": _canonical_json(
                    {"name": contract.acceptance_profile}
                ),
            }
        )
    return rows


def apply_strategy_publication_schema(
    service: str = SETTINGS.research_service,
) -> None:
    """Install the generic gate and seed the repository publication contracts."""

    with connect(service) as conn:
        with conn.cursor() as cur:
            install_strategy_publication_schema(cur)


def install_strategy_publication_schema(cursor: Any) -> None:
    """Install and synchronize publication contracts on the caller transaction."""

    seed_rows = build_strategy_publication_seed_rows()
    cursor.execute(CREATE_STRATEGY_PUBLICATION_SCHEMA_SQL)
    cursor.execute(LOCK_ACTIVE_STRATEGY_PUBLICATION_CONTRACTS_SQL)
    cursor.execute(
        RETIRE_ABSENT_STRATEGY_PUBLICATION_CONTRACTS_SQL,
        {
            "current_contract_ids": [
                params["contract_id"] for params in seed_rows
            ]
        },
    )
    for params in seed_rows:
        cursor.execute(DEACTIVATE_SUPERSEDED_STRATEGY_PUBLICATION_SQL, params)
        cursor.execute(UPSERT_STRATEGY_PUBLICATION_CONTRACT_SQL, params)


def verify_strategy_publication_db_contracts(
    service: str = SETTINGS.research_service,
) -> dict[str, dict[str, str]]:
    """Probe each database contract and roll back every synthetic manifest."""

    results: dict[str, dict[str, str]] = {}
    with connect(service) as conn:
        try:
            with conn.cursor() as cur:
                for contract in iter_publication_contracts():
                    strategy_id = contract.strategy_id
                    result_key = f"{strategy_id}:{contract.profile}"
                    expected_identity = build_publication_identity(contract)
                    valid_params = _verification_manifest_params(
                        strategy_id=strategy_id,
                        identity=expected_identity,
                    )
                    try:
                        cur.execute(VERIFY_STRATEGY_PUBLICATION_MANIFEST_SQL, valid_params)
                    except Exception as exc:
                        raise RuntimeError(
                            "valid strategy publication manifest rejected: "
                            f"{strategy_id}/{contract.profile}"
                        ) from exc

                    invalid_identity = deepcopy(expected_identity)
                    invalid_identity.setdefault("publication_policy", {})[
                        "_db_contract_probe_invalid"
                    ] = True
                    invalid_params = _verification_manifest_params(
                        strategy_id=strategy_id,
                        identity=invalid_identity,
                    )
                    cur.execute("SAVEPOINT strategy_publication_invalid")
                    try:
                        cur.execute(
                            VERIFY_STRATEGY_PUBLICATION_MANIFEST_SQL,
                            invalid_params,
                        )
                    except Exception as exc:
                        cur.execute("ROLLBACK TO SAVEPOINT strategy_publication_invalid")
                        cur.execute("RELEASE SAVEPOINT strategy_publication_invalid")
                        if not (
                            isinstance(exc, psycopg.Error)
                            and exc.sqlstate == STRATEGY_PUBLICATION_SQLSTATE
                        ):
                            raise RuntimeError(
                                "invalid strategy publication probe failed unexpectedly: "
                                f"{strategy_id}/{contract.profile}"
                            ) from exc
                    else:
                        cur.execute("ROLLBACK TO SAVEPOINT strategy_publication_invalid")
                        cur.execute("RELEASE SAVEPOINT strategy_publication_invalid")
                        raise RuntimeError(
                            "invalid strategy publication manifest unexpectedly accepted: "
                            f"{strategy_id}/{contract.profile}"
                        )
                    results[result_key] = {
                        "valid": "accepted",
                        "invalid": "rejected",
                    }
        finally:
            conn.rollback()
    return results


def _verification_manifest_params(
    *,
    strategy_id: str,
    identity: dict[str, Any],
) -> dict[str, str]:
    unique_id = uuid4().hex
    run_id = f"strategy-publication-contract-verify-{unique_id}"
    return {
        "manifest_id": f"{run_id}:{strategy_id}",
        "run_id": run_id,
        "run_date": date.today().isoformat(),
        "trade_date": date.today().isoformat(),
        "module": STRATEGY_MODULE_BY_ID[strategy_id],
        "metadata": _canonical_json({"publication_identity": identity}),
    }
