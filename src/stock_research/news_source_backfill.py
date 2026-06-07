import hashlib
import re
import warnings
from pathlib import Path

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.news_features import build_news_feature_daily, map_news_mentions
from stock_research.topn_news_enrichment import build_topn_news_enrichment

try:
    import akshare as ak
except ImportError:  # pragma: no cover - optional dependency in tests/runtime
    ak = None


NEWS_SOURCE_COLUMNS = [
    "source_event_id",
    "source_name",
    "source_channel",
    "event_family",
    "asset_id",
    "ts_code",
    "stock_name",
    "title",
    "content",
    "published_at",
    "collected_at",
    "language",
    "url",
    "hash_key",
    "source_status",
    "metadata",
]

DEFAULT_TUSHARE_NEWS_SRC = "sina"
AKSHARE_STOCK_NEWS_PROVIDER = "akshare_stock_news_em"
AKSHARE_STOCK_NEWS_CHANNEL = "eastmoney_stock_news"
DEFAULT_HISTORICAL_REPLACEMENT_PROVIDERS = (
    "eastmoney_individual_notice",
    "eastmoney_research_report",
)
HISTORICAL_TOP10_NEWS_PROVIDERS = (
    "eastmoney_individual_notice",
    "eastmoney_research_report",
    "cninfo_disclosure_announcement",
)


