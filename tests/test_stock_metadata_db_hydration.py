from __future__ import annotations

import pandas as pd

from stock_research import stock_metadata_db_hydration as hydration


def test_build_stock_metadata_read_model_prefers_db_industry_and_concepts() -> None:
    assets = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000551", "stock_code": "000551", "stock_name": "创元科技"},
            {"asset_id": "000657.SZ", "stock_code": "000657", "stock_name": "中钨高新"},
        ]
    )
    industries = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000551",
                "industry_system": "csrc",
                "industry_name": "专用设备制造业",
                "source": "baostock",
            },
            {
                "asset_id": "000657.SZ",
                "industry_system": "csrc",
                "industry_name": "有色金属冶炼和压延加工业",
                "source": "baostock",
            },
        ]
    )
    concepts = pd.DataFrame(
        [
            {
                "asset_id": "000551.SZ",
                "concept_system": "ths",
                "concept_name": "机器人概念",
                "source": "akshare:concept_constituents",
            },
            {
                "asset_id": "000551.SZ",
                "concept_system": "ths",
                "concept_name": "高端装备",
                "source": "akshare:concept_constituents",
            },
        ]
    )

    model = hydration.build_stock_metadata_read_model(assets=assets, industries=industries, concepts=concepts)

    assert model.loc[model["stock_code"] == "000551", "industry"].item() == "专用设备制造业"
    assert model.loc[model["stock_code"] == "000551", "concept_tags"].item() == "机器人概念 / 高端装备"
    assert model.loc[model["stock_code"] == "000551", "industry_source"].item() == "baostock"
    assert model.loc[model["stock_code"] == "000551", "concept_source"].item() == "akshare:concept_constituents"
    assert model.loc[model["stock_code"] == "000657", "concept_tags"].item() == "no_concept_mapping_found"
    assert model.loc[model["stock_code"] == "000657", "concept_mapping_status"].item() == "missing_concept_mapping"


def test_coverage_audit_counts_missing_industry_and_concepts() -> None:
    model = pd.DataFrame(
        [
            {"stock_code": "000551", "industry": "专用设备制造业", "concept_tags": "机器人概念"},
            {"stock_code": "000657", "industry": "", "concept_tags": "no_concept_mapping_found"},
        ]
    )

    audit = hydration.build_stock_metadata_coverage_audit(model)

    assert audit["total_stock_count"] == 2
    assert audit["industry_mapped_count"] == 1
    assert audit["concept_mapped_count"] == 1
    assert audit["missing_industry_count"] == 1
    assert audit["missing_concept_count"] == 1
    assert audit["all_industry_mapped"] is False
    assert audit["all_concept_status_accounted_for"] is True


def test_run_stock_metadata_db_hydration_writes_research_only_outputs(tmp_path, monkeypatch) -> None:
    model = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000551",
                "stock_code": "000551",
                "stock_name": "创元科技",
                "industry": "专用设备制造业",
                "industry_system": "csrc",
                "industry_source": "baostock",
                "concept_tags": "机器人概念",
                "concept_source": "akshare:concept_constituents",
                "concept_mapping_status": "mapped",
            }
        ]
    )
    calls = []
    monkeypatch.setattr(hydration, "load_all_active_stock_metadata_from_db", lambda **_kwargs: model)
    monkeypatch.setattr(hydration, "sync_industry_memberships", lambda trade_date, service: calls.append(("industry", trade_date, service)) or 1)
    monkeypatch.setattr(
        hydration,
        "sync_concept_memberships_for_service",
        lambda trade_date, service, max_concepts=None: calls.append(("concept", trade_date, service, max_concepts)) or {"boards": 2, "memberships": 3, "failed_concepts": []},
    )

    summary = hydration.run_stock_metadata_db_hydration(
        as_of_date="2026-07-08",
        output_dir=tmp_path,
        sync_industry=True,
        sync_concept=True,
        service="stock_research_test",
    )

    assert calls == [
        ("industry", "2026-07-08", "stock_research_test"),
        ("concept", "2026-07-08", "stock_research_test", None),
    ]
    assert summary["active_stock_count"] == 1
    assert summary["industry_mapped_count"] == 1
    assert summary["concept_mapped_count"] == 1
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert (tmp_path / "stock_metadata_industry_concept_db_read_model.csv").exists()
    assert (tmp_path / "stock_metadata_industry_concept_db_hydration_summary.json").exists()
    assert (tmp_path / "stock_metadata_industry_concept_db_hydration_guardrails.json").exists()


def test_run_stock_metadata_db_hydration_records_concept_sync_error(tmp_path, monkeypatch) -> None:
    model = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000551",
                "stock_code": "000551",
                "stock_name": "创元科技",
                "industry": "专用设备制造业",
                "industry_system": "csrc",
                "industry_source": "baostock",
                "concept_tags": "no_concept_mapping_found",
                "concept_source": "",
                "concept_mapping_status": "missing_concept_mapping",
            }
        ]
    )
    monkeypatch.setattr(hydration, "load_all_active_stock_metadata_from_db", lambda **_kwargs: model)

    def fail_concept_sync(**_kwargs):
        raise RuntimeError("concept source unavailable")

    monkeypatch.setattr(hydration, "sync_concept_memberships_for_service", fail_concept_sync)

    summary = hydration.run_stock_metadata_db_hydration(
        as_of_date="2026-07-08",
        output_dir=tmp_path,
        sync_concept=True,
        service="stock_research_test",
    )

    assert summary["concept_sync_performed"] is True
    assert summary["concept_sync_failed_count"] == 1
    assert summary["concept_sync_error"] == "concept source unavailable"
    assert summary["missing_concept_count"] == 1
    assert summary["acceptance_decision"] == "conditionally_ready_with_concept_sync_gap"
    assert (tmp_path / "stock_metadata_industry_concept_db_missing_mapping_audit.csv").exists()


def test_sync_concept_memberships_for_service_clears_proxy_env(monkeypatch) -> None:
    calls = []

    class FakeNoProxy:
        def __enter__(self):
            calls.append("enter_no_proxy")

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit_no_proxy")
            return False

    class FakeConnect:
        def __enter__(self):
            calls.append("enter_connect")
            return "conn"

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit_connect")
            return False

    monkeypatch.setattr(hydration, "no_proxy_env", lambda: FakeNoProxy())
    monkeypatch.setattr(hydration, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(
        hydration,
        "sync_concept_memberships_from_akshare",
        lambda conn, trade_date, max_concepts=None, offset=0, concept_system="em": calls.append(
            (conn, trade_date, max_concepts, offset, concept_system)
        )
        or {"boards": 1, "memberships": 2, "failed_concepts": []},
    )

    result = hydration.sync_concept_memberships_for_service(
        trade_date="2026-07-09",
        service="stock_research_test",
        max_concepts=10,
        offset=50,
        concept_system="ths",
    )

    assert result == {"boards": 1, "memberships": 2, "failed_concepts": []}
    assert calls == [
        "enter_no_proxy",
        "enter_connect",
        ("conn", "2026-07-09", 10, 50, "ths"),
        "exit_connect",
        "exit_no_proxy",
    ]
