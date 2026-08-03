from __future__ import annotations

from datetime import datetime
import re
from typing import Any


_REPORT_IDENTITY_MAX_LENGTH = 200
_STRICT_AWARE_ISO8601_RE = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)


def normalize_report_identity(value: Any) -> str:
    if type(value) is not str:
        return ""
    if (
        not value
        or value != value.strip()
        or "\x00" in value
        or len(value) > _REPORT_IDENTITY_MAX_LENGTH
    ):
        return ""
    return value


def normalize_aware_iso8601_timestamp(value: Any) -> str:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif type(value) is str:
        text = value.strip()
        if (
            not text
            or text != value
            or _STRICT_AWARE_ISO8601_RE.fullmatch(text) is None
        ):
            return ""
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return ""
    else:
        return ""
    try:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return ""
        serialized = parsed.isoformat()
    except Exception:
        return ""
    if _STRICT_AWARE_ISO8601_RE.fullmatch(serialized) is None:
        return ""
    try:
        reparsed = datetime.fromisoformat(serialized)
        if reparsed.tzinfo is None or reparsed.utcoffset() is None:
            return ""
    except Exception:
        return ""
    return serialized