def normalize_news_source_rows(rows: list[dict], *, source_status: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=NEWS_SOURCE_COLUMNS)

    frame["title"] = frame["title"].fillna("").astype(str).str.strip()
    frame["event_family"] = (
        frame.get("event_family", pd.Series(index=frame.index, dtype="object"))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")
    frame = frame.loc[frame["published_at"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=NEWS_SOURCE_COLUMNS)
    frame["collected_at"] = pd.Timestamp.now(tz="UTC")
    frame["language"] = (
        frame.get("language", pd.Series(index=frame.index, dtype="object"))
        .fillna("zh")
        .astype(str)
        .str.strip()
        .replace("", "zh")
    )
    frame["metadata"] = frame.get(
        "metadata",
        pd.Series([{} for _ in range(len(frame))], index=frame.index, dtype="object"),
    ).apply(lambda value: value if isinstance(value, dict) else {})
    frame["source_status"] = source_status
    frame["hash_key"] = (
        frame["source_name"].fillna("").astype(str)
        + "|"
        + frame["title"]
        + "|"
        + frame["published_at"].astype(str)
    ).map(lambda text: hashlib.sha1(text.encode("utf-8")).hexdigest())
    frame = frame.drop_duplicates(subset=["source_event_id"], keep="last").reset_index(drop=True)
    return frame.reindex(columns=NEWS_SOURCE_COLUMNS)


def normalize_historical_source_rows(
    *,
    rows: list[dict[str, object]],
    provider: str,
    asset_id: str,
    ts_code: str,
    stock_name: str,
) -> pd.DataFrame:
    provider_map = {
        "eastmoney_individual_notice": _build_eastmoney_individual_notice_rows,
        "eastmoney_research_report": _build_eastmoney_research_report_rows,
        "cninfo_disclosure_announcement": _build_cninfo_disclosure_announcement_rows,
    }
    try:
        builder = provider_map[provider]
    except KeyError as exc:
        raise ValueError(f"unsupported provider: {provider}") from exc

    normalized_rows = builder(
        rows=rows,
        asset_id=asset_id,
        ts_code=ts_code,
        stock_name=stock_name,
    )
    return normalize_news_source_rows(normalized_rows, source_status="available")


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _normalize_provider_list(
    *,
    provider: str | None = None,
    providers: list[str] | None = None,
) -> list[str]:
    if providers is not None:
        normalized = [str(item).strip() for item in providers if str(item).strip()]
        if not normalized:
            raise ValueError("providers must contain at least one provider")
        return normalized
    if provider is None:
        return [AKSHARE_STOCK_NEWS_PROVIDER]
    normalized_provider = str(provider).strip()
    if not normalized_provider:
        raise ValueError("provider must be a non-empty string")
    return [normalized_provider]


def _asset_id_from_ts_code(ts_code: str) -> str:
    normalized_ts_code = _normalize_topn_ts_code(ts_code)
    if not normalized_ts_code:
        return ""
    symbol, market = normalized_ts_code.split(".")
    market_map = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}
    normalized_market = market_map.get(market, market)
    return f"CN:{normalized_market}:{symbol}"


def _frame_records(frame: pd.DataFrame | None) -> list[dict[str, object]]:
    if frame is None or frame.empty:
        return []
    return [dict(row) for row in frame.to_dict(orient="records")]


def _is_cninfo_empty_result_keyerror(exc: KeyError) -> bool:
    message = str(exc)
    return all(
        token in message
        for token in (
            "None of [Index([",
            "代码",
            "简称",
            "公告标题",
            "公告时间",
            "announcementId",
            "orgId",
            "are in the [columns]",
        )
    )


def _date_compact(value: str) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return ""
    return pd.Timestamp(timestamp).strftime("%Y%m%d")


def _first_text(*values: object) -> str:
    for value in values:
        text = _coerce_text(value)
        if text:
            return text
    return ""


def _build_stable_source_event_id(
    *,
    provider: str,
    ts_code: str,
    title: str,
    published_at: str,
    url: str,
) -> str:
    normalized_ts_code = str(ts_code or "").strip().upper()
    return hashlib.sha1(
        f"{provider}|{normalized_ts_code}|{title}|{published_at}|{url}".encode("utf-8")
    ).hexdigest()


def _normalize_published_at_for_hash(value: object) -> str:
    published_at = pd.to_datetime(value, errors="coerce")
    if pd.isna(published_at):
        return ""
    timestamp = pd.Timestamp(published_at)
    if timestamp.tzinfo is None or timestamp.tz is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S")


def _build_eastmoney_individual_notice_rows(
    *,
    rows: list[dict[str, object]],
    asset_id: str,
    ts_code: str,
    stock_name: str,
) -> list[dict]:
    normalized_rows: list[dict] = []
    for row in rows:
        published_at = _first_text(row.get("公告日期"), row.get("日期"))
        published_at_for_hash = _normalize_published_at_for_hash(
            row.get("公告日期") if _coerce_text(row.get("公告日期")) else row.get("日期")
        )
        title = _first_text(row.get("公告标题"), row.get("标题"))
        url = _first_text(row.get("网址"), row.get("公告链接"))
        source_event_id = url
        if not source_event_id:
            source_event_id = _build_stable_source_event_id(
                provider="eastmoney_individual_notice",
                ts_code=ts_code,
                title=title,
                published_at=published_at_for_hash,
                url=url,
            )
        normalized_rows.append(
            {
                "source_event_id": str(source_event_id),
                "source_name": "eastmoney_individual_notice",
                "source_channel": "eastmoney_notice",
                "event_family": "disclosure_notice",
                "asset_id": asset_id,
                "ts_code": ts_code,
                "stock_name": stock_name,
                "title": title,
                "content": "",
                "published_at": published_at,
                "language": "zh",
                "url": url or None,
                "metadata": {
                    "provider": "eastmoney_individual_notice",
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "raw": row,
                },
            }
        )
    return normalized_rows


def _build_eastmoney_research_report_rows(
    *,
    rows: list[dict[str, object]],
    asset_id: str,
    ts_code: str,
    stock_name: str,
) -> list[dict]:
    normalized_rows: list[dict] = []
    for row in rows:
        published_at = _first_text(row.get("日期"), row.get("报告日期"))
        published_at_for_hash = _normalize_published_at_for_hash(
            row.get("日期") if _coerce_text(row.get("日期")) else row.get("报告日期")
        )
        title = _first_text(row.get("报告名称"), row.get("标题"))
        url = _first_text(row.get("报告PDF链接"), row.get("报告链接"))
        source_event_id = url
        if not source_event_id:
            source_event_id = _build_stable_source_event_id(
                provider="eastmoney_research_report",
                ts_code=ts_code,
                title=title,
                published_at=published_at_for_hash,
                url=url,
            )
        normalized_rows.append(
            {
                "source_event_id": str(source_event_id),
                "source_name": "eastmoney_research_report",
                "source_channel": "eastmoney_research",
                "event_family": "institution_report",
                "asset_id": asset_id,
                "ts_code": ts_code,
                "stock_name": stock_name,
                "title": title,
                "content": "",
                "published_at": published_at,
                "language": "zh",
                "url": url or None,
                "metadata": {
                    "provider": "eastmoney_research_report",
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "raw": row,
                },
            }
        )
    return normalized_rows


def _build_cninfo_disclosure_announcement_rows(
    *,
    rows: list[dict[str, object]],
    asset_id: str,
    ts_code: str,
    stock_name: str,
) -> list[dict]:
    normalized_rows: list[dict] = []
    for row in rows:
        published_at = _first_text(row.get("公告时间"), row.get("发布时间"))
        published_at_for_hash = _normalize_published_at_for_hash(
            row.get("公告时间") if _coerce_text(row.get("公告时间")) else row.get("发布时间")
        )
        title = _first_text(row.get("公告标题"), row.get("公告名称"))
        url = _first_text(row.get("公告链接"), row.get("网址"))
        source_event_id = url
        if not source_event_id:
            source_event_id = _build_stable_source_event_id(
                provider="cninfo_disclosure_announcement",
                ts_code=ts_code,
                title=title,
                published_at=published_at_for_hash,
                url=url,
            )
        normalized_rows.append(
            {
                "source_event_id": str(source_event_id),
                "source_name": "cninfo_disclosure_announcement",
                "source_channel": "cninfo_disclosure",
                "event_family": "disclosure_notice",
                "asset_id": asset_id,
                "ts_code": ts_code,
                "stock_name": stock_name,
                "title": title,
                "content": "",
                "published_at": published_at,
                "language": "zh",
                "url": url or None,
                "metadata": {
                    "provider": "cninfo_disclosure_announcement",
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "raw": row,
                },
            }
        )
    return normalized_rows


def _fetch_eastmoney_individual_notice_rows(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    if ak is None:
        raise RuntimeError("akshare is not installed")

    frame = ak.stock_individual_notice_report(
        security=symbol,
        symbol="全部",
        begin_date=_date_compact(start_date) or None,
        end_date=_date_compact(end_date) or None,
    )
    return _frame_records(frame)


def _fetch_eastmoney_research_report_rows(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    if ak is None:
        raise RuntimeError("akshare is not installed")

    frame = ak.stock_research_report_em(symbol=symbol)
    return _frame_records(frame)


def _fetch_cninfo_disclosure_announcement_rows(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    if ak is None:
        raise RuntimeError("akshare is not installed")

    try:
        frame = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=symbol,
            market="沪深京",
            start_date=_date_compact(start_date) or None,
            end_date=_date_compact(end_date) or None,
        )
    except KeyError as exc:
        if _is_cninfo_empty_result_keyerror(exc):
            return []
        raise
    return _frame_records(frame)


def fetch_historical_provider_rows(
    *,
    provider: str,
    symbol: str,
    ts_code: str,
    stock_name: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    provider_map = {
        "eastmoney_individual_notice": _fetch_eastmoney_individual_notice_rows,
        "eastmoney_research_report": _fetch_eastmoney_research_report_rows,
        "cninfo_disclosure_announcement": _fetch_cninfo_disclosure_announcement_rows,
    }
    try:
        fetcher = provider_map[provider]
    except KeyError as exc:
        raise ValueError(f"unsupported historical provider: {provider}") from exc

    rows = fetcher(symbol=symbol, start_date=start_date, end_date=end_date)
    if not rows:
        return []

    asset_id = _asset_id_from_ts_code(ts_code)
    events = normalize_historical_source_rows(
        rows=rows,
        provider=provider,
        asset_id=asset_id,
        ts_code=ts_code,
        stock_name=stock_name,
    )
    return _filter_rows_by_window(
        events.to_dict(orient="records"),
        start_date=start_date,
        end_date=end_date,
    )


def build_tushare_news_client(token: str | None = None):
    import tushare as ts

    if token:
        ts.set_token(token)
    return ts.pro_api(token) if token else ts.pro_api()


def _format_tushare_news_datetime(value: str, *, is_end: bool) -> str:
    text = str(value).strip()
    if " " in text:
        return text
    suffix = "23:59:59" if is_end else "00:00:00"
    return f"{text} {suffix}"


def _window_bounds(*, start_date: str, end_date: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    return (
        pd.Timestamp(_format_tushare_news_datetime(start_date, is_end=False)),
        pd.Timestamp(_format_tushare_news_datetime(end_date, is_end=True)),
    )


def _filter_rows_by_window(rows: list[dict], *, start_date: str, end_date: str) -> list[dict]:
    if not rows:
        return rows

    start_ts, end_ts = _window_bounds(start_date=start_date, end_date=end_date)
    kept_rows: list[dict] = []
    for row in rows:
        published_at = pd.to_datetime(row.get("published_at"), errors="coerce")
        if pd.isna(published_at):
            continue
        if start_ts <= published_at <= end_ts:
            kept_rows.append(row)
    return kept_rows


def _fetch_akshare_stock_news_rows(symbol: str, *, start_date: str, end_date: str) -> list[dict]:
    if ak is None:
        raise RuntimeError("akshare is not installed")

    frame = ak.stock_news_em(symbol=symbol)
    if frame is None or frame.empty:
        return []

    rows: list[dict] = []
    for row in frame.to_dict(orient="records"):
        title = row.get("新闻标题")
        published_at = row.get("发布时间")
        raw_url = row.get("新闻链接")
        url = None if pd.isna(raw_url) else raw_url
        article_source = row.get("文章来源") or AKSHARE_STOCK_NEWS_CHANNEL
        source_event_id = url or hashlib.sha1(
            f"{AKSHARE_STOCK_NEWS_PROVIDER}|{article_source}|{title or ''}|{published_at or ''}|{url or ''}".encode(
                "utf-8"
            )
        ).hexdigest()
        rows.append(
            {
                "source_event_id": source_event_id,
                "source_name": AKSHARE_STOCK_NEWS_PROVIDER,
                "source_channel": article_source,
                "title": title,
                "content": row.get("新闻内容"),
                "published_at": published_at,
                "language": "zh",
                "url": url,
                "metadata": {"provider": AKSHARE_STOCK_NEWS_PROVIDER, "raw": row},
            }
        )
    return _filter_rows_by_window(rows, start_date=start_date, end_date=end_date)


def _fetch_cninfo_announcement_rows(
    *, ts_code: str, stock_name: str | None, start_date: str, end_date: str
) -> list[dict]:
    raise RuntimeError("cninfo_announcement provider is not implemented yet")


def fetch_news_rows(
    *,
    start_date: str,
    end_date: str,
    provider: str = "tushare",
    token: str | None = None,
    symbol: str | None = None,
    ts_code: str | None = None,
    stock_name: str | None = None,
) -> list[dict]:
    if provider == AKSHARE_STOCK_NEWS_PROVIDER:
        if not symbol:
            raise ValueError("symbol is required for akshare_stock_news_em")
        return _fetch_akshare_stock_news_rows(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )

    if provider == "cninfo_announcement":
        if not ts_code:
            raise ValueError("ts_code is required for cninfo_announcement")
        return _fetch_cninfo_announcement_rows(
            ts_code=ts_code,
            stock_name=stock_name,
            start_date=start_date,
            end_date=end_date,
        )

    if provider != "tushare":
        raise ValueError(f"unsupported provider: {provider}")

    client = build_tushare_news_client(token=token)
    frame = client.news(
        src=DEFAULT_TUSHARE_NEWS_SRC,
        start_date=_format_tushare_news_datetime(start_date, is_end=False),
        end_date=_format_tushare_news_datetime(end_date, is_end=True),
    )
    if frame is None or frame.empty:
        return []

    rows: list[dict] = []
    for row in frame.to_dict(orient="records"):
        title = row.get("title")
        content = row.get("content")
        published_at = row.get("datetime") or row.get("pub_time") or row.get("published_at")
        source_name = row.get("src") or row.get("source_name") or "tushare_news"
        source_channel = row.get("channels") or row.get("source_channel") or provider
        source_event_id = row.get("news_id") or row.get("id") or row.get("source_event_id")
        if source_event_id is None and published_at is not None:
            source_event_id = hashlib.sha1(
                f"{source_name}|{title or ''}|{published_at}".encode("utf-8")
            ).hexdigest()
        rows.append(
            {
                "source_event_id": source_event_id,
                "source_name": source_name,
                "source_channel": source_channel,
                "title": title,
                "content": content,
                "published_at": published_at,
                "language": row.get("language") or "zh",
                "url": row.get("url") or row.get("uri"),
                "metadata": {"provider": provider, "raw": row},
            }
        )
    return rows


def _is_permission_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "permission" in text
        or "denied" in text
        or "权限" in text
        or "token" in text
        or "api init error" in text
        or "凭证码" in text
    )


def _default_output_dir(*, start_date: str, end_date: str) -> Path:
    return Path("outputs/research") / f"news_source_backfill_{start_date}_{end_date}"


def _default_topn_output_dir(*, trade_date: str) -> Path:
    return Path("outputs/research") / f"topn_news_source_backfill_{trade_date}"


def _load_historical_top10_candidates(
    *,
    top10_path: str | Path,
    start_date: str,
    end_date: str,
    sample_trade_dates: int | None = None,
) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", "ts_code", "stock_name"]
    frame = pd.read_csv(top10_path, low_memory=False)
    if frame.empty or any(column not in frame.columns for column in columns):
        return pd.DataFrame(columns=columns)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    frame = frame.loc[frame["trade_date"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    start_ts = pd.to_datetime(start_date, errors="coerce")
    end_ts = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return pd.DataFrame(columns=columns)

    start_day = start_ts.date()
    end_day = end_ts.date()
    frame = frame.loc[(frame["trade_date"] >= start_day) & (frame["trade_date"] <= end_day)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["ts_code"] = frame.get("ts_code", pd.Series(index=frame.index, dtype="object")).map(
        _normalize_topn_ts_code
    )
    frame = frame.loc[frame["ts_code"] != ""].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    if sample_trade_dates is not None:
        if sample_trade_dates <= 0:
            return pd.DataFrame(columns=columns)
        allowed_dates = sorted(frame["trade_date"].dropna().unique())[:sample_trade_dates]
        frame = frame.loc[frame["trade_date"].isin(allowed_dates)].copy()
        if frame.empty:
            return pd.DataFrame(columns=columns)

    frame = frame.reindex(columns=columns).reset_index(drop=True)
    return frame


def _ts_code_to_symbol(ts_code: str) -> str:
    return str(ts_code).split(".")[0].strip()


def _normalize_topn_ts_code(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text or text == "NAN":
        return ""
    if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", text):
        return ""
    return text


def _normalize_topn_stock_name_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in {"nan", "none"}:
        return ""
    return text


def _is_placeholder_stock_name(name: object, *, asset_id: object, ts_code: object) -> bool:
    text = _normalize_topn_stock_name_text(name).upper()
    if not text:
        return True
    normalized_ts_code = _normalize_topn_ts_code(ts_code)
    normalized_asset_id = str(asset_id or "").strip().upper()
    asset_code = normalized_asset_id.split(":")[-1]
    symbol = normalized_ts_code.split(".")[0] if normalized_ts_code else ""
    return text in {normalized_ts_code, symbol, asset_code, normalized_asset_id}


def _resolve_topn_stock_name(
    *,
    current_name: object,
    asset_id: object,
    ts_code: object,
    lookup: dict[str, str],
) -> str:
    normalized_ts_code = str(ts_code or "").strip().upper()
    normalized_asset_id = str(asset_id or "").strip().upper()
    current = _normalize_topn_stock_name_text(current_name)
    if current and not _is_placeholder_stock_name(current, asset_id=asset_id, ts_code=normalized_ts_code):
        return current
    return (
        lookup.get(normalized_ts_code)
        or lookup.get(normalized_asset_id)
        or current
    )


def _load_topn_stock_name_lookup(*, ts_codes: list[str]) -> dict[str, str]:
    if not ts_codes:
        return {}
    wanted = {str(code).strip().upper() for code in ts_codes if str(code).strip()}
    if not wanted:
        return {}
    wanted_asset_ids = {_asset_id_from_ts_code(ts_code) for ts_code in wanted}
    wanted_asset_ids.discard("")
    sql = """
        SELECT asset_id, ts_code, name AS stock_name
        FROM core.asset_master
        WHERE (ts_code = ANY(%s) OR asset_id = ANY(%s))
          AND name IS NOT NULL
          AND name <> ''
    """
    try:
        with connect(SETTINGS.research_service) as conn:
            rows = fetch_all(conn, sql, (sorted(wanted), sorted(wanted_asset_ids)))
    except Exception as exc:
        warnings.warn(
            f"TopN stock name lookup unavailable; using candidate names. reason={exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}
    lookup: dict[str, str] = {}
    for row in rows:
        ts_code = _normalize_topn_ts_code(row.get("ts_code"))
        asset_id = str(row.get("asset_id") or "").strip().upper()
        stock_name = _normalize_topn_stock_name_text(row.get("stock_name"))
        if ts_code and stock_name and not _is_placeholder_stock_name(
            stock_name,
            asset_id=asset_id,
            ts_code=ts_code,
        ):
            lookup.setdefault(ts_code, stock_name)
        if asset_id and stock_name and not _is_placeholder_stock_name(
            stock_name,
            asset_id=asset_id,
            ts_code=ts_code,
        ):
            lookup.setdefault(asset_id, stock_name)
    return lookup


def _normalize_topn_candidate_stock_names(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "ts_code" not in frame.columns or "stock_name" not in frame.columns:
        return frame.copy()

    normalized = frame.copy()
    normalized["ts_code"] = normalized["ts_code"].fillna("").map(_normalize_topn_ts_code)
    lookup = _load_topn_stock_name_lookup(ts_codes=normalized["ts_code"].tolist())
    normalized["stock_name"] = normalized.apply(
        lambda row: _resolve_topn_stock_name(
            current_name=row.get("stock_name"),
            asset_id=row.get("asset_id"),
            ts_code=row.get("ts_code"),
            lookup=lookup,
        ),
        axis=1,
    )
    return normalized


def _candidate_context_from_row(row: dict) -> dict[str, str]:
    return {
        "asset_id": row["asset_id"],
        "ts_code": row["ts_code"],
        "stock_name": row["stock_name"],
    }


def _aggregate_topn_event_rows(event_rows: list[dict]) -> list[dict]:
    aggregated: dict[str, dict] = {}
    candidate_seen_by_event: dict[str, set[tuple[str, str, str]]] = {}
    for row in event_rows:
        source_event_id = row["source_event_id"]
        metadata = dict(row.get("metadata") or {})
        matched_candidates = list(metadata.get("matched_candidates") or [])
        base_row = aggregated.setdefault(source_event_id, {**row, "metadata": {**metadata, "matched_candidates": []}})
        seen = candidate_seen_by_event.setdefault(source_event_id, set())
        for candidate in matched_candidates:
            candidate_key = (
                str(candidate.get("asset_id", "")),
                str(candidate.get("ts_code", "")),
                str(candidate.get("stock_name", "")),
            )
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            base_row["metadata"]["matched_candidates"].append(candidate)
    return list(aggregated.values())


def _write_news_source_backfill_report(*, output_dir: Path, events: pd.DataFrame, source_status: str) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "events": str(output_dir / "news_source_backfill_events.csv"),
        "report": str(output_dir / "news_source_backfill_report.md"),
    }
    events.to_csv(paths["events"], index=False)
    report_lines = [
        "# News Source Backfill Report",
        "",
        f"- source_status: {source_status}",
        f"- event_rows: {len(events)}",
    ]
    Path(paths["report"]).write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return paths


def _collect_topn_news_source_events_for_candidates(
    *,
    candidates: pd.DataFrame,
    provider: str | None = None,
    providers: list[str] | None = None,
    trade_date: str,
    fetch_start_date: str | None = None,
) -> pd.DataFrame:
    frame = candidates.copy()
    if frame.empty:
        return normalize_news_source_rows([], source_status="available")

    frame["ts_code"] = frame.get("ts_code", pd.Series(index=frame.index, dtype="object")).map(
        _normalize_topn_ts_code
    )
    frame = frame.loc[frame["ts_code"] != ""].copy()
    if frame.empty:
        return normalize_news_source_rows([], source_status="available")

    unique_symbol_candidates = frame.drop_duplicates(subset=["ts_code"], keep="last").copy()
    stock_name_lookup = _load_topn_stock_name_lookup(
        ts_codes=frame["ts_code"].tolist()
    )
    window_start_date = fetch_start_date or trade_date
    active_providers = _normalize_provider_list(provider=provider, providers=providers)

    event_rows: list[dict] = []
    candidate_contexts_by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in frame.to_dict(orient="records"):
        symbol = _ts_code_to_symbol(row["ts_code"])
        candidate_context = _candidate_context_from_row(
            {
                **row,
                "stock_name": _resolve_topn_stock_name(
                    current_name=row.get("stock_name"),
                    asset_id=row.get("asset_id"),
                    ts_code=row.get("ts_code"),
                    lookup=stock_name_lookup,
                ),
            }
        )
        bucket = candidate_contexts_by_symbol.setdefault(symbol, [])
        if candidate_context not in bucket:
            bucket.append(candidate_context)

    historical_providers = set(HISTORICAL_TOP10_NEWS_PROVIDERS)
    for current_provider in active_providers:
        for row in unique_symbol_candidates.to_dict(orient="records"):
            symbol = _ts_code_to_symbol(row["ts_code"])
            if current_provider in historical_providers:
                try:
                    rows = fetch_historical_provider_rows(
                        provider=current_provider,
                        symbol=symbol,
                        ts_code=row["ts_code"],
                        stock_name=row["stock_name"],
                        start_date=window_start_date,
                        end_date=trade_date,
                    )
                except Exception as exc:
                    warnings.warn(
                        (
                            "historical top10 provider fetch failed; "
                            f"provider={current_provider} symbol={symbol} trade_date={trade_date} "
                            f"reason={exc}"
                        ),
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
            else:
                rows = fetch_news_rows(
                    start_date=window_start_date,
                    end_date=trade_date,
                    provider=current_provider,
                    symbol=symbol,
                )
            for item in rows:
                metadata = dict(item.get("metadata") or {})
                metadata["matched_candidates"] = candidate_contexts_by_symbol.get(symbol, [])
                normalized_item = dict(item)
                normalized_item["metadata"] = metadata
                event_rows.append(normalized_item)

    return normalize_news_source_rows(
        _aggregate_topn_event_rows(event_rows),
        source_status="available",
    )


def run_news_source_backfill(
    *,
    start_date: str,
    end_date: str,
    provider: str = "tushare",
    token: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    try:
        rows = fetch_news_rows(
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            token=token,
        )
        source_status = "available"
    except Exception as exc:
        if not _is_permission_error(exc):
            raise
        rows = []
        source_status = "permission_denied"

    events = normalize_news_source_rows(rows, source_status=source_status)
    resolved_output_dir = Path(output_dir) if output_dir is not None else _default_output_dir(
        start_date=start_date,
        end_date=end_date,
    )
    paths = _write_news_source_backfill_report(
        output_dir=resolved_output_dir,
        events=events,
        source_status=source_status,
    )
    return {"source_status": source_status, "events": events, "paths": paths}


def run_topn_news_source_backfill(
    *,
    candidates_path: str | Path,
    provider: str,
    trade_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    candidates = pd.read_csv(candidates_path, low_memory=False)
    candidates["trade_date"] = pd.to_datetime(candidates["trade_date"], errors="coerce").dt.date
    target_date = pd.to_datetime(trade_date, errors="coerce").date()
    candidates = candidates.loc[candidates["trade_date"] == target_date].copy()
    events = _collect_topn_news_source_events_for_candidates(
        candidates=candidates,
        provider=provider,
        trade_date=trade_date,
    )
    resolved_output_dir = Path(output_dir) if output_dir is not None else _default_topn_output_dir(
        trade_date=trade_date
    )
    paths = _write_news_source_backfill_report(
        output_dir=resolved_output_dir,
        events=events,
        source_status="available",
    )
    return {"events": events, "paths": paths}


def _default_historical_top10_output_dir(*, start_date: str, end_date: str) -> Path:
    return Path("outputs/research") / f"historical_top10_news_backfill_{start_date}_{end_date}"


def _is_nonempty_text(value: object) -> bool:
    return bool(str(value or "").strip())


def _is_capital_broker_resonance(summary: object) -> bool:
    text = str(summary or "").strip()
    return "共振" in text and ("券商" in text or "金股" in text) and ("主力" in text or "资金" in text)


def _is_risk_without_catalyst(row: pd.Series) -> bool:
    compact_summary = str(row.get("news_compact_summary") or "").strip()
    if not compact_summary:
        return False
    if "风险" not in compact_summary or "无新增催化" not in compact_summary:
        return False
    return True


def _build_historical_top10_summary_frame(
    *,
    candidates: pd.DataFrame,
    source_events: pd.DataFrame,
    mentions: pd.DataFrame,
    features: pd.DataFrame,
    enrichment: pd.DataFrame,
) -> pd.DataFrame:
    trade_date_count = int(candidates["trade_date"].nunique()) if not candidates.empty else 0
    enrichment_rows = int(len(enrichment))
    coverage_rows = int(
        enrichment.loc[enrichment.get("news_attention_level", pd.Series(dtype="object")).fillna("").ne("unknown")].shape[0]
        if not enrichment.empty and "news_attention_level" in enrichment.columns
        else 0
    )
    coverage_rate = float(coverage_rows / enrichment_rows) if enrichment_rows else 0.0
    compact_summary_nonempty_rows = int(
        enrichment["news_compact_summary"].map(_is_nonempty_text).sum() if "news_compact_summary" in enrichment.columns else 0
    )
    capital_broker_resonance_rows = int(
        enrichment["news_compact_summary"].map(_is_capital_broker_resonance).sum()
        if "news_compact_summary" in enrichment.columns
        else 0
    )
    risk_without_catalyst_rows = int(
        enrichment.apply(_is_risk_without_catalyst, axis=1).sum() if not enrichment.empty else 0
    )

    summary_row = {
        "trade_date_count": trade_date_count,
        "candidate_rows": int(len(candidates)),
        "source_event_rows": int(len(source_events)),
        "mention_rows": int(len(mentions)),
        "feature_rows": int(len(features)),
        "enrichment_rows": enrichment_rows,
        "coverage_rows": coverage_rows,
        "coverage_rate": coverage_rate,
        "compact_summary_nonempty_rows": compact_summary_nonempty_rows,
        "capital_broker_resonance_rows": capital_broker_resonance_rows,
        "risk_without_catalyst_rows": risk_without_catalyst_rows,
    }
    return pd.DataFrame([summary_row])


def _write_historical_top10_report(*, output_dir: Path, summary: pd.DataFrame) -> str:
    row = summary.iloc[0].to_dict() if not summary.empty else {}
    coverage_rate = float(row.get("coverage_rate", 0.0) or 0.0)
    report_lines = [
        "# Historical Top10 News Backfill Report",
        "",
        "## Summary",
        "",
        f"- trade_date_count: {int(row.get('trade_date_count', 0) or 0)}",
        f"- candidate_rows: {int(row.get('candidate_rows', 0) or 0)}",
        f"- source_event_rows: {int(row.get('source_event_rows', 0) or 0)}",
        f"- mention_rows: {int(row.get('mention_rows', 0) or 0)}",
        f"- feature_rows: {int(row.get('feature_rows', 0) or 0)}",
        f"- enrichment_rows: {int(row.get('enrichment_rows', 0) or 0)}",
        f"- coverage_rows: {int(row.get('coverage_rows', 0) or 0)}",
        f"- coverage_rate: {coverage_rate:.2%}",
        f"- compact_summary_nonempty_rows: {int(row.get('compact_summary_nonempty_rows', 0) or 0)}",
        f"- capital_broker_resonance_rows: {int(row.get('capital_broker_resonance_rows', 0) or 0)}",
        f"- risk_without_catalyst_rows: {int(row.get('risk_without_catalyst_rows', 0) or 0)}",
    ]
    report_path = output_dir / "historical_top10_news_backfill_report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return str(report_path)


def run_historical_top10_news_backfill(
    *,
    top10_path: str | Path,
    start_date: str,
    end_date: str,
    provider: str | None = None,
    providers: list[str] | None = None,
    output_dir: str | Path | None = None,
    sample_trade_dates: int | None = None,
) -> dict[str, object]:
    resolved_providers = providers
    resolved_provider = provider
    if resolved_provider is None and resolved_providers is None:
        resolved_providers = list(DEFAULT_HISTORICAL_REPLACEMENT_PROVIDERS)

    candidates = _load_historical_top10_candidates(
        top10_path=top10_path,
        start_date=start_date,
        end_date=end_date,
        sample_trade_dates=sample_trade_dates,
    )
    candidates = _normalize_topn_candidate_stock_names(candidates)
    resolved_output_dir = Path(output_dir) if output_dir is not None else _default_historical_top10_output_dir(
        start_date=start_date,
        end_date=end_date,
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    candidate_path = resolved_output_dir / "historical_top10_candidates.csv"
    source_events_path = resolved_output_dir / "historical_news_source_events.csv"
    mentions_path = resolved_output_dir / "historical_news_feature_mentions.csv"
    features_path = resolved_output_dir / "historical_news_feature_daily.csv"
    enrichment_path = resolved_output_dir / "historical_top10_news_enrichment.csv"
    candidates.to_csv(candidate_path, index=False)

    daily_events: list[pd.DataFrame] = []
    for trade_day, daily_candidates in candidates.groupby("trade_date", sort=True):
        fetch_start_date = (pd.Timestamp(trade_day) - pd.Timedelta(days=1)).date().isoformat()
        daily_events.append(
            _collect_topn_news_source_events_for_candidates(
                candidates=daily_candidates,
                provider=resolved_provider,
                providers=resolved_providers,
                trade_date=str(trade_day),
                fetch_start_date=fetch_start_date,
            )
        )

    source_events = (
        pd.concat(daily_events, ignore_index=True)
        if daily_events
        else normalize_news_source_rows([], source_status="available")
    )
    source_events.to_csv(source_events_path, index=False)

    mentions = map_news_mentions(events=source_events, assets=candidates)
    mentions.to_csv(mentions_path, index=False)

    trade_dates = [
        pd.Timestamp(trade_day).date().isoformat()
        for trade_day in sorted(candidates["trade_date"].dropna().unique())
    ]
    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=trade_dates,
        mode="replay",
    )
    features.to_csv(features_path, index=False)

    enrichment = build_topn_news_enrichment(candidates=candidates, news_features=features)
    enrichment.to_csv(enrichment_path, index=False)

    summary = _build_historical_top10_summary_frame(
        candidates=candidates,
        source_events=source_events,
        mentions=mentions,
        features=features,
        enrichment=enrichment,
    )
    summary_path = resolved_output_dir / "historical_top10_news_backfill_summary.csv"
    summary.to_csv(summary_path, index=False)
    report_path = _write_historical_top10_report(output_dir=resolved_output_dir, summary=summary)

    return {
        "candidates": candidates,
        "source_events": source_events,
        "mentions": mentions,
        "features": features,
        "enrichment": enrichment,
        "trade_date_count": int(candidates["trade_date"].nunique()) if not candidates.empty else 0,
        "paths": {
            "candidates": str(candidate_path),
            "source_events": str(source_events_path),
            "mentions": str(mentions_path),
            "features": str(features_path),
            "enrichment": str(enrichment_path),
            "summary": str(summary_path),
            "report": report_path,
        },
    }
