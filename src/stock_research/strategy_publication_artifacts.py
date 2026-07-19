"""Atomic immutable artifact publication for official strategies."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


ARTIFACT_VERSION = "strategy_artifact_v1"
_FRAME_NAMES = ("equity", "positions", "trades", "review")


def write_strategy_publication_artifacts(
    *,
    output_dir: str | Path,
    strategy_id: str,
    run_id: str,
    started_at: datetime,
    publication_identity: Mapping[str, Any],
    frames: Mapping[str, pd.DataFrame],
    summary: Mapping[str, Any],
    config: Mapping[str, Any],
    compatibility_destinations: Mapping[str, str | Path],
) -> dict[str, Any]:
    """Write one immutable strategy publication, then refresh compatibility mirrors."""

    mirror_destinations = _validate_compatibility_destinations(compatibility_destinations)
    missing_frames = [name for name in _FRAME_NAMES if name not in frames]
    if missing_frames:
        raise ValueError(f"strategy publication frames missing: {', '.join(missing_frames)}")
    if not isinstance(publication_identity, Mapping):
        raise ValueError("publication_identity must be a mapping")

    output = Path(output_dir)
    strategy_root = output / "strategy_runs" / _safe_component(strategy_id)
    strategy_root.mkdir(parents=True, exist_ok=True)
    publish_id = _build_publish_id(
        run_id=run_id,
        started_at=started_at,
        publication_identity=publication_identity,
    )
    final_dir = strategy_root / publish_id
    while final_dir.exists():
        publish_id = f"{publish_id}-{uuid.uuid4().hex[:8]}"
        final_dir = strategy_root / publish_id

    temp_dir = Path(tempfile.mkdtemp(prefix=f".{publish_id}.tmp-", dir=str(strategy_root)))
    try:
        for name in _FRAME_NAMES:
            _write_frame(pd.DataFrame(frames[name]), temp_dir / f"{name}.csv")

        persisted_summary = _json_ready(dict(summary))
        persisted_summary["publication_identity"] = _json_ready(dict(publication_identity))
        persisted_summary["artifact_version"] = ARTIFACT_VERSION
        _write_json(temp_dir / "summary.json", persisted_summary)

        file_hashes = {
            name: _sha256(temp_dir / f"{name}.csv")
            for name in _FRAME_NAMES
        }
        file_hashes["summary"] = _sha256(temp_dir / "summary.json")
        files = {
            name: {
                "relative_path": f"{name}.csv" if name in _FRAME_NAMES else "summary.json",
                "absolute_path": str(
                    (final_dir / (f"{name}.csv" if name in _FRAME_NAMES else "summary.json")).resolve()
                ),
                "sha256": digest,
            }
            for name, digest in file_hashes.items()
        }
        manifest = {
            "artifact_version": ARTIFACT_VERSION,
            "publish_id": publish_id,
            "strategy_id": str(strategy_id),
            "run_id": str(run_id),
            "started_at": _utc_text(started_at),
            "publication_identity": _json_ready(dict(publication_identity)),
            "config": _json_ready(dict(config)),
            "files": files,
        }
        _write_json(temp_dir / "publication_manifest.json", manifest)
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    versioned_paths = {
        f"{name}_path": final_dir / f"{name}.csv"
        for name in _FRAME_NAMES
    }
    versioned_paths["summary_path"] = final_dir / "summary.json"
    versioned_paths["publication_manifest_path"] = final_dir / "publication_manifest.json"
    _publish_compatibility_mirrors(versioned_paths, mirror_destinations)

    return {
        "artifact_version": ARTIFACT_VERSION,
        "publish_id": publish_id,
        "publication_identity": _json_ready(dict(publication_identity)),
        "version_dir": final_dir,
        "publication_manifest_path": versioned_paths["publication_manifest_path"],
        "file_hashes": file_hashes,
        "output_paths": versioned_paths,
        "summary": persisted_summary,
        "config": _json_ready(dict(config)),
    }


def _build_publish_id(
    *,
    run_id: str,
    started_at: datetime,
    publication_identity: Mapping[str, Any],
) -> str:
    identity_fingerprint = str(publication_identity.get("config_fingerprint") or "")
    if not identity_fingerprint:
        identity_fingerprint = hashlib.sha256(
            _json_bytes(_json_ready(dict(publication_identity)), indent=None)
        ).hexdigest()
    timestamp = _utc_datetime(started_at).strftime("%Y%m%dT%H%M%S%fZ")
    return "-".join(
        (
            _safe_component(run_id)[:80],
            timestamp,
            _safe_component(identity_fingerprint)[:12],
            uuid.uuid4().hex[:12],
        )
    )


def _safe_component(value: object) -> str:
    component = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return component or "unknown"


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_bytes(_json_bytes(payload, indent=2))


def _json_bytes(payload: Any, *, indent: int | None) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":") if indent is None else None,
            ensure_ascii=False,
            indent=indent,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_compatibility_destinations(
    destinations: Mapping[str, str | Path],
) -> dict[str, Path]:
    if set(destinations) != set(_FRAME_NAMES):
        raise ValueError(
            "compatibility destinations must contain exactly: " + ", ".join(_FRAME_NAMES)
        )
    normalized: dict[str, Path] = {}
    resolved: set[Path] = set()
    for name in _FRAME_NAMES:
        raw = destinations[name]
        if not str(raw).strip():
            raise ValueError(f"compatibility destination missing: {name}")
        destination = Path(raw)
        if (
            not destination.name
            or destination.is_symlink()
            or (destination.exists() and destination.is_dir())
        ):
            raise ValueError(f"invalid compatibility destination: {name}")
        resolved_destination = destination.resolve()
        if resolved_destination in resolved:
            raise ValueError("compatibility destinations must be unique")
        resolved.add(resolved_destination)
        normalized[name] = destination
    return normalized


def _publish_compatibility_mirrors(
    versioned_paths: Mapping[str, Path],
    destinations: Mapping[str, Path],
) -> None:
    staged: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    attempted: list[str] = []
    try:
        for name in _FRAME_NAMES:
            destination = destinations[name]
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged[name] = _temp_sibling(destination, label="stage")
            _copy_file(versioned_paths[f"{name}_path"], staged[name])
        for name in _FRAME_NAMES:
            destination = destinations[name]
            if destination.exists():
                backups[name] = _temp_sibling(destination, label="backup")
                _copy_file(destination, backups[name])
        try:
            for name in _FRAME_NAMES:
                attempted.append(name)
                _replace_mirror(staged[name], destinations[name])
        except Exception:
            for name in reversed(attempted):
                destination = destinations[name]
                backup = backups.get(name)
                try:
                    if backup is not None and backup.exists():
                        os.replace(backup, destination)
                    else:
                        destination.unlink(missing_ok=True)
                except Exception:
                    pass
            raise
    finally:
        for path in (*staged.values(), *backups.values()):
            path.unlink(missing_ok=True)


def _temp_sibling(destination: Path, *, label: str) -> Path:
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.{label}-",
        dir=str(destination.parent),
    )
    os.close(file_descriptor)
    return Path(temp_name)


def _copy_file(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)


def _replace_mirror(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _utc_text(value: datetime) -> str:
    return _utc_datetime(value).isoformat()


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value
