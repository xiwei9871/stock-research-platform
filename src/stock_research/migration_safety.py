import shlex
import subprocess
from pathlib import Path
from typing import Any


def _quote_service(service: str) -> str:
    return '"' + f"service={service}".replace('"', '\\"') + '"'


def build_backup_restore_check_plan(
    backup_path: str | Path,
    source_service: str = "stock_research",
    restore_service: str | None = None,
) -> dict[str, Any]:
    path = Path(backup_path)
    restore = restore_service or f"{source_service}_restore_check"
    commands = [
        " ".join(
            [
                "pg_dump",
                "--format=custom",
                "--file",
                shlex.quote(str(path)),
                _quote_service(source_service),
            ]
        ),
        " ".join(["pg_restore", "--list", shlex.quote(str(path))]),
        " ".join(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--dbname",
                _quote_service(restore),
                shlex.quote(str(path)),
            ]
        ),
    ]
    return {
        "backup_path": str(path),
        "source_service": source_service,
        "restore_service": restore,
        "commands": commands,
    }


def run_backup_restore_check(
    backup_path: str | Path,
    source_service: str = "stock_research",
    restore_service: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    plan = build_backup_restore_check_plan(
        backup_path=backup_path,
        source_service=source_service,
        restore_service=restore_service,
    )
    path = Path(backup_path)
    if dry_run:
        return {**plan, "status": "planned", "checks": []}

    checks = []
    if not path.exists() or path.stat().st_size <= 0:
        return {
            **plan,
            "status": "failed",
            "checks": [
                {
                    "check": "backup_file_exists",
                    "status": "failed",
                    "detail": str(path),
                }
            ],
        }
    checks.append({"check": "backup_file_exists", "status": "ok", "detail": str(path)})

    result = subprocess.run(
        ["pg_restore", "--list", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        checks.append(
            {
                "check": "backup_catalog_readable",
                "status": "failed",
                "detail": result.stderr.strip() or result.stdout.strip(),
            }
        )
        return {**plan, "status": "failed", "checks": checks}
    checks.append({"check": "backup_catalog_readable", "status": "ok", "detail": str(path)})
    return {**plan, "status": "ok", "checks": checks}
