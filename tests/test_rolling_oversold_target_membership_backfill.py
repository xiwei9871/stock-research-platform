from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stock_research.rolling_oversold import target_membership_backfill as backfill


def _master(
    asset_id: str,
    *,
    exchange: str = "SZ",
    is_active: bool = True,
    list_date: date | None = date(2020, 1, 1),
    delist_date: date | None = None,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "symbol": asset_id.rsplit(":", 1)[-1],
        "name": asset_id,
        "exchange": exchange,
        "list_date": list_date,
        "delist_date": delist_date,
        "is_active": is_active,
        "is_beijing": exchange == "BJ",
    }


def test_load_target_codes_accepts_concept_csv_and_plain_code_list(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("concept_code,concept_name\n300238,核电\n309268,样本\n", encoding="utf-8")
    list_path = tmp_path / "targets.txt"
    list_path.write_text("300238\n309268\n", encoding="utf-8")

    assert backfill.load_target_codes(csv_path) == ("300238", "309268")
    assert backfill.load_target_codes(list_path) == ("300238", "309268")

    duplicate_path = tmp_path / "duplicate.txt"
    duplicate_path.write_text("300238\n300238\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        backfill.load_target_codes(duplicate_path)

    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("30023\n", encoding="utf-8")
    with pytest.raises(ValueError, match="six-digit"):
        backfill.load_target_codes(invalid_path)


def test_target_membership_dry_run_does_not_write(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame(
            [
                {"name": "核电", "code": "300238"},
            ]
        ),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_constituents",
        lambda symbol: pd.DataFrame([{"代码": "000001", "名称": "样本"}]),
    )
    monkeypatch.setattr(
        backfill,
        "load_target_asset_master",
        lambda asset_ids, trade_date, service: [_master("CN:SZ:000001")],
    )
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda *args, **kwargs: pytest.fail("dry-run must not write"),
    )
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda *args, **kwargs: pytest.fail("dry-run must not write"),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238", "309268"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["database_writes"] == 0
    assert result["source_missing_codes"] == ["309268"]
    assert result["valid_non_bj_memberships"] == 1
    assert result["paths"]["json"]
    assert result["paths"]["csv"]


def test_target_membership_backfill_rejects_bj_members():
    rows = [{"asset_id": "CN:BJ:920001", "concept_code": "300238"}]

    with pytest.raises(ValueError, match="out_of_scope_bse"):
        backfill.validate_target_membership_rows(rows, target_codes={"300238"})


def test_asset_eligibility_is_point_in_time_around_delist_date():
    cutoff = date(2026, 7, 31)

    # Current master status may already be inactive, but a future delist proves
    # that the asset was eligible at the frozen cutoff.
    assert backfill._asset_eligibility(
        _master(
            "CN:SZ:000001",
            is_active=False,
            delist_date=date(2026, 8, 15),
        ),
        cutoff,
    ) == ("valid", "")
    assert backfill._asset_eligibility(
        _master(
            "CN:SZ:000001",
            is_active=True,
            delist_date=date(2026, 7, 31),
        ),
        cutoff,
    )[0] == "delisted"
    assert backfill._asset_eligibility(
        _master(
            "CN:SZ:000001",
            is_active=True,
            delist_date=date(2026, 7, 30),
        ),
        cutoff,
    )[0] == "delisted"
    assert backfill._asset_eligibility(
        _master(
            "CN:SZ:000001",
            is_active=True,
            list_date=date(2026, 8, 1),
        ),
        cutoff,
    )[0] == "inactive_pit"


@pytest.mark.parametrize("empty_response", [None, pd.DataFrame(), []])
def test_empty_constituent_response_is_failed_and_does_not_close_history(
    monkeypatch, tmp_path: Path, empty_response
):
    class FakeConnection:
        pass

    @contextmanager
    def fake_connect(_service):
        yield FakeConnection()

    execute_calls: list[tuple[str, list[object]]] = []
    monkeypatch.setattr(backfill, "connect", fake_connect)
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame([{"name": "核电", "code": "300238"}]),
    )
    monkeypatch.setattr(backfill, "fetch_target_concept_constituents", lambda symbol: empty_response)
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda conn, sql, params: execute_calls.append((sql, list(params))),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=False,
    )

    assert result["failed_concepts"] == ["300238"]
    assert result["valid_non_bj_memberships"] == 0
    assert not [call for call in execute_calls if "UPDATE core.concept_membership" in call[0]]


