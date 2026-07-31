from __future__ import annotations

import argparse
import json
import logging
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from stock_research.theme_research_report_manifest import (
    ReportManifestError,
    ReportManifestLimits,
)


logger = logging.getLogger(__name__)

_MAX_ERRORS = 100
_ERROR_FIELDS = {"code", "manifest_path", "theme_id", "version"}
_IDENTITY_SAFE_MANIFEST_CODES = {
    "ARTIFACT_ENTRY_INVALID",
    "ARTIFACT_CHECKSUM_MISMATCH",
    "ARTIFACT_FILE_CHANGED",
    "ARTIFACT_FILE_INVALID",
    "ARTIFACT_MISSING",
    "ARTIFACT_PATH_INVALID",
    "ARTIFACT_SIZE_MISMATCH",
    "ARTIFACT_TOO_LARGE",
    "MARKDOWN_REQUIRED",
}


def _load_settings() -> Any:
    from stock_research.config import SETTINGS

    return SETTINGS


def load_report_manifest(*args: Any, **kwargs: Any) -> Any:
    from stock_research.theme_research_report_manifest import (
        load_report_manifest as load,
    )

    return load(*args, **kwargs)


def register_report_manifest(*args: Any, **kwargs: Any) -> Any:
    from stock_research.theme_research_report_store import (
        register_report_manifest as register,
    )

    return register(*args, **kwargs)


def _is_theme_research_report_error(exc: Exception) -> bool:
    try:
        from stock_research.theme_research_report_store import ThemeResearchReportError
    except MemoryError:
        raise
    except Exception:
        return False
    return isinstance(exc, ThemeResearchReportError)


def _freeze_error(error: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        detached = dict(error)
    except (TypeError, ValueError) as exc:
        raise ValueError("scan errors must be mappings") from exc
    if (
        not detached
        or "code" not in detached
        or set(detached) - _ERROR_FIELDS
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in detached.items()
        )
    ):
        raise ValueError("scan errors must contain only supported string fields")
    return MappingProxyType(detached)


