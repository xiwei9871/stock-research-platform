from pathlib import Path
import warnings

import pandas as pd
import pytest

from stock_research import cli
from stock_research.news_source_backfill import (
    _load_historical_top10_candidates,
    run_historical_top10_news_backfill,
    run_topn_news_source_backfill,
)


def test_run_topn_news_source_backfill_uses_candidate_symbols_and_writes_events(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
            },
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:688390",
                "ts_code": "688390.SH",
                "stock_name": "固德威",
            },
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert Path(result["paths"]["events"]).exists()
    assert len(result["events"]) == 2
    assert set(result["events"]["source_event_id"]) == {"600183-1", "300201-1"}
    assert set(result["events"]["source_name"]) == {"akshare_stock_news_em"}
    assert all("matched_candidates" in metadata for metadata in result["events"]["metadata"])
    assert result["events"].iloc[0]["metadata"]["matched_candidates"] == [
        {
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
        }
    ]


def test_run_topn_news_source_backfill_replaces_code_like_stock_name_from_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "600183.SH",
            }
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    lookup_calls = 0

    def _fake_lookup(*, ts_codes):
        nonlocal lookup_calls
        lookup_calls += 1
        assert ts_codes == ["600183.SH"]
        return {"600183.SH": "生益科技"}

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        _fake_lookup,
        raising=False,
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert lookup_calls == 1
    assert result["events"].iloc[0]["metadata"]["matched_candidates"] == [
        {
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
        }
    ]


def test_run_topn_news_source_backfill_replaces_lowercase_code_like_stock_name_from_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "cn:sh:600183",
                "ts_code": "600183.SH",
                "stock_name": "600183.sh",
            }
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"600183.SH": "生益科技"},
        raising=False,
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert result["events"].iloc[0]["metadata"]["matched_candidates"] == [
        {
            "asset_id": "cn:sh:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
        }
    ]


def test_run_topn_news_source_backfill_preserves_real_stock_name_from_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"600183.SH": "替换名称"},
        raising=False,
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert result["events"].iloc[0]["metadata"]["matched_candidates"] == [
        {
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
        }
    ]


def test_run_topn_news_source_backfill_skips_malformed_candidate_rows(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:000001",
                "ts_code": "",
                "stock_name": "平安银行",
            },
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    fetch_calls: list[str] = []

    def _fake_fetch(**kwargs):
        fetch_calls.append(kwargs["symbol"])
        return [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ]

    monkeypatch.setattr("stock_research.news_source_backfill.fetch_news_rows", _fake_fetch)

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert fetch_calls == ["600183"]
    assert len(result["events"]) == 1


def test_run_topn_news_source_backfill_warns_when_lookup_loading_fails(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "600183.SH",
            }
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_topn_news_source_backfill(
            candidates_path=candidates_path,
            provider="akshare_stock_news_em",
            trade_date="2026-06-02",
            output_dir=tmp_path / "out",
        )

    assert len(result["events"]) == 1
    assert any("lookup" in str(item.message).lower() for item in caught)


def test_run_topn_news_source_backfill_degrades_safely_without_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "600183.SH",
            }
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f"{kwargs['symbol']}-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": f"{kwargs['symbol']} 新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {},
        raising=False,
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert result["events"].iloc[0]["metadata"]["matched_candidates"] == [
        {
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "600183.SH",
        }
    ]


def test_topn_news_source_backfill_cli_prints_paths(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        "stock_research.cli.run_topn_news_source_backfill",
        lambda **kwargs: {
            "events": pd.DataFrame([{"source_event_id": "600183-1"}]),
            "paths": {
                "events": str(tmp_path / "events.csv"),
                "report": str(tmp_path / "report.md"),
            },
        },
    )

    cli.main_for_args(
        [
            "topn-news-source-backfill",
            "--candidates-path",
            str(tmp_path / "candidates.csv"),
            "--provider",
            "akshare_stock_news_em",
            "--trade-date",
            "2026-06-02",
        ]
    )

    output = capsys.readouterr().out
    assert "topn_news_source_backfill|events|" in output
    assert "topn_news_source_backfill|report|" in output
    assert "topn_news_source_backfill|rows|1" in output


