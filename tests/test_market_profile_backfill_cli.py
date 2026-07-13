from stock_research import cli


def test_market_profile_audit_cli_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "audit_market_profile_gaps",
        lambda: {
            "active_assets": 5209,
            "region_present": 0,
            "region_gap": 5209,
            "concept_present": 0,
            "concept_gap": 5209,
            "np_parent_present": 0,
            "np_parent_gap": 5209,
        },
    )

    cli.main(["market-profile-audit"])

    assert capsys.readouterr().out.strip() == (
        "market_profile_audit|active_assets|5209|region_present|0|"
        "region_gap|5209|concept_present|0|concept_gap|5209|"
        "np_parent_present|0|np_parent_gap|5209"
    )


def test_sync_market_profile_regions_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_regions_from_tushare",
        lambda fallback_limit=200, workers=1, batch_size=50: calls.append((fallback_limit, workers, batch_size))
        or {
            "source": "tushare:stock_basic",
            "source_rows": 5529,
            "region_rows": 5200,
            "updated_rows": 5200,
        },
    )

    cli.main(["sync-market-profile-regions", "--fallback-limit", "100", "--workers", "2", "--batch-size", "25"])

    assert calls == [(100, 2, 25)]
    assert capsys.readouterr().out.strip() == (
        "market_profile_regions_synced|source|tushare:stock_basic|source_rows|5529|region_rows|5200|updated_rows|5200"
    )


def test_sync_market_profile_regions_cli_prints_readable_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "sync_regions_from_tushare",
        lambda fallback_limit=200, workers=1, batch_size=50: (_ for _ in ()).throw(
            RuntimeError("stock_basic frequency limit")
        ),
    )

    rc = cli.main(["sync-market-profile-regions"])

    assert rc == 1
    assert capsys.readouterr().out.strip() == (
        "market_profile_regions_synced|status|failed|error|stock_basic frequency limit"
    )


def test_sync_market_profile_regions_eastmoney_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_regions_from_eastmoney_company_survey",
        lambda limit=200, offset=0, service="stock_research", workers=1, batch_size=50: calls.append(
            (limit, offset, service, workers, batch_size)
        )
        or {
            "source": "eastmoney:PC_HSF10_CompanySurvey",
            "source_rows": 139,
            "region_rows": 139,
            "updated_rows": 139,
        },
    )

    cli.main(
        [
            "sync-market-profile-regions-eastmoney",
            "--limit",
            "139",
            "--offset",
            "3",
            "--workers",
            "4",
            "--batch-size",
            "20",
        ]
    )

    assert calls == [(139, 3, "stock_research", 4, 20)]
    assert capsys.readouterr().out.strip() == (
        "market_profile_regions_eastmoney_synced|source|eastmoney:PC_HSF10_CompanySurvey|"
        "source_rows|139|region_rows|139|updated_rows|139"
    )


def test_sync_market_profile_np_parent_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_em_profit_sheet_gap_assets",
        lambda limit, offset=0, workers=1: calls.append((limit, offset, workers))
        or {"assets": 3, "income_statement": 240, "raw_payload": 3, "failed_assets": 1},
    )

    cli.main(["sync-market-profile-np-parent", "--limit", "3", "--offset", "5", "--workers", "2"])

    assert calls == [(3, 5, 2)]
    assert capsys.readouterr().out.strip() == (
        "market_profile_np_parent_synced|assets|3|income_statement|240|raw_payload|3|failed_assets|1"
    )


def test_sync_market_profile_concepts_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_concept_memberships_for_service",
        lambda trade_date, service, max_concepts=None, offset=0, concept_system="em": calls.append(
            (trade_date, service, max_concepts, offset, concept_system)
        )
        or {"boards": 496, "memberships": 28000, "failed_concepts": ["失败概念"]},
    )

    cli.main(
        [
            "sync-market-profile-concepts",
            "--trade-date",
            "2026-07-09",
            "--max-concepts",
            "10",
            "--offset",
            "50",
            "--concept-system",
            "ths",
        ]
    )

    assert calls == [("2026-07-09", "stock_research", 10, 50, "ths")]
    assert capsys.readouterr().out.strip() == (
        "market_profile_concepts_synced|boards|496|memberships|28000|failed_concepts|1"
    )


def test_sync_market_profile_stock_concepts_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_eastmoney_core_conceptions_for_gap_assets",
        lambda trade_date, limit, offset=0, service="stock_research": calls.append((trade_date, limit, offset, service))
        or {"assets": 2, "concepts": 5, "memberships": 7, "failed_assets": 1},
    )

    cli.main(
        [
            "sync-market-profile-stock-concepts",
            "--trade-date",
            "2026-07-09",
            "--limit",
            "2",
            "--offset",
            "3",
        ]
    )

    assert calls == [("2026-07-09", 2, 3, "stock_research")]
    assert capsys.readouterr().out.strip() == (
        "market_profile_stock_concepts_synced|assets|2|concepts|5|memberships|7|failed_assets|1"
    )