def test_900xxx_is_audited_without_being_written(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame([{"name": "核电", "code": "300238"}]),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_constituents",
        lambda symbol: pd.DataFrame(
            [
                {"代码": "900001", "名称": "沪市B股"},
                {"代码": "920001", "名称": "北交所"},
                {"代码": "000001", "名称": "样本"},
            ]
        ),
    )
    monkeypatch.setattr(
        backfill,
        "load_target_asset_master",
        lambda asset_ids, trade_date, service: [_master("CN:SZ:000001")],
    )
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda *args, **kwargs: pytest.fail("dry-run must not write"),
    )
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda *args, **kwargs: pytest.fail("dry-run must not write"),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=True,
    )

    assert result["out_of_scope_900xxx"] == ["900001"]
    assert result["out_of_scope_900xxx_count"] == 1
    assert result["out_of_scope_bse"] == ["CN:BJ:920001"]
    assert result["valid_non_bj_memberships"] == 1


@pytest.mark.parametrize(
    "malformed_response",
    [
        (item for item in []),
        pd.DataFrame([{"名称": "没有代码列"}]),
        ["not-a-mapping"],
    ],
)
def test_empty_or_invalid_constituent_response_blocks_history_close(
    monkeypatch, tmp_path: Path, malformed_response
):
    class FakeConnection:
        pass

    @contextmanager
    def fake_connect(_service):
        yield FakeConnection()

    execute_calls: list[tuple[str, list[object]]] = []
    monkeypatch.setattr(backfill, "connect", fake_connect)
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame([{"name": "核电", "code": "300238"}]),
    )
    monkeypatch.setattr(backfill, "fetch_target_concept_constituents", lambda symbol: malformed_response)
    monkeypatch.setattr(backfill, "execute_many", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda conn, sql, params: execute_calls.append((sql, list(params))),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=False,
    )

    assert result["failed_concepts"] == ["300238"]
    assert result["database_writes"] == 0
    assert result["write_blocked_reason"] == "source_incomplete"
    assert not execute_calls


def test_source_missing_code_blocks_execute_before_any_database_write(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame([{"name": "核电", "code": "300238"}]),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_constituents",
        lambda symbol: pd.DataFrame([{"代码": "000001", "名称": "样本"}]),
    )
    monkeypatch.setattr(
        backfill,
        "load_target_asset_master",
        lambda asset_ids, trade_date, service: [_master("CN:SZ:000001")],
    )
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda *args, **kwargs: pytest.fail("partial source must not write"),
    )
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda *args, **kwargs: pytest.fail("partial source must not close history"),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238", "309268"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=False,
    )

    assert result["source_missing_codes"] == ["309268"]
    assert result["write_blocked"] is True
    assert result["write_blocked_reason"] == "source_incomplete"
    assert result["database_writes"] == 0