def test_run_topn_news_source_backfill_aggregates_multi_candidate_coverage_and_dedupes_symbol_fetches(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
            },
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    fetch_calls: list[str] = []

    def _fake_fetch(**kwargs):
        fetch_calls.append(kwargs["symbol"])
        return [
            {
                "source_event_id": "shared-article-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "共享新闻",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": "https://example.com/shared",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        _fake_fetch,
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert fetch_calls == ["600183", "300201"]
    assert len(result["events"]) == 1
    metadata = result["events"].iloc[0]["metadata"]
    assert "matched_candidates" in metadata
    assert metadata["matched_candidates"] == [
        {
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
        },
        {
            "asset_id": "CN:SZ:300201",
            "ts_code": "300201.SZ",
            "stock_name": "海伦哲",
        },
    ]


def test_load_historical_top10_candidates_filters_window_and_samples_trade_dates(
    tmp_path,
) -> None:
    top10_path = tmp_path / "top10.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "extra": "keep-out",
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "extra": "keep-out",
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:000001",
                "ts_code": "",
                "stock_name": "平安银行",
                "extra": "keep-out",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SZ:300408",
                "ts_code": "300408.SZ",
                "stock_name": "三环集团",
                "extra": "keep-out",
            },
        ]
    ).to_csv(top10_path, index=False)

    result = _load_historical_top10_candidates(
        top10_path=top10_path,
        start_date="2025-01-03",
        end_date="2025-01-06",
        sample_trade_dates=1,
    )

    assert list(result.columns) == ["trade_date", "asset_id", "ts_code", "stock_name"]
    assert result["trade_date"].nunique() == 1
    assert result["trade_date"].min().isoformat() == "2025-01-03"
    assert set(result["ts_code"]) == {"300201.SZ"}


def test_load_historical_top10_candidates_returns_empty_when_trade_date_missing(
    tmp_path,
) -> None:
    top10_path = tmp_path / "top10.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    ).to_csv(top10_path, index=False)

    result = _load_historical_top10_candidates(
        top10_path=top10_path,
        start_date="2025-01-03",
        end_date="2025-01-06",
        sample_trade_dates=1,
    )

    assert list(result.columns) == ["trade_date", "asset_id", "ts_code", "stock_name"]
    assert result.empty


def test_run_historical_top10_news_backfill_writes_combined_artifacts(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
            },
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    collected_calls: list[tuple[str, tuple[str, ...]]] = []

    def _fake_collect(*, candidates, provider=None, providers=None, trade_date, fetch_start_date=None):
        collected_calls.append((trade_date, fetch_start_date, tuple(candidates["ts_code"])))
        candidate = candidates.iloc[0]
        return pd.DataFrame(
            [
                {
                    "source_event_id": f"{trade_date}-event",
                    "source_name": "akshare_stock_news_em",
                    "source_channel": "东方财富",
                    "title": f"{trade_date} {candidate['stock_name']} 订单增长",
                    "content": "正文",
                    "published_at": f"{trade_date} 09:00:00",
                    "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                    "language": "zh",
                    "url": None,
                    "hash_key": f"{trade_date}-hash",
                    "source_status": "available",
                    "metadata": {
                        "matched_candidates": [
                            {
                                "asset_id": candidate["asset_id"],
                                "ts_code": candidate["ts_code"],
                                "stock_name": candidate["stock_name"],
                            }
                        ]
                    },
                }
            ]
        )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._collect_topn_news_source_events_for_candidates",
        _fake_collect,
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-03",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert collected_calls == [
        ("2025-01-03", "2025-01-02", ("600183.SH",)),
        ("2025-01-06", "2025-01-05", ("300201.SZ",)),
    ]
    assert Path(result["paths"]["candidates"]).exists()
    assert Path(result["paths"]["source_events"]).exists()
    assert Path(result["paths"]["mentions"]).exists()
    assert Path(result["paths"]["features"]).exists()
    assert Path(result["paths"]["enrichment"]).exists()
    assert result["trade_date_count"] == 2
    assert len(result["source_events"]) == 2
    assert len(result["mentions"]) == 2
    assert len(result["features"]) == 3
    assert len(result["enrichment"]) == 2
    assert pd.read_csv(result["paths"]["candidates"]).shape[0] == 2
    assert pd.read_csv(result["paths"]["source_events"]).shape[0] == 2
    assert pd.read_csv(result["paths"]["mentions"]).shape[0] == 2
    assert pd.read_csv(result["paths"]["features"]).shape[0] == 3
    assert pd.read_csv(result["paths"]["enrichment"]).shape[0] == 2
    assert result["enrichment"].iloc[0]["news_compact_summary"] == "近3日订单/中标催化"


