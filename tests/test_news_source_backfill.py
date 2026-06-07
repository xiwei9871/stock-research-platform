import pandas as pd
import pytest
from unittest.mock import ANY
import hashlib

from stock_research import cli
from stock_research.news_source_backfill import (
    NEWS_SOURCE_COLUMNS,
    _fetch_cninfo_disclosure_announcement_rows,
    fetch_news_rows,
    normalize_historical_source_rows,
    normalize_news_source_rows,
    run_news_source_backfill,
)


def test_normalize_news_rows_deduplicates_same_source_event_id_using_last_row() -> None:
    rows = [
        {
            "source_event_id": "n1",
            "title": "A",
            "published_at": "2026-06-01 09:01:00",
            "source_name": "tushare_news",
        },
        {
            "source_event_id": "n1",
            "title": "B",
            "published_at": "2026-06-01 09:01:00",
            "source_name": "tushare_news",
        },
    ]

    frame = normalize_news_source_rows(rows, source_status="available")

    assert len(frame) == 1
    assert frame.loc[0, "source_event_id"] == "n1"
    assert frame.loc[0, "title"] == "B"
    assert frame.loc[0, "hash_key"]


def test_normalize_news_rows_sets_permission_denied_status() -> None:
    frame = normalize_news_source_rows([], source_status="permission_denied")

    assert list(frame.columns) == NEWS_SOURCE_COLUMNS
    assert frame.empty


def test_normalize_news_rows_populates_contract_fields() -> None:
    rows = [
        {
            "source_event_id": "n2",
            "title": "  Trim Me  ",
            "published_at": "2026-06-01 09:01:00+08:00",
            "source_name": "tushare_news",
            "language": "",
            "metadata": "not-a-dict",
        }
    ]

    frame = normalize_news_source_rows(rows, source_status="available")

    assert frame.loc[0, "title"] == "Trim Me"
    assert isinstance(frame.loc[0, "published_at"], pd.Timestamp)
    assert frame.loc[0, "published_at"] == pd.Timestamp("2026-06-01 09:01:00+08:00")
    assert isinstance(frame.loc[0, "collected_at"], pd.Timestamp)
    assert frame.loc[0, "source_status"] == "available"
    assert frame.loc[0, "language"] == "zh"
    assert frame.loc[0, "metadata"] == {}


def test_normalize_news_rows_drops_invalid_published_at_rows() -> None:
    rows = [
        {
            "source_event_id": "n3",
            "title": "Bad timestamp",
            "published_at": "not-a-real-time",
            "source_name": "tushare_news",
        },
        {
            "source_event_id": "n4",
            "title": "Good timestamp",
            "published_at": "2026-06-01 10:00:00",
            "source_name": "tushare_news",
        },
    ]

    frame = normalize_news_source_rows(rows, source_status="available")

    assert list(frame["source_event_id"]) == ["n4"]
    assert frame["published_at"].notna().all()


