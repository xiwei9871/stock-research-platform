from __future__ import annotations

import json
import os
from pathlib import Path


def build_runtime_provenance(
    *,
    release_root: str | Path,
    release_id: str,
    frontend_build_id: str,
    package_file: str | Path,
) -> dict[str, str]:
    source_root = Path(release_root).resolve()
    expected_package_path = source_root / "src" / "stock_research"
    expected_package_root = expected_package_path.resolve()
    python_package_root = Path(package_file).resolve().parent

    try:
        expected_package_root.relative_to(source_root)
    except ValueError as exc:
        raise RuntimeError(
            "python package root does not match release root: "
            f"expected {expected_package_root}, got {python_package_root}"
        ) from exc
    if python_package_root != expected_package_root:
        raise RuntimeError(
            "python package root does not match release root: "
            f"expected {expected_package_root}, got {python_package_root}"
        )

    api_release_id = release_id.strip()
    frontend_release_id = frontend_build_id.strip()
    if api_release_id and frontend_release_id and api_release_id != frontend_release_id:
        raise RuntimeError(
            "API and frontend release IDs do not match: "
            f"{api_release_id!r} != {frontend_release_id!r}"
        )

    return {
        "release_id": api_release_id,
        "source_root": str(source_root),
        "python_package_root": str(python_package_root),
        "frontend_build_id": frontend_release_id,
    }


def runtime_provenance(*, package_file: str | Path | None = None) -> dict[str, str]:
    if package_file is None:
        import stock_research

        package_file = stock_research.__file__

    repository_root = Path(__file__).resolve().parents[2]
    release_root = os.environ.get("STOCK_RESEARCH_RELEASE_ROOT", "").strip()
    selected_release_root = Path(release_root or repository_root)
    declared_frontend_build_id = os.environ.get("STOCK_RESEARCH_FRONTEND_BUILD_ID", "").strip()
    frontend_build_id = _frontend_build_id_from_metadata(
        release_root=selected_release_root,
        declared_frontend_build_id=declared_frontend_build_id,
    )
    return build_runtime_provenance(
        release_root=selected_release_root,
        release_id=os.environ.get("STOCK_RESEARCH_RELEASE_ID", ""),
        frontend_build_id=frontend_build_id,
        package_file=package_file,
    )


def _frontend_build_id_from_metadata(
    *,
    release_root: Path,
    declared_frontend_build_id: str,
) -> str:
    configured_path = os.environ.get("STOCK_RESEARCH_FRONTEND_METADATA_FILE", "").strip()
    metadata_path = (
        Path(configured_path)
        if configured_path
        else release_root / "dashboard" / "dist" / "release.json"
    )
    if not metadata_path.is_file():
        if declared_frontend_build_id:
            raise RuntimeError(f"frontend release metadata is missing: {metadata_path}")
        return ""

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"frontend release metadata is invalid: {metadata_path}") from exc
    metadata_build_id = str(payload.get("release_id") or "").strip()
    if not metadata_build_id:
        if declared_frontend_build_id:
            raise RuntimeError(f"frontend release metadata is missing release_id: {metadata_path}")
        return ""
    if declared_frontend_build_id and declared_frontend_build_id != metadata_build_id:
        raise RuntimeError(
            "frontend release metadata does not match declared frontend release: "
            f"{metadata_build_id!r} != {declared_frontend_build_id!r}"
        )
    return metadata_build_id
