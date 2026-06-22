from dataclasses import dataclass


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
