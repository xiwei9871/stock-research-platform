from __future__ import annotations

import errno


_PATH_STRUCTURE_ERRNOS = frozenset({errno.ELOOP, errno.ENOTDIR})


def is_path_structure_error(error: OSError) -> bool:
    """Return whether an OS error proves an unsafe path shape."""
    return error.errno in _PATH_STRUCTURE_ERRNOS
