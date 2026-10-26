"""DATA-R3-P2 — financial PIT interface adversarial tests (real DB)."""
import datetime as dt

import pytest

from stock_research.db import connect, fetch_all
from stock_research.config import SETTINGS
from stock_research.financial_pit import (
    ANN_SENTINEL, VERSION_POLICIES, financial_pit_at)

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def conn():
    with connect(SETTINGS.research_service) as c:
        yield c


def _row_with_ann(conn):
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp,
               announcement_date::text ann
        FROM finance.income_statement
        WHERE announcement_date > '2020-01-01' LIMIT 1""")
    assert rows, "no announced income rows in DB"
    return rows[0]


def test_unknown_asset_is_not_reported(conn):
    r = financial_pit_at(conn, "CN:XX:000000", "2024-06-01", "income")
    assert r.pit_status == "period_not_reported"
    assert r.publicly_available_at_asof is False


def test_invalid_statement_type_rejected(conn):
    with pytest.raises(ValueError):
        financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "balance_sheet")


def test_invalid_version_policy_rejected(conn):
    with pytest.raises(ValueError):
        financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income",
                         version_policy="newest")
    for p in VERSION_POLICIES:
        financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income",
                         version_policy=p)


def test_period_ended_but_not_announced_blocks(conn):
    row = _row_with_ann(conn)
    day_before = (dt.date.fromisoformat(row["ann"])
                  - dt.timedelta(days=1)).isoformat()
    r = financial_pit_at(conn, row["asset_id"], day_before, "income",
                         report_period=row["rp"])
    assert r.pit_status == "not_yet_published"
    assert r.publicly_available_at_asof is False


def test_announcement_day_itself_is_blocked(conn):
    row = _row_with_ann(conn)
    r = financial_pit_at(conn, row["asset_id"], row["ann"], "income",
                         report_period=row["rp"])
    assert r.pit_status == "not_yet_published", (
        "announcement-date-only must not leak into the same trading day")


def test_day_after_announcement_is_visible(conn):
    row = _row_with_ann(conn)
    day_after = (dt.date.fromisoformat(row["ann"])
                 + dt.timedelta(days=1)).isoformat()
    r = financial_pit_at(conn, row["asset_id"], day_after, "income",
                         report_period=row["rp"])
    assert r.publicly_available_at_asof is True
    assert r.pit_status in ("verified_public", "restated_selected")
    assert r.publication_evidence == row["ann"]


def test_sentinel_announcement_fails_closed(conn):
    rows = fetch_all(conn, f"""
        SELECT asset_id, report_period::text rp FROM finance.balance_sheet
        WHERE announcement_date='{ANN_SENTINEL}' LIMIT 1""")
    if not rows:
        pytest.skip("no sentinel announcement rows currently")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                         "balance", report_period=rows[0]["rp"])
    assert r.pit_status == "publication_date_missing"
    assert r.publicly_available_at_asof is False


def test_deterministic_repeat(conn):
    a = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    b = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    assert a.__dict__ == b.__dict__


def test_future_asof_does_not_change_past_versions(conn):
    row = _row_with_ann(conn)
    r = financial_pit_at(conn, row["asset_id"], "2027-01-01", "income",
                         report_period=row["rp"])
    assert r.publication_evidence is not None
    assert r.publication_evidence <= row["ann"]


def test_delisted_asset_history_survives(conn):
    rows = fetch_all(conn, """
        SELECT a.asset_id FROM core.asset_master a
        JOIN finance.income_statement i ON i.asset_id=a.asset_id
        WHERE a.delist_date IS NOT NULL LIMIT 1""")
    if not rows:
        pytest.skip("no delisted assets in asset_master")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01", "income")
    assert r.publicly_available_at_asof is True
