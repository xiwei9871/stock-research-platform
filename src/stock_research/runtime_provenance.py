from __future__ import annotations

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
    expected_package_root = (source_root / "src" / "stock_research").resolve()
    python_package_root = Path(package_file).resolve().parent

    try:
        python_package_root.relative_to(expected_package_root)
    except ValueError as exc:
        raise RuntimeError(
            "python package root does not match release root: "
            f"expected {expected_package_root}, got {python_package_root}"
        ) from exc

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
    return build_runtime_provenance(
        release_root=release_root or repository_root,
        release_id=os.environ.get("STOCK_RESEARCH_RELEASE_ID", ""),
        frontend_build_id=os.environ.get("STOCK_RESEARCH_FRONTEND_BUILD_ID", ""),
        package_file=package_file,
    )