def test_failed_source_concept_blocks_all_writes_and_preserves_history(monkeypatch, tmp_path: Path):
    class FakeConnection:
        pass

    @contextmanager
    def fake_connect(_service):
        yield FakeConnection()

    execute_many_calls: list[tuple[str, list[tuple[object, ...]]]] = []
    execute_calls: list[tuple[str, list[object]]] = []
    monkeypatch.setattr(backfill, "connect", fake_connect)
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame(
            [
                {"name": "成功板块", "code": "300238"},
                {"name": "失败板块", "code": "309268"},
            ]
        ),
    )

    def constituents(symbol):
        if symbol == "309268":
            raise RuntimeError("source unavailable")
        return pd.DataFrame([{"代码": "000001", "名称": "样本"}])

    monkeypatch.setattr(backfill, "fetch_target_concept_constituents", constituents)
    monkeypatch.setattr(
        backfill,
        "load_target_asset_master",
        lambda asset_ids, trade_date, service: [_master("CN:SZ:000001")],
    )
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda conn, sql, rows: execute_many_calls.append((sql, list(rows))),
    )
    monkeypatch.setattr(
        backfill,
        "execute",
        lambda conn, sql, params: execute_calls.append((sql, list(params))),
    )

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238", "309268"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=False,
    )

    assert result["failed_concepts"] == ["309268"]
    assert result["database_writes"] == 0
    assert result["write_blocked"] is True
    assert result["write_blocked_reason"] == "source_incomplete"
    assert execute_many_calls == []
    assert execute_calls == []


def test_ths_detail_constituent_adapter_paginates_and_extracts_second_column(monkeypatch):
    class FakeResponse:
        def __init__(self, text: str, *, status_code: int = 200, content_type: str = "text/html"):
            self.text = text
            self.status_code = status_code
            self.headers = {"Content-Type": content_type}

    pages = {
        1: """
        <html><body><div class='m-page'><span class='page_info'>1/2</span></div>
        <table class='m-table m-pager-table'><tbody>
          <tr><td>1</td><td><a>000001</a></td><td>样本一</td></tr>
        </tbody></table></body></html>
        """,
        2: """
        <html><body><div class='m-page'><span class='page_info'>2/2</span></div>
        <table class='m-table m-pager-table'><tbody>
          <tr><td>2</td><td><a>600000</a></td><td>样本二</td></tr>
        </tbody></table></body></html>
        """,
    }
    seen_urls: list[str] = []

    class FakeSession:
        def get(self, url, **kwargs):
            seen_urls.append(url)
            page = int(url.split("/page/")[1].split("/")[0])
            return FakeResponse(pages[page])

    monkeypatch.setattr(backfill, "_get_ths_v_code", lambda: "test-v")
    monkeypatch.setattr(backfill.requests, "Session", lambda: FakeSession())

    frame = backfill.fetch_ths_detail_constituents("300238")

    assert frame["代码"].tolist() == ["000001", "600000"]
    assert frame["名称"].tolist() == ["样本一", "样本二"]
    assert "/code/300238/" in seen_urls[0]
    assert "?cb=1" in seen_urls[0]
    assert len(seen_urls) == 2


@pytest.mark.parametrize(
    "response",
    [
        {"status_code": 401, "content_type": "text/html", "text": "<html/>"},
        {"status_code": 200, "content_type": "text/plain", "text": "not html"},
        {
            "status_code": 200,
            "content_type": "text/html",
            "text": "<html><body><span class='page_info'>1/1</span><table class='m-table m-pager-table'><tbody></tbody></table></body></html>",
        },
    ],
)
def test_ths_detail_constituent_adapter_fails_closed_for_bad_or_empty_response(
    monkeypatch, response
):
    class FakeResponse:
        status_code = response["status_code"]
        headers = {"Content-Type": response["content_type"]}
        text = response["text"]

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(backfill, "_get_ths_v_code", lambda: "test-v")
    monkeypatch.setattr(backfill.requests, "Session", lambda: FakeSession())
    with pytest.raises(RuntimeError, match="401|non_html|empty_response"):
        backfill.fetch_ths_detail_constituents("300238")