def test_run_historical_top10_news_backfill_combines_multiple_historical_providers(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    fetch_calls: list[str] = []

    def _fake_fetch_historical_provider_rows(
        *,
        provider,
        symbol,
        ts_code,
        stock_name,
        start_date,
        end_date,
    ):
        fetch_calls.append(provider)
        if provider == "eastmoney_individual_notice":
            return [
                {
                    "source_event_id": "notice-1",
                    "source_name": "eastmoney_individual_notice",
                    "source_channel": "eastmoney_notice",
                    "event_family": "disclosure_notice",
                    "title": "生益科技:2024年年度业绩预增公告",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "https://data.eastmoney.com/notices/detail/600183/AN1.html",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        if provider == "eastmoney_research_report":
            return [
                {
                    "source_event_id": "report-1",
                    "source_name": "eastmoney_research_report",
                    "source_channel": "eastmoney_research",
                    "event_family": "institution_report",
                    "title": "产品结构优化，业绩爆发式增长",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "https://pdf.dfcfw.com/pdf/abc.pdf",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        if provider == "cninfo_disclosure_announcement":
            return [
                {
                    "source_event_id": "cninfo-1",
                    "source_name": "cninfo_disclosure_announcement",
                    "source_channel": "cninfo_disclosure",
                    "event_family": "disclosure_notice",
                    "title": "生益科技2024年年度业绩预增公告",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1&orgId=2",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        return []

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_provider_rows",
        _fake_fetch_historical_provider_rows,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-24",
        end_date="2025-01-24",
        providers=[
            "eastmoney_individual_notice",
            "eastmoney_research_report",
            "cninfo_disclosure_announcement",
        ],
        output_dir=tmp_path / "out",
    )

    assert fetch_calls == [
        "eastmoney_individual_notice",
        "eastmoney_research_report",
        "cninfo_disclosure_announcement",
    ]
    assert len(result["source_events"]) == 3
    assert set(result["source_events"]["source_name"]) == {
        "eastmoney_individual_notice",
        "eastmoney_research_report",
        "cninfo_disclosure_announcement",
    }
    assert set(result["source_events"]["event_family"]) == {"disclosure_notice", "institution_report"}


def test_run_historical_top10_news_backfill_keeps_successful_historical_provider_rows_when_one_provider_fails(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    def _fake_fetch_historical_provider_rows(
        *,
        provider,
        symbol,
        ts_code,
        stock_name,
        start_date,
        end_date,
    ):
        if provider == "eastmoney_individual_notice":
            raise RuntimeError("provider temporarily unavailable")
        if provider == "eastmoney_research_report":
            return [
                {
                    "source_event_id": "report-1",
                    "source_name": "eastmoney_research_report",
                    "source_channel": "eastmoney_research",
                    "event_family": "institution_report",
                    "title": "产品结构优化，业绩爆发式增长",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "https://pdf.dfcfw.com/pdf/abc.pdf",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        return []

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_provider_rows",
        _fake_fetch_historical_provider_rows,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-24",
        end_date="2025-01-24",
        providers=[
            "eastmoney_individual_notice",
            "eastmoney_research_report",
        ],
        output_dir=tmp_path / "out",
    )

    assert len(result["source_events"]) == 1
    assert set(result["source_events"]["source_name"]) == {"eastmoney_research_report"}


def test_run_historical_top10_news_backfill_includes_t_minus_one_evening_news_in_overnight_slice(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"600183.SH": "生益科技"},
        raising=False,
    )

    fetch_calls: list[tuple[str, str]] = []

    def _fake_fetch(**kwargs):
        fetch_calls.append((kwargs["start_date"], kwargs["end_date"]))
        if kwargs["start_date"] == "2025-01-05" and kwargs["end_date"] == "2025-01-06":
            return [
                {
                    "source_event_id": "overnight-1",
                    "source_name": "akshare_stock_news_em",
                    "source_channel": "东方财富",
                    "title": "生益科技 T-1 evening 订单增长",
                    "content": "正文",
                    "published_at": "2025-01-05 20:30:00",
                    "language": "zh",
                    "url": None,
                    "metadata": {
                        "matched_candidates": [
                            {
                                "asset_id": "CN:SH:600183",
                                "ts_code": "600183.SH",
                                "stock_name": "生益科技",
                            }
                        ]
                    },
                }
            ]
        return []

    monkeypatch.setattr("stock_research.news_source_backfill.fetch_news_rows", _fake_fetch)

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-06",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert fetch_calls == [("2025-01-05", "2025-01-06")]
    assert len(result["source_events"]) == 1
    assert len(result["mentions"]) == 1
    assert len(result["features"]) == 1
    assert result["features"].iloc[0]["overnight_news_count"] == 1


def test_run_historical_top10_news_backfill_normalizes_code_like_stock_name_into_final_outputs(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "600183.SH",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"600183.SH": "生益科技"},
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": "same-day-1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "生益科技 订单增长",
                "content": "正文",
                "published_at": "2025-01-06 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-06",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert result["candidates"].iloc[0]["stock_name"] == "生益科技"
    assert result["enrichment"].iloc[0]["stock_name"] == "生益科技"
    assert result["enrichment"].iloc[0]["news_compact_summary"] == "近3日订单/中标催化"


def test_run_historical_top10_news_backfill_fills_empty_stock_name_from_asset_id_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": "",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    captured: dict[str, object] = {}

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        if "asset_id" in sql:
            return [
                {
                    "asset_id": "CN:SH:600066",
                    "ts_code": None,
                    "stock_name": "宇通客车",
                }
            ]
        return []

    def _fake_collect(*, candidates, provider=None, providers=None, trade_date, fetch_start_date=None):
        candidate = candidates.iloc[0]
        return pd.DataFrame(
            [
                {
                    "source_event_id": f"{trade_date}-event",
                    "source_name": "eastmoney_individual_notice",
                    "source_channel": "eastmoney_notice",
                    "event_family": "disclosure_notice",
                    "asset_id": candidate["asset_id"],
                    "ts_code": candidate["ts_code"],
                    "stock_name": candidate["stock_name"],
                    "title": f"{candidate['stock_name']} 公告",
                    "content": "",
                    "published_at": f"{trade_date} 09:00:00",
                    "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                    "language": "zh",
                    "url": None,
                    "hash_key": f"{trade_date}-hash",
                    "source_status": "available",
                    "metadata": {
                        "matched_candidates": [
                            {
                                "asset_id": candidate["asset_id"],
                                "ts_code": candidate["ts_code"],
                                "stock_name": candidate["stock_name"],
                            }
                        ]
                    },
                }
            ]
        )

    monkeypatch.setattr("stock_research.news_source_backfill.connect", lambda *args, **kwargs: _FakeConnection())
    monkeypatch.setattr("stock_research.news_source_backfill.fetch_all", _fake_fetch_all)
    monkeypatch.setattr(
        "stock_research.news_source_backfill._collect_topn_news_source_events_for_candidates",
        _fake_collect,
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-06",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert "asset_id" in str(captured["sql"])
    assert captured["params"] == (["600066.SH"], ["CN:SH:600066"])
    assert result["candidates"].iloc[0]["stock_name"] == "宇通客车"
    assert result["source_events"].iloc[0]["stock_name"] == "宇通客车"
    assert result["enrichment"].iloc[0]["stock_name"] == "宇通客车"


def test_run_historical_top10_news_backfill_fills_nan_stock_name_from_asset_id_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": pd.NA,
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"CN:SH:600066": "宇通客车"},
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._collect_topn_news_source_events_for_candidates",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "source_event_id": "2025-01-06-event",
                    "source_name": "eastmoney_individual_notice",
                    "source_channel": "eastmoney_notice",
                    "event_family": "disclosure_notice",
                    "asset_id": "CN:SH:600066",
                    "ts_code": "600066.SH",
                    "stock_name": kwargs["candidates"].iloc[0]["stock_name"],
                    "title": "宇通客车 公告",
                    "content": "",
                    "published_at": "2025-01-06 09:00:00",
                    "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                    "language": "zh",
                    "url": None,
                    "hash_key": "2025-01-06-hash",
                    "source_status": "available",
                    "metadata": {
                        "matched_candidates": [
                            {
                                "asset_id": "CN:SH:600066",
                                "ts_code": "600066.SH",
                                "stock_name": kwargs["candidates"].iloc[0]["stock_name"],
                            }
                        ]
                    },
                }
            ]
        ),
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-06",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert result["candidates"].iloc[0]["stock_name"] == "宇通客车"
    assert result["source_events"].iloc[0]["stock_name"] == "宇通客车"
    assert result["enrichment"].iloc[0]["stock_name"] == "宇通客车"


def test_run_historical_top10_news_backfill_fills_textual_nan_stock_name_from_asset_id_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SH:600066",
                "ts_code": "600066.SH",
                "stock_name": " nan ",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_topn_stock_name_lookup",
        lambda *, ts_codes: {"CN:SH:600066": "宇通客车"},
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill._collect_topn_news_source_events_for_candidates",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "source_event_id": "2025-01-06-event",
                    "source_name": "eastmoney_individual_notice",
                    "source_channel": "eastmoney_notice",
                    "event_family": "disclosure_notice",
                    "asset_id": "CN:SH:600066",
                    "ts_code": "600066.SH",
                    "stock_name": kwargs["candidates"].iloc[0]["stock_name"],
                    "title": "宇通客车 公告",
                    "content": "",
                    "published_at": "2025-01-06 09:00:00",
                    "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                    "language": "zh",
                    "url": None,
                    "hash_key": "2025-01-06-hash",
                    "source_status": "available",
                    "metadata": {
                        "matched_candidates": [
                            {
                                "asset_id": "CN:SH:600066",
                                "ts_code": "600066.SH",
                                "stock_name": kwargs["candidates"].iloc[0]["stock_name"],
                            }
                        ]
                    },
                }
            ]
        ),
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-06",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    assert result["candidates"].iloc[0]["stock_name"] == "宇通客车"
    assert result["source_events"].iloc[0]["stock_name"] == "宇通客车"
    assert result["enrichment"].iloc[0]["stock_name"] == "宇通客车"


def test_historical_top10_news_backfill_cli_prints_paths_and_rows(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        "stock_research.cli.run_historical_top10_news_backfill",
        lambda **kwargs: recorded.update(kwargs) or {
            "paths": {
                "candidates": str(tmp_path / "historical_top10_candidates.csv"),
                "source_events": str(tmp_path / "historical_news_source_events.csv"),
            },
            "source_events": pd.DataFrame([{"source_event_id": "n1"}, {"source_event_id": "n2"}]),
        },
    )

    cli.main_for_args(
        [
            "historical-top10-news-backfill",
            "--top10-path",
            str(tmp_path / "top10.csv"),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-06",
        ]
    )

    output = capsys.readouterr().out
    assert recorded["providers"] == [
        "eastmoney_individual_notice",
        "eastmoney_research_report",
    ]
    assert "historical_top10_news_backfill|candidates|" in output
    assert "historical_top10_news_backfill|source_events|" in output
    assert "historical_top10_news_backfill|source_rows|2" in output


def test_historical_top10_news_backfill_cli_accepts_multiple_providers(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        "stock_research.cli.run_historical_top10_news_backfill",
        lambda **kwargs: recorded.update(kwargs)
        or {
            "paths": {
                "candidates": str(tmp_path / "historical_top10_candidates.csv"),
                "source_events": str(tmp_path / "historical_news_source_events.csv"),
            },
            "source_events": pd.DataFrame([{"source_event_id": "n1"}]),
        },
    )

    cli.main_for_args(
        [
            "historical-top10-news-backfill",
            "--top10-path",
            str(tmp_path / "top10.csv"),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-06",
            "--providers",
            "eastmoney_individual_notice",
            "eastmoney_research_report",
            "cninfo_disclosure_announcement",
        ]
    )

    output = capsys.readouterr().out
    assert recorded["providers"] == [
        "eastmoney_individual_notice",
        "eastmoney_research_report",
        "cninfo_disclosure_announcement",
    ]
    assert "historical_top10_news_backfill|source_rows|1" in output


def test_run_historical_top10_news_backfill_writes_summary_and_report(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
            },
        ]
    )
    source_events = pd.DataFrame(
        [
            {
                "source_event_id": "2025-01-03-event",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "生益科技 主力资金抢筹 券商推荐",
                "content": "正文",
                "published_at": "2025-01-03 09:00:00",
                "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                "language": "zh",
                "url": None,
                "hash_key": "hash-1",
                "source_status": "available",
                "metadata": {
                    "matched_candidates": [
                        {
                            "asset_id": "CN:SH:600183",
                            "ts_code": "600183.SH",
                            "stock_name": "生益科技",
                        }
                    ]
                },
            },
            {
                "source_event_id": "2025-01-06-event",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "海伦哲 风险提示",
                "content": "正文",
                "published_at": "2025-01-06 09:00:00",
                "collected_at": pd.Timestamp("2026-06-06T00:00:00Z"),
                "language": "zh",
                "url": None,
                "hash_key": "hash-2",
                "source_status": "available",
                "metadata": {
                    "matched_candidates": [
                        {
                            "asset_id": "CN:SZ:300201",
                            "ts_code": "300201.SZ",
                            "stock_name": "海伦哲",
                        }
                    ]
                },
            },
        ]
    )
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "2025-01-03-event",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "title",
                "trade_date": "2025-01-03",
                "published_at": "2025-01-03 09:00:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "生益科技 主力资金抢筹 券商推荐",
                "content": "正文",
            },
            {
                "source_event_id": "2025-01-06-event",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "mapping_method": "title",
                "trade_date": "2025-01-06",
                "published_at": "2025-01-06 09:00:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "东方财富",
                "title": "海伦哲 风险提示",
                "content": "正文",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "high",
                "headline_main_force_flow_count_3d": 1,
                "headline_gold_stock_count_3d": 1,
                "headline_keyword_positive_count_3d": 1,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 1,
                "overnight_news_count": 0,
                "news_compact_summary": "近3日主力资金关注 + 券商金股推荐共振",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "news_attention_level": "low",
                "headline_risk_event_count_3d": 1,
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "news_compact_summary": "近3日风险事件类新闻1条但无新增催化",
            },
        ]
    )
    enrichment = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "news_consensus_summary": "近3日券商推荐类新闻1条，关注度high",
                "news_risk_summary": "",
                "news_compact_summary": "近3日主力资金关注 + 券商金股推荐共振",
                "theme_catalyst_summary": "近3日经营/主题催化新闻1条",
                "overnight_catalyst_note": "",
                "news_attention_level": "high",
                "news_risk_attention_flag": False,
                "news_enrichment_quality_flag": "rich",
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "news_consensus_summary": "",
                "news_risk_summary": "近3日风险事件类新闻1条",
                "news_compact_summary": "近3日风险事件类新闻1条但无新增催化",
                "theme_catalyst_summary": "",
                "overnight_catalyst_note": "",
                "news_attention_level": "low",
                "news_risk_attention_flag": True,
                "news_enrichment_quality_flag": "medium",
            },
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )
    def _fake_collect(**kwargs):
        trade_date = kwargs["trade_date"]
        return source_events.loc[
            source_events["published_at"].str.startswith(trade_date)
        ].reset_index(drop=True)

    monkeypatch.setattr(
        "stock_research.news_source_backfill._collect_topn_news_source_events_for_candidates",
        _fake_collect,
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.map_news_mentions",
        lambda **kwargs: mentions.copy(),
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_news_feature_daily",
        lambda **kwargs: features.copy(),
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_topn_news_enrichment",
        lambda **kwargs: enrichment.copy(),
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-03",
        end_date="2025-01-06",
        provider="akshare_stock_news_em",
        output_dir=tmp_path / "out",
    )

    summary_path = Path(result["paths"]["summary"])
    report_path = Path(result["paths"]["report"])
    assert summary_path.exists()
    assert report_path.exists()

    summary = pd.read_csv(summary_path)
    assert summary.loc[0, "trade_date_count"] == 2
    assert summary.loc[0, "candidate_rows"] == 2
    assert summary.loc[0, "source_event_rows"] == 2
    assert summary.loc[0, "mention_rows"] == 2
    assert summary.loc[0, "feature_rows"] == 2
    assert summary.loc[0, "enrichment_rows"] == 2
    assert summary.loc[0, "coverage_rows"] == 2
    assert summary.loc[0, "coverage_rate"] == 1.0
    assert summary.loc[0, "compact_summary_nonempty_rows"] == 2
    assert summary.loc[0, "capital_broker_resonance_rows"] == 1
    assert summary.loc[0, "risk_without_catalyst_rows"] == 1

    report = report_path.read_text(encoding="utf-8")
    assert "# Historical Top10 News Backfill Report" in report
    assert "trade_date_count: 2" in report
    assert "capital_broker_resonance_rows: 1" in report
    assert "risk_without_catalyst_rows: 1" in report