@dataclass(frozen=True)
class ReportScanResult:
    discovered: int
    indexed: int
    unchanged: int
    invalid: int
    errors: Sequence[Mapping[str, Any]]
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        counts = (self.discovered, self.indexed, self.unchanged, self.invalid)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts
        ):
            raise ValueError("scan result counts must be non-negative integers")
        try:
            timestamps_are_aware = (
                self.started_at.utcoffset() is not None
                and self.completed_at.utcoffset() is not None
            )
        except Exception as exc:
            raise ValueError("scan result timestamps must be timezone aware") from exc
        if not timestamps_are_aware:
            raise ValueError("scan result timestamps must be timezone aware")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        object.__setattr__(self, "errors", tuple(_freeze_error(error) for error in self.errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovered": self.discovered,
            "indexed": self.indexed,
            "unchanged": self.unchanged,
            "invalid": self.invalid,
            "errors": [dict(error) for error in self.errors],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


def limits_from_settings(settings: Any) -> ReportManifestLimits:
    try:
        return ReportManifestLimits(
            max_manifest_bytes=settings.theme_research_report_max_manifest_bytes,
            max_markdown_bytes=settings.theme_research_report_max_markdown_bytes,
            max_pdf_bytes=settings.theme_research_report_max_pdf_bytes,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("theme research report limits are invalid") from exc


def _is_temporary_or_hidden(name: str) -> bool:
    return name.startswith(".") or name.endswith(".tmp")


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_child_directory(parent_fd: int, name: str) -> int | None:
    entry_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISDIR(entry_stat.st_mode):
        return None
    return os.open(name, _directory_open_flags(), dir_fd=parent_fd)


def _sorted_directory_names(directory_fd: int) -> list[str]:
    return sorted(os.listdir(directory_fd))


def _directory_entry_matches_fd(parent_fd: int, name: str, child_fd: int) -> bool:
    try:
        entry_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened_stat = os.fstat(child_fd)
    except (OSError, ValueError):
        return False
    return (
        stat.S_ISDIR(entry_stat.st_mode)
        and not stat.S_ISLNK(entry_stat.st_mode)
        and entry_stat.st_dev == opened_stat.st_dev
        and entry_stat.st_ino == opened_stat.st_ino
    )


def _safe_close(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _append_error(errors: list[dict[str, str]], error: dict[str, str]) -> None:
    logger.warning(
        "theme report scan failure %s",
        json.dumps(error, ensure_ascii=False, sort_keys=True),
    )
    errors.append(error)
    errors.sort(key=_error_sort_key)
    if len(errors) > _MAX_ERRORS:
        errors.pop()


def _error_sort_key(error: Mapping[str, str]) -> tuple[str, str, str, str]:
    theme_id = error.get("theme_id", "")
    return (
        error.get("manifest_path", f"{theme_id}/" if theme_id else ""),
        error.get("code", ""),
        theme_id,
        error.get("version", ""),
    )


def _manifest_error(
    code: str,
    relative_path: str,
    *,
    theme_id: str | None = None,
    version: str | None = None,
) -> dict[str, str]:
    result = {"code": code, "manifest_path": relative_path}
    if theme_id is not None:
        result["theme_id"] = theme_id
    if version is not None:
        result["version"] = version
    return result


def scan_theme_research_report_root(
    root: str | os.PathLike[str],
    *,
    limits: ReportManifestLimits,
    service: str | None = None,
) -> ReportScanResult:
    started_at = datetime.now(timezone.utc)
    discovered = indexed = unchanged = invalid = 0
    errors: list[dict[str, str]] = []
    selected_service = (
        service
        if service is not None
        else _load_settings().theme_research_runtime_service
    )

    try:
        report_root = Path(os.path.abspath(os.fspath(root)))
        root_fd = os.open(report_root, _directory_open_flags())
    except FileNotFoundError:
        return ReportScanResult(0, 0, 0, 0, (), started_at, datetime.now(timezone.utc))
    except (OSError, TypeError, ValueError):
        _append_error(errors, {"code": "REPORT_ROOT_INVALID"})
        return ReportScanResult(0, 0, 0, 1, errors, started_at, datetime.now(timezone.utc))

    try:
        try:
            theme_names = _sorted_directory_names(root_fd)
        except (OSError, ValueError):
            _append_error(errors, {"code": "REPORT_DISCOVERY_ERROR"})
            return ReportScanResult(
                0,
                0,
                0,
                1,
                errors,
                started_at,
                datetime.now(timezone.utc),
            )

        for theme_id in theme_names:
            if _is_temporary_or_hidden(theme_id):
                continue
            theme_fd: int | None = None
            try:
                theme_fd = _open_child_directory(root_fd, theme_id)
                if theme_fd is None:
                    continue
                version_names = _sorted_directory_names(theme_fd)
            except (OSError, ValueError):
                _safe_close(theme_fd)
                invalid += 1
                _append_error(
                    errors, {"code": "REPORT_DISCOVERY_ERROR", "theme_id": theme_id}
                )
                continue
            except BaseException:
                _safe_close(theme_fd)
                raise
            try:
                for version in version_names:
                    if _is_temporary_or_hidden(version):
                        continue
                    if not _directory_entry_matches_fd(root_fd, theme_id, theme_fd):
                        invalid += 1
                        _append_error(
                            errors,
                            {
                                "code": "REPORT_DISCOVERY_ERROR",
                                "theme_id": theme_id,
                            },
                        )
                        break
                    relative_path = f"{theme_id}/{version}/manifest.json"
                    version_fd: int | None = None
                    try:
                        version_fd = _open_child_directory(theme_fd, version)
                        if version_fd is None:
                            continue
                    except (OSError, ValueError):
                        invalid += 1
                        _append_error(
                            errors,
                            _manifest_error(
                                "REPORT_DISCOVERY_ERROR",
                                relative_path,
                                theme_id=theme_id,
                                version=version,
                            ),
                        )
                        continue
                    try:
                        try:
                            os.stat(
                                "manifest.json",
                                dir_fd=version_fd,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            continue
                        except (OSError, ValueError):
                            invalid += 1
                            _append_error(
                                errors,
                                _manifest_error(
                                    "REPORT_DISCOVERY_ERROR",
                                    relative_path,
                                    theme_id=theme_id,
                                    version=version,
                                ),
                            )
                            continue

                        if (
                            not _directory_entry_matches_fd(
                                root_fd, theme_id, theme_fd
                            )
                            or not _directory_entry_matches_fd(
                                theme_fd, version, version_fd
                            )
                        ):
                            invalid += 1
                            _append_error(
                                errors,
                                _manifest_error(
                                    "REPORT_DISCOVERY_ERROR",
                                    relative_path,
                                    theme_id=theme_id,
                                    version=version,
                                ),
                            )
                            continue

                        discovered += 1
                        manifest_path = report_root / theme_id / version / "manifest.json"
                        manifest = None
                        try:
                            manifest = load_report_manifest(
                                manifest_path,
                                report_root=report_root,
                                limits=limits,
                            )
                            store_result = register_report_manifest(
                                manifest, service=selected_service
                            )
                            outcome = (
                                store_result.get("result")
                                if isinstance(store_result, Mapping)
                                else None
                            )
                            if outcome == "indexed":
                                indexed += 1
                            elif outcome == "unchanged":
                                unchanged += 1
                            else:
                                raise RuntimeError(
                                    "report store returned an unsupported result"
                                )
                        except MemoryError:
                            raise
                        except ReportManifestError as exc:
                            invalid += 1
                            safe_identity = exc.code in _IDENTITY_SAFE_MANIFEST_CODES
                            _append_error(
                                errors,
                                _manifest_error(
                                    exc.code,
                                    relative_path,
                                    theme_id=theme_id if safe_identity else None,
                                    version=version if safe_identity else None,
                                ),
                            )
                        except Exception as exc:
                            invalid += 1
                            if (
                                manifest is not None
                                and _is_theme_research_report_error(exc)
                            ):
                                error = _manifest_error(
                                    exc.code,
                                    relative_path,
                                    theme_id=manifest.theme_id,
                                    version=manifest.version,
                                )
                            elif isinstance(exc, OSError):
                                error = _manifest_error(
                                    "INDEX_IO_ERROR", relative_path
                                )
                            else:
                                error = _manifest_error(
                                    "INDEX_UNEXPECTED_ERROR", relative_path
                                )
                            _append_error(errors, error)
                    finally:
                        _safe_close(version_fd)
            finally:
                _safe_close(theme_fd)
    finally:
        _safe_close(root_fd)

    return ReportScanResult(
        discovered,
        indexed,
        unchanged,
        invalid,
        errors,
        started_at,
        datetime.now(timezone.utc),
    )


def _build_parser(settings: Any) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.theme_research_report_index")
    parser.add_argument("--root", type=Path, default=settings.theme_research_report_root)
    parser.add_argument("--service", default=settings.theme_research_runtime_service)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings = _load_settings()
        limits = limits_from_settings(settings)
    except (ImportError, TypeError, ValueError):
        print(
            json.dumps(
                {"error": {"code": "REPORT_INDEX_CONFIGURATION_ERROR"}},
                ensure_ascii=False,
            )
        )
        return 3

    args = _build_parser(settings).parse_args(argv)

    result = scan_theme_research_report_root(args.root, limits=limits, service=args.service)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    if result.invalid == 0:
        return 0
    if any(
        error.get("code") == "REPORT_ROOT_INVALID"
        or (
            error.get("code") == "REPORT_DISCOVERY_ERROR"
            and "theme_id" not in error
            and "manifest_path" not in error
        )
        for error in result.errors
    ):
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
