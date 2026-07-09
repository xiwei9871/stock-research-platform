from stock_research import cli


def test_market_profile_audit_cli_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "audit_market_profile_gaps",
        lambda: {
            "active_assets": 5209,
            "region_present": 0,
            "concept_present": 0,
            "np_parent_present": 0,
        },
    )

    cli.main(["market-profile-audit"])

    assert capsys.readouterr().out.strip() == (
        "market_profile_audit|active_assets|5209|region_present|0|"
        "concept_present|0|np_parent_present|0"
    )


def test_sync_market_profile_regions_cli_prints_counts(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "sync_regions_from_tushare",
        lambda: {"source_rows": 5529, "region_rows": 5200, "updated_rows": 5200},
    )

    cli.main(["sync-market-profile-regions"])

    assert capsys.readouterr().out.strip() == (
        "market_profile_regions_synced|source_rows|5529|region_rows|5200|updated_rows|5200"
    )


def test_sync_market_profile_np_parent_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_em_profit_sheet_gap_assets",
        lambda limit, offset=0: calls.append((limit, offset))
        or {"assets": 3, "income_statement": 240, "raw_payload": 3, "failed_assets": 1},
    )

    cli.main(["sync-market-profile-np-parent", "--limit", "3", "--offset", "5"])

    assert calls == [(3, 5)]
    assert capsys.readouterr().out.strip() == (
        "market_profile_np_parent_synced|assets|3|income_statement|240|raw_payload|3|failed_assets|1"
    )


def test_sync_market_profile_concepts_cli_prints_counts(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "sync_concept_memberships_for_service",
        lambda trade_date, service, max_concepts=None: calls.append((trade_date, service, max_concepts))
        or {"boards": 496, "memberships": 28000, "failed_concepts": ["失败概念"]},
    )

    cli.main(["sync-market-profile-concepts", "--trade-date", "2026-07-09", "--max-concepts", "10"])

    assert calls == [("2026-07-09", "stock_research", 10)]
    assert capsys.readouterr().out.strip() == (
        "market_profile_concepts_synced|boards|496|memberships|28000|failed_concepts|1"
    )