def test_run_historical_top10_news_backfill_summary_reports_nonzero_replacement_source_rows(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    def _fake_fetch_historical_provider_rows(
        *,
        provider,
        symbol,
        ts_code,
        stock_name,
        start_date,
        end_date,
    ):
        if provider == "eastmoney_individual_notice":
            return [
                {
                    "source_event_id": "notice-1",
                    "source_name": "eastmoney_individual_notice",
                    "source_channel": "eastmoney_notice",
                    "event_family": "disclosure_notice",
                    "title": "生益科技:2024年年度业绩预增公告",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "https://data.eastmoney.com/notices/detail/600183/AN1.html",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        if provider == "eastmoney_research_report":
            return [
                {
                    "source_event_id": "report-1",
                    "source_name": "eastmoney_research_report",
                    "source_channel": "eastmoney_research",
                    "event_family": "institution_report",
                    "title": "产品结构优化，业绩爆发式增长",
                    "content": "",
                    "published_at": "2025-01-24 00:00:00",
                    "language": "zh",
                    "url": "https://pdf.dfcfw.com/pdf/abc.pdf",
                    "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
                }
            ]
        return []

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_provider_rows",
        _fake_fetch_historical_provider_rows,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-24",
        end_date="2025-01-24",
        providers=["eastmoney_individual_notice", "eastmoney_research_report"],
        output_dir=tmp_path / "out",
    )

    summary_path = Path(result["paths"]["summary"])
    report_path = Path(result["paths"]["report"])
    summary = pd.read_csv(summary_path)

    assert int(summary.loc[0, "source_event_rows"]) == 2
    assert int(summary.loc[0, "mention_rows"]) == 2
    assert int(summary.loc[0, "feature_rows"]) == 1
    assert int(summary.loc[0, "enrichment_rows"]) == 1
    assert int(summary.loc[0, "coverage_rows"]) == 1
    assert summary.loc[0, "coverage_rate"] == 1.0

    report = report_path.read_text(encoding="utf-8")
    assert "- source_event_rows: 2" in report
    assert "- mention_rows: 2" in report
    assert "- feature_rows: 1" in report
    assert "- enrichment_rows: 1" in report


def test_run_historical_top10_news_backfill_defaults_to_replacement_providers(
    tmp_path,
    monkeypatch,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )

    monkeypatch.setattr(
        "stock_research.news_source_backfill._load_historical_top10_candidates",
        lambda **kwargs: candidates.copy(),
    )

    fetch_calls: list[str] = []

    def _fake_fetch_historical_provider_rows(
        *,
        provider,
        symbol,
        ts_code,
        stock_name,
        start_date,
        end_date,
    ):
        fetch_calls.append(provider)
        return [
            {
                "source_event_id": f"{provider}-1",
                "source_name": provider,
                "source_channel": provider,
                "event_family": "disclosure_notice" if provider == "eastmoney_individual_notice" else "institution_report",
                "title": f"{provider} title",
                "content": "",
                "published_at": "2025-01-24 00:00:00",
                "language": "zh",
                "url": "",
                "metadata": {"provider": provider, "ts_code": ts_code, "stock_name": stock_name},
            }
        ]

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_provider_rows",
        _fake_fetch_historical_provider_rows,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.map_news_mentions",
        lambda **kwargs: pd.DataFrame([{"mention": 1}]),
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_news_feature_daily",
        lambda **kwargs: pd.DataFrame([{"feature": 1}]),
        raising=False,
    )
    monkeypatch.setattr(
        "stock_research.news_source_backfill.build_topn_news_enrichment",
        lambda **kwargs: pd.DataFrame([{"enrichment": 1}]),
        raising=False,
    )

    result = run_historical_top10_news_backfill(
        top10_path=tmp_path / "top10.csv",
        start_date="2025-01-24",
        end_date="2025-01-24",
        output_dir=tmp_path / "out",
    )

    assert fetch_calls == [
        "eastmoney_individual_notice",
        "eastmoney_research_report",
    ]
    assert int(pd.read_csv(result["paths"]["summary"]).loc[0, "source_event_rows"]) == 2


def test_topn_news_source_backfill_cli_rejects_unimplemented_cninfo_provider(tmp_path, monkeypatch) -> None:
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    ).to_csv(candidates_path, index=False)
    monkeypatch.setattr(
        "stock_research.cli.run_topn_news_source_backfill",
        lambda **kwargs: {"events": pd.DataFrame(), "paths": {"events": "", "report": ""}},
    )

    with pytest.raises(SystemExit):
        cli.main_for_args(
            [
                "topn-news-source-backfill",
                "--candidates-path",
                str(candidates_path),
                "--provider",
                "cninfo_announcement",
                "--trade-date",
                "2026-06-02",
            ]
        )
