"""DATA-R3-P2.1 — financial PIT interface adversarial tests (real DB)."""
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


def test_illegal_asof_rejected(conn):
    for bad in (None, "not-a-date", "2024-13-40", "", object()):
        with pytest.raises(ValueError):
            financial_pit_at(conn, "CN:SH:600000", bad, "income")


def test_illegal_report_period_rejected(conn):
    with pytest.raises(ValueError):
        financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income",
                         report_period="bad-period")


def test_no_period_picks_latest_known_not_earliest(conn):
    r = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    assert r.publicly_available_at_asof
    # must be the newest period publicly known by as_of, never the oldest
    assert r.report_period >= "2023-01-01"
    latest = fetch_all(conn, """
        SELECT max(report_period)::text rp FROM finance.income_statement
        WHERE asset_id='CN:SH:600000'
          AND announcement_date < '2024-06-01'""")[0]["rp"]
    assert r.report_period == latest


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


def test_same_day_multi_source_deterministic(conn):
    """Same key present under multiple sources -> stable pick."""
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp
        FROM finance.income_statement
        GROUP BY 1,2,report_type
        HAVING count(DISTINCT source)>1
           AND min(announcement_date)=max(announcement_date) LIMIT 1""")
    if not rows:
        pytest.skip("no same-ann multi-source key")
    r1 = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                          "income", report_period=rows[0]["rp"],
                          source_preference=("baostock",))
    r2 = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                          "income", report_period=rows[0]["rp"],
                          source_preference=("baostock",))
    assert r1.selected_statement_version == r2.selected_statement_version


def test_source_preference_is_honored(conn):
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp,
               announcement_date::text ann
        FROM finance.income_statement
        WHERE source='baostock' ORDER BY report_period DESC LIMIT 1""")
    if not rows:
        pytest.skip("no baostock rows")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                         "income", report_period=rows[0]["rp"],
                         source_preference=("baostock",))
    assert r.source == "baostock"


def test_initial_vs_latest_on_restated_key(conn):
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp, source
        FROM finance.balance_sheet
        GROUP BY 1,2,3,report_type
        HAVING count(DISTINCT announcement_date)>1 LIMIT 1""")
    if not rows:
        pytest.skip("no restated key currently in DB")
    kw = dict(conn=conn, asset_id=rows[0]["asset_id"], as_of="2027-01-01",
              statement_type="balance", report_period=rows[0]["rp"],
              source_preference=(rows[0]["source"],))
    latest = financial_pit_at(version_policy="latest_public", **kw)
    initial = financial_pit_at(version_policy="initial_public", **kw)
    assert latest.pit_status == "restated_selected"
    assert initial.publication_evidence < latest.publication_evidence


def test_historical_version_missing_flag(conn):
    """initial_public on a re-announcement-signature row must not be
    disguised as the initial published version."""
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp
        FROM finance.income_statement
        WHERE announcement_date > report_period + interval '240 days'
        GROUP BY 1,2,source
        HAVING count(DISTINCT announcement_date)=1 LIMIT 1""")
    if not rows:
        pytest.skip("no re-announcement-signature rows")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                         "income", report_period=rows[0]["rp"],
                         version_policy="initial_public")
    assert r.pit_status == "historical_version_missing"


def test_ttm_periods_independently_pit_checked(conn):
    """Each TTM component period must satisfy its own as_of gate."""
    asset_rows = fetch_all(conn, """
        SELECT asset_id FROM finance.income_statement
        WHERE report_period IN ('2024-12-31','2025-03-31')
        GROUP BY 1 HAVING count(*)=2 LIMIT 1""")
    if not asset_rows:
        pytest.skip("insufficient fixture")
    a = asset_rows[0]["asset_id"]
    fy = fetch_all(conn, """
        SELECT announcement_date::text ann FROM finance.income_statement
        WHERE asset_id=%s AND report_period='2024-12-31' LIMIT 1""",
                   [a])[0]["ann"]
    q1 = fetch_all(conn, """
        SELECT announcement_date::text ann FROM finance.income_statement
        WHERE asset_id=%s AND report_period='2025-03-31' LIMIT 1""",
                   [a])[0]["ann"]
    # as_of between FY-ann+1 and Q1-ann: TTM may use FY but not Q1
    asof = (dt.date.fromisoformat(fy) + dt.timedelta(days=1)).isoformat()
    if asof <= q1:
        r_fy = financial_pit_at(conn, a, asof, "income",
                                report_period="2024-12-31")
        r_q1 = financial_pit_at(conn, a, asof, "income",
                                report_period="2025-03-31")
        assert r_fy.publicly_available_at_asof
        assert not r_q1.publicly_available_at_asof