def test_ths_detail_single_page_without_page_info_is_accepted(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        text = """
        <table class='m-table m-pager-table'><tbody>
          <tr><td>1</td><td>000001</td><td>样本</td></tr>
        </tbody></table>
        """

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(backfill, "_get_ths_v_code", lambda: "test-v")
    monkeypatch.setattr(backfill.requests, "Session", lambda: FakeSession())

    frame = backfill.fetch_ths_detail_constituents("309185")

    assert frame["代码"].tolist() == ["000001"]


@pytest.mark.parametrize(
    "body",
    [
        "",
        "<html><body>请先登录后继续</body></html>",
        "<html><body>captcha challenge</body></html>",
        '<script>location.href="//upass.10jqka.com.cn/login"</script>',
    ],
)
def test_ths_detail_empty_body_or_auth_challenge_is_explicit(monkeypatch, body):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        text = body

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(backfill, "_get_ths_v_code", lambda: "test-v")
    monkeypatch.setattr(backfill.requests, "Session", lambda: FakeSession())
    with pytest.raises(RuntimeError, match="ths_auth_challenge"):
        backfill.fetch_ths_detail_constituents("300238")


def test_target_membership_uses_idempotent_conflict_key(monkeypatch, tmp_path: Path):
    class FakeConnection:
        pass

    @contextmanager
    def fake_connect(_service):
        yield FakeConnection()

    execute_many_calls: list[tuple[str, list[tuple[object, ...]]]] = []
    monkeypatch.setattr(backfill, "connect", fake_connect)
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_boards",
        lambda: pd.DataFrame([{"name": "核电", "code": "300238"}]),
    )
    monkeypatch.setattr(
        backfill,
        "fetch_target_concept_constituents",
        lambda symbol: pd.DataFrame([{"代码": "000001", "名称": "样本"}]),
    )
    monkeypatch.setattr(
        backfill,
        "load_target_asset_master",
        lambda asset_ids, trade_date, service: [_master("CN:SZ:000001")],
    )
    monkeypatch.setattr(
        backfill,
        "execute_many",
        lambda conn, sql, rows: execute_many_calls.append((sql, list(rows))),
    )
    monkeypatch.setattr(backfill, "execute", lambda *args, **kwargs: None)

    result = backfill.run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes={"300238"},
        service="research-test",
        output_dir=tmp_path,
        dry_run=False,
    )

    membership_sql = next(sql for sql, _rows in execute_many_calls if "concept_membership" in sql)
    assert "ON CONFLICT (asset_id, concept_system, concept_code, start_date)" in membership_sql
    assert result["upsert_conflict_key"] == [
        "asset_id",
        "concept_system",
        "concept_code",
        "start_date",
    ]


def test_target_membership_cli_parser_and_dispatch(monkeypatch, tmp_path: Path, capsys):
    from stock_research import cli

    parser = cli.build_parser()
    parsed = parser.parse_args(
        [
            "rolling-sector-target-membership-backfill",
            "--trade-date",
            "2026-07-31",
            "--concept-codes-file",
            str(tmp_path / "targets.csv"),
            "--service",
            "research-test",
            "--output-dir",
            str(tmp_path),
            "--dry-run",
        ]
    )
    assert parsed.trade_date == "2026-07-31"
    assert parsed.concept_codes_file == str(tmp_path / "targets.csv")
    assert parsed.dry_run is True

    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "dry_run": True,
            "database_writes": 0,
            "paths": {"json": str(tmp_path / "summary.json"), "csv": str(tmp_path / "rows.csv")},
            "target_code_count": 1,
            "valid_non_bj_memberships": 0,
            "source_missing_codes": [],
            "failed_concepts": [],
            "out_of_scope_bse": [],
        }

    monkeypatch.setattr(cli, "run_target_membership_backfill", fake_run, raising=False)
    assert (
        cli.main_for_args(
            [
                "rolling-sector-target-membership-backfill",
                "--trade-date",
                "2026-07-31",
                "--concept-codes-file",
                str(tmp_path / "targets.csv"),
                "--service",
                "research-test",
                "--output-dir",
                str(tmp_path),
                "--dry-run",
            ]
        )
        == 0
    )
    assert captured["trade_date"] == date(2026, 7, 31)
    assert captured["target_codes"] == str(tmp_path / "targets.csv")
    assert captured["dry_run"] is True
    output = capsys.readouterr().out
    assert "rolling_sector_target_membership_backfill|json|" in output
    assert "rolling_sector_target_membership_backfill|database_writes|0" in output
