from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    display_name: str
    role: str
    is_active: bool