def test_normalize_eastmoney_individual_notice_rows() -> None:
    rows = [
        {
            "代码": "600183",
            "名称": "生益科技",
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告类型": "业绩预告",
            "公告日期": "2025-01-24",
            "网址": "https://data.eastmoney.com/notices/detail/600183/AN1.html",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="eastmoney_individual_notice",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(events) == 1
    assert events.iloc[0]["source_name"] == "eastmoney_individual_notice"
    assert events.iloc[0]["source_channel"] == "eastmoney_notice"
    assert events.iloc[0]["event_family"] == "disclosure_notice"
    assert events.iloc[0]["asset_id"] == "CN:SH:600183"
    assert events.iloc[0]["ts_code"] == "600183.SH"
    assert events.iloc[0]["stock_name"] == "生益科技"
    assert events.iloc[0]["content"] == ""
    assert events.iloc[0]["published_at"] == pd.Timestamp("2025-01-24 00:00:00")
    assert events.iloc[0]["metadata"]["provider"] == "eastmoney_individual_notice"


def test_normalize_eastmoney_research_report_rows() -> None:
    rows = [
        {
            "股票代码": "600183",
            "股票简称": "生益科技",
            "报告名称": "产品结构优化，业绩爆发式增长",
            "东财评级": "买入",
            "机构": "太平洋",
            "日期": "2025-05-27",
            "报告PDF链接": "https://pdf.dfcfw.com/pdf/abc.pdf",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="eastmoney_research_report",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(events) == 1
    assert events.iloc[0]["source_name"] == "eastmoney_research_report"
    assert events.iloc[0]["source_channel"] == "eastmoney_research"
    assert events.iloc[0]["event_family"] == "institution_report"
    assert events.iloc[0]["asset_id"] == "CN:SH:600183"
    assert events.iloc[0]["ts_code"] == "600183.SH"
    assert events.iloc[0]["stock_name"] == "生益科技"
    assert events.iloc[0]["title"] == "产品结构优化，业绩爆发式增长"
    assert events.iloc[0]["content"] == ""
    assert events.iloc[0]["published_at"] == pd.Timestamp("2025-05-27 00:00:00")
    assert events.iloc[0]["metadata"]["provider"] == "eastmoney_research_report"


def test_normalize_cninfo_disclosure_rows() -> None:
    rows = [
        {
            "代码": "600183",
            "简称": "生益科技",
            "公告标题": "生益科技2024年年度业绩预增公告",
            "公告时间": "2025-01-24",
            "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1&orgId=2",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="cninfo_disclosure_announcement",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(events) == 1
    assert events.iloc[0]["source_name"] == "cninfo_disclosure_announcement"
    assert events.iloc[0]["source_channel"] == "cninfo_disclosure"
    assert events.iloc[0]["event_family"] == "disclosure_notice"
    assert events.iloc[0]["asset_id"] == "CN:SH:600183"
    assert events.iloc[0]["ts_code"] == "600183.SH"
    assert events.iloc[0]["stock_name"] == "生益科技"
    assert events.iloc[0]["content"] == ""
    assert events.iloc[0]["published_at"] == pd.Timestamp("2025-01-24 00:00:00")
    assert events.iloc[0]["metadata"]["provider"] == "cninfo_disclosure_announcement"


def test_fetch_cninfo_disclosure_announcement_rows_treats_known_empty_keyerror_as_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAk:
        @staticmethod
        def stock_zh_a_disclosure_report_cninfo(
            *, symbol: str, market: str, start_date: str, end_date: str
        ):
            raise KeyError(
                "None of [Index(['代码', '简称', '公告标题', '公告时间', 'announcementId', 'orgId'], dtype='str')] are in the [columns]"
            )

    monkeypatch.setattr("stock_research.news_source_backfill.ak", FakeAk(), raising=False)

    rows = _fetch_cninfo_disclosure_announcement_rows(
        symbol="600919",
        start_date="2025-01-01",
        end_date="2025-01-31",
    )

    assert rows == []


def test_fetch_cninfo_disclosure_announcement_rows_does_not_swallow_unrelated_keyerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAk:
        @staticmethod
        def stock_zh_a_disclosure_report_cninfo(
            *, symbol: str, market: str, start_date: str, end_date: str
        ):
            raise KeyError("unexpected missing column")

    monkeypatch.setattr("stock_research.news_source_backfill.ak", FakeAk(), raising=False)

    with pytest.raises(KeyError, match="unexpected missing column"):
        _fetch_cninfo_disclosure_announcement_rows(
            symbol="600919",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )


def test_historical_fallback_source_event_id_normalizes_date_shape() -> None:
    base_row = {
        "公告标题": "生益科技:2024年年度业绩预增公告",
    }
    date_shapes = [
        {"公告日期": "2025-01-24"},
        {"公告日期": "2025-01-24 00:00:00"},
    ]

    expected_source_event_id = hashlib.sha1(
        "eastmoney_individual_notice|600183.SH|生益科技:2024年年度业绩预增公告|2025-01-24T00:00:00|".encode(
            "utf-8"
        )
    ).hexdigest()

    source_event_ids: list[str] = []
    for date_row in date_shapes:
        events = normalize_historical_source_rows(
            rows=[{**base_row, **date_row}, {**base_row, **date_row}],
            provider="eastmoney_individual_notice",
            asset_id="CN:SH:600183",
            ts_code="600183.SH",
            stock_name="生益科技",
        )

        assert len(events) == 1
        assert events.iloc[0]["source_event_id"] == expected_source_event_id
        source_event_ids.append(events.iloc[0]["source_event_id"])

    assert source_event_ids[0] == source_event_ids[1]


def test_historical_fallback_source_event_id_normalizes_timezone_shape() -> None:
    rows = [
        {
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告日期": "2025-01-24 08:00:00+08:00",
        },
        {
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告日期": "2025-01-24 08:00:00+08:00",
        },
    ]

    upper = normalize_historical_source_rows(
        rows=rows,
        provider="eastmoney_individual_notice",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    utc_rows = [
        {
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告日期": "2025-01-24 00:00:00+00:00",
        },
        {
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告日期": "2025-01-24 00:00:00+00:00",
        },
    ]
    lower = normalize_historical_source_rows(
        rows=utc_rows,
        provider="eastmoney_individual_notice",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    expected_source_event_id = hashlib.sha1(
        "eastmoney_individual_notice|600183.SH|生益科技:2024年年度业绩预增公告|2025-01-24T00:00:00|".encode(
            "utf-8"
        )
    ).hexdigest()

    assert len(upper) == 1
    assert len(lower) == 1
    assert upper.iloc[0]["source_event_id"] == expected_source_event_id
    assert lower.iloc[0]["source_event_id"] == expected_source_event_id
    assert upper.iloc[0]["source_event_id"] == lower.iloc[0]["source_event_id"]


@pytest.mark.parametrize(
    ("provider", "rows", "expected_source_name", "expected_source_channel", "expected_source_event_id"),
    [
        (
            "eastmoney_individual_notice",
            [
                {
                    "公告标题": "生益科技:2024年年度业绩预增公告",
                    "公告日期": "2025-01-24",
                },
                {
                    "公告标题": "生益科技:2024年年度业绩预增公告",
                    "公告日期": "2025-01-24",
                },
            ],
            "eastmoney_individual_notice",
            "eastmoney_notice",
            hashlib.sha1(
                "eastmoney_individual_notice|600183.SH|生益科技:2024年年度业绩预增公告|2025-01-24T00:00:00|".encode("utf-8")
            ).hexdigest(),
        ),
        (
            "eastmoney_research_report",
            [
                {
                    "报告名称": "产品结构优化，业绩爆发式增长",
                    "日期": "2025-05-27",
                },
                {
                    "报告名称": "产品结构优化，业绩爆发式增长",
                    "日期": "2025-05-27",
                },
            ],
            "eastmoney_research_report",
            "eastmoney_research",
            hashlib.sha1(
                "eastmoney_research_report|600183.SH|产品结构优化，业绩爆发式增长|2025-05-27T00:00:00|".encode("utf-8")
            ).hexdigest(),
        ),
        (
            "cninfo_disclosure_announcement",
            [
                {
                    "公告标题": "生益科技2024年年度业绩预增公告",
                    "公告时间": "2025-01-24",
                },
                {
                    "公告标题": "生益科技2024年年度业绩预增公告",
                    "公告时间": "2025-01-24",
                },
            ],
            "cninfo_disclosure_announcement",
            "cninfo_disclosure",
            hashlib.sha1(
                "cninfo_disclosure_announcement|600183.SH|生益科技2024年年度业绩预增公告|2025-01-24T00:00:00|".encode("utf-8")
            ).hexdigest(),
        ),
    ],
)
def test_normalize_historical_source_rows_uses_stable_fallback_id_without_link(
    provider: str,
    rows: list[dict[str, object]],
    expected_source_name: str,
    expected_source_channel: str,
    expected_source_event_id: str,
) -> None:
    events = normalize_historical_source_rows(
        rows=rows,
        provider=provider,
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(events) == 1
    assert events.iloc[0]["source_name"] == expected_source_name
    assert events.iloc[0]["source_channel"] == expected_source_channel
    assert events.iloc[0]["source_event_id"] == expected_source_event_id


def test_fetch_news_rows_returns_permission_denied_result_when_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_tushare_news_client",
        lambda token=None: (_ for _ in ()).throw(RuntimeError("permission denied")),
    )

    result = run_news_source_backfill(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="tushare",
    )

    assert result["source_status"] == "permission_denied"
    assert result["events"].empty


def test_news_source_backfill_treats_tushare_api_init_error_as_permission_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_tushare_news_client",
        lambda token=None: (_ for _ in ()).throw(Exception("api init error.\n请设置tushare pro的token凭证码")),
    )

    result = run_news_source_backfill(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="tushare",
    )

    assert result["source_status"] == "permission_denied"
    assert result["events"].empty


def test_fetch_news_rows_calls_tushare_news_with_src_and_datetime_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}

    class FakeClient:
        def news(self, *, src, start_date, end_date):
            recorded["src"] = src
            recorded["start_date"] = start_date
            recorded["end_date"] = end_date
            return pd.DataFrame(
                [
                    {
                        "datetime": "2026-06-01 09:30:00",
                        "title": "  Provider row  ",
                        "content": "body",
                        "channels": "finance",
                    }
                ]
            )

    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_tushare_news_client",
        lambda token=None: FakeClient(),
    )

    rows = fetch_news_rows(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="tushare",
    )

    assert recorded["src"]
    assert recorded["start_date"] == "2026-06-01 00:00:00"
    assert recorded["end_date"] == "2026-06-02 23:59:59"
    assert rows == [
        {
            "source_event_id": ANY,
            "source_name": "tushare_news",
            "source_channel": "finance",
            "title": "  Provider row  ",
            "content": "body",
            "published_at": "2026-06-01 09:30:00",
            "language": "zh",
            "url": None,
            "metadata": ANY,
        }
    ]


def test_fetch_news_rows_akshare_stock_news_em_normalizes_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAk:
        @staticmethod
        def stock_news_em(symbol: str):
            return pd.DataFrame(
                [
                    {
                        "关键词": symbol,
                        "新闻标题": "生益科技获机构看好",
                        "新闻内容": "公司订单增长。",
                        "发布时间": "2026-06-02 08:30:00",
                        "文章来源": "东方财富",
                        "新闻链接": "https://example.com/news1",
                    },
                    {
                        "关键词": symbol,
                        "新闻标题": "生益科技盘前催化",
                        "新闻内容": "订单继续改善。",
                        "发布时间": "2026-06-02 21:30:00",
                        "文章来源": "证券时报",
                        "新闻链接": None,
                    },
                    {
                        "关键词": symbol,
                        "新闻标题": "窗口外旧新闻",
                        "新闻内容": "不应进入结果。",
                        "发布时间": "2026-05-31 20:30:00",
                        "文章来源": "财联社",
                        "新闻链接": "https://example.com/old",
                    }
                ]
            )

    monkeypatch.setattr("stock_research.news_source_backfill.ak", FakeAk(), raising=False)

    rows = fetch_news_rows(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="akshare_stock_news_em",
        symbol="600183",
    )

    assert len(rows) == 2
    assert rows[0]["source_name"] == "akshare_stock_news_em"
    assert rows[0]["source_channel"] == "东方财富"
    assert rows[0]["title"] == "生益科技获机构看好"
    assert rows[0]["source_event_id"] == "https://example.com/news1"
    assert rows[0]["metadata"]["provider"] == "akshare_stock_news_em"

    expected_fallback_id = hashlib.sha1(
        "akshare_stock_news_em|证券时报|生益科技盘前催化|2026-06-02 21:30:00|".encode("utf-8")
    ).hexdigest()
    assert rows[1]["source_channel"] == "证券时报"
    assert rows[1]["source_event_id"] == expected_fallback_id
    assert rows[1]["metadata"]["provider"] == "akshare_stock_news_em"


def test_fetch_news_rows_cninfo_announcement_normalizes_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "stock_research.news_source_backfill._fetch_cninfo_announcement_rows",
        lambda ts_code, stock_name, start_date, end_date: [
            {
                "source_event_id": "ann1",
                "source_name": "cninfo_announcement",
                "source_channel": "disclosure_announcement",
                "title": "关于股票交易异常波动的公告",
                "content": "",
                "published_at": "2026-06-02 20:00:00",
                "language": "zh",
                "url": "https://www.cninfo.com.cn/ann1",
                "metadata": {"ts_code": ts_code, "stock_name": stock_name},
            }
        ],
    )

    rows = fetch_news_rows(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="cninfo_announcement",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(rows) == 1
    assert rows[0]["source_name"] == "cninfo_announcement"
    assert rows[0]["source_channel"] == "disclosure_announcement"


def test_news_source_backfill_cli_prints_paths(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    monkeypatch.setattr(
        "stock_research.cli.run_news_source_backfill",
        lambda **kwargs: {
            "source_status": "available",
            "events": pd.DataFrame(),
            "paths": {
                "events": str(tmp_path / "events.csv"),
                "report": str(tmp_path / "report.md"),
            },
        },
    )

    cli.main_for_args(
        [
            "news-source-backfill",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-02",
        ]
    )

    output = capsys.readouterr().out
    assert "news_source_backfill|events|" in output
    assert "news_source_backfill|report|" in output
    assert "news_source_backfill|source_status|" in output
