from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AssetSummary:
    asset_id: str
    symbol: str
    name: str
    exchange: str
    board: str | None
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BarPoint:
    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    amount: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreRow:
    trade_date: str
    asset_id: str
    rank: int
    score_total: float
    score_version: str
    score_components: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistSignalRow:
    watchlist_id: str
    trade_date: str
    asset_id: str
    stock_code: str
    stock_name: str
    priority: int
    signal_score: float | None
    primary_signal: str
    signal_tags: list[str]
    risk_tags: list[str]
    must_watch: bool
    reason_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportLink:
    report_type: str
    title: str
    path: str
    format: str
    trade_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
