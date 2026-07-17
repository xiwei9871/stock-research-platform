from copy import deepcopy
from hashlib import sha256
from typing import Any, Iterable

import rfc8785


def canonical_bytes(
    payload: Any,
    *,
    excluded_paths: Iterable[tuple[str, ...]] = (),
) -> bytes:
    normalized = deepcopy(payload)
    for path in excluded_paths:
        if not path:
            continue
        parent = normalized
        for part in path[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                break
            parent = parent[part]
        else:
            if isinstance(parent, dict):
                parent.pop(path[-1], None)
    return rfc8785.dumps(normalized)


def content_sha256(
    payload: Any,
    *,
    excluded_paths: Iterable[tuple[str, ...]] = (),
) -> str:
    return sha256(canonical_bytes(payload, excluded_paths=excluded_paths)).hexdigest()
