from dataclasses import asdict, dataclass
from typing import Any, Literal, TypedDict


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


DataStatus = Literal["completed", "partial", "missing", "stale"]
SectorType = Literal["industry", "concept"]


@dataclass(frozen=True)
class MarketOverviewIndex:
    code: str
    name: str
    close: float | None
    change_pct: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorHeatmapItem:
    sector_id: str
    sector_name: str
    sector_type: SectorType
    change_pct: float | None
    amount: float | None
    up_count: int | None
    down_count: int | None
    main_net_inflow: float | None
    stock_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorFundFlowItem:
    rank: int
    sector_id: str
    sector_name: str
    sector_type: SectorType
    change_pct: float | None
    amount: float | None
    main_net_inflow: float | None
    main_net_inflow_ratio: float | None
    leading_stock_name: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorLeadingStock:
    asset_id: str
    name: str
    change_pct: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketOverviewIndexPayload(TypedDict):
    code: str
    name: str
    close: float | None
    change_pct: float | None


class SectorHeatmapItemPayload(TypedDict):
    sector_id: str
    sector_name: str
    sector_type: SectorType
    change_pct: float | None
    amount: float | None
    up_count: int | None
    down_count: int | None
    main_net_inflow: float | None
    stock_count: int | None


class SectorFundFlowItemPayload(TypedDict):
    rank: int
    sector_id: str
    sector_name: str
    sector_type: SectorType
    change_pct: float | None
    amount: float | None
    main_net_inflow: float | None
    main_net_inflow_ratio: float | None
    leading_stock_name: str | None


class SectorLeadingStockPayload(TypedDict):
    asset_id: str
    name: str
    change_pct: float | None


class BaseDashboardPayload(TypedDict):
    trade_date: str
    updated_at: str | None
    source: str
    data_status: DataStatus
    warnings: list[str]


class MarketOverviewPayload(BaseDashboardPayload):
    indices: list[MarketOverviewIndexPayload]
    total_amount: float | None
    up_count: int | None
    down_count: int | None
    limit_up_count: int | None
    limit_down_count: int | None


class SectorHeatmapPayload(BaseDashboardPayload):
    items: list[SectorHeatmapItemPayload]


class SectorFundFlowPayload(BaseDashboardPayload):
    inflow: list[SectorFundFlowItemPayload]
    outflow: list[SectorFundFlowItemPayload]


class SectorDetailPayload(BaseDashboardPayload):
    sector_id: str
    sector_name: str
    sector_type: SectorType
    change_pct: float | None
    amount: float | None
    up_count: int | None
    down_count: int | None
    main_net_inflow: float | None
    main_net_inflow_ratio: float | None
    stock_count: int | None
    leading_stocks: list[SectorLeadingStockPayload]