def test_deterministic_repeat(conn):
    a = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    b = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    assert a.__dict__ == b.__dict__


def test_delisted_asset_history_survives(conn):
    rows = fetch_all(conn, """
        SELECT a.asset_id FROM core.asset_master a
        JOIN finance.income_statement i ON i.asset_id=a.asset_id
        WHERE a.delist_date IS NOT NULL LIMIT 1""")
    if not rows:
        pytest.skip("no delisted assets in asset_master")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01", "income")
    assert r.publicly_available_at_asof is True


# ---------- P2.1-Final: parser adversarial + operational semantics ----------

import sys as _sys
_sys.path.insert(0, "scripts")
import p21_forensics_v2 as fx  # noqa: E402


def test_parser_list_payload_multi_period():
    pl = [{"REPORT_DATE": "2025-12-31", "NOTICE_DATE": "2026-03-30",
           "REPORT_TYPE": "年报", "NETPROFIT": 100, "OPERATE_INCOME": 500},
          {"REPORT_DATE": "2025-09-30", "NOTICE_DATE": "2025-10-30",
           "REPORT_TYPE": "三季报", "NETPROFIT": 80}]
    rows = fx.to_rows(pl)
    assert len(rows) == 2
    assert fx.pkey(rows[0]) == "2025-12-31"
    assert "NETPROFIT" in fx.metrics_of(rows[0])
    assert "NOTICE_DATE" not in fx.metrics_of(rows[0])


def test_parser_dict_and_wrapper_shapes():
    assert fx.to_rows({"data": [{"REPORT_DATE": "2025-12-31"}]})
    assert fx.to_rows({"REPORT_DATE": "2025-12-31"})
    assert fx.to_rows("garbage") == []
    assert fx.to_rows(None) == []


def test_field_classification():
    a = {"NETPROFIT": 100.0, "OPERATE_INCOME": 500, "MISSING_B": 1}
    b = {"NETPROFIT": 100.5, "OPERATE_INCOME": 500,
         "NEW_FIELD": 2, "MISSING_A": 3}
    per, worst = fx.classify_fields(a, b)
    assert per["OPERATE_INCOME"] == "equal"
    assert per["NETPROFIT"] in ("precision", "changed")
    assert per["MISSING_B"] == "missing" and per["NEW_FIELD"] == "missing"
    a2, b2 = {"X": None}, {"X": 5}
    per2, _ = fx.classify_fields(a2, b2)
    assert per2["X"] == "null_asymmetry"
    a3, b3 = {"X": 100.0001}, {"X": 100.0000}
    per3, _ = fx.classify_fields(a3, b3)
    assert per3["X"] in ("precision", "equal")


def test_empty_extraction_not_unchanged():
    assert fx.metrics_of({"REPORT_DATE": "2025-12-31"}) == {}
    # a payload with only meta keys must not feed a fake "same" verdict —
    # handled at comparison level (extraction_empty classification)


def test_operational_availability_is_unknown(conn):
    r = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    assert r.operationally_available_at_asof is None
    assert any("UNKNOWN" in x for x in r.restriction_reasons)


def test_initial_provable_flag_and_no_disguise(conn):
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp
        FROM finance.income_statement
        WHERE announcement_date > report_period + interval '240 days'
        GROUP BY 1,2,source
        HAVING count(DISTINCT announcement_date)=1 LIMIT 1""")
    if not rows:
        pytest.skip("no re-announcement-signature rows")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                         "income", report_period=rows[0]["rp"],
                         version_policy="initial_public")
    assert r.pit_status == "historical_version_missing"
    assert r.evidence_trace["initial_version_provable"] is False
    # surviving version may still be public — the two facts stay separate
    assert isinstance(r.publicly_available_at_asof, bool)
