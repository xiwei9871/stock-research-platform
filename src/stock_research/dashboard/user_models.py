from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class UserWatchlistItem:
    id: int
    user_id: int
    asset_id: str
    trade_date_added: str
    source: str
    notes: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UserReviewItem:
    id: int
    session_id: int
    user_id: int
    asset_id: str
    decision: str
    conviction: str
    tags: list[str]
    notes: str
    follow_up_required: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UserReviewSession:
    id: int
    user_id: int
    trade_date: str
    title: str
    summary: str
    market_view: str
    position_view: str
    next_action: str
    created_at: str
    updated_at: str
    items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
