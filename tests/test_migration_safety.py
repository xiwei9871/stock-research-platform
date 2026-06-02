from pathlib import Path

from stock_research import migration_safety


def test_build_backup_restore_check_plan_includes_dump_list_and_restore_commands():
    plan = migration_safety.build_backup_restore_check_plan(
        backup_path=Path("/tmp/stock_research.dump"),
        source_service="stock_research",
        restore_service="stock_research_restore_check",
    )

    assert plan["backup_path"] == "/tmp/stock_research.dump"
    assert plan["source_service"] == "stock_research"
    assert plan["restore_service"] == "stock_research_restore_check"
    assert plan["commands"] == [
        'pg_dump --format=custom --file /tmp/stock_research.dump "service=stock_research"',
        "pg_restore --list /tmp/stock_research.dump",
        'pg_restore --clean --if-exists --no-owner --dbname "service=stock_research_restore_check" /tmp/stock_research.dump',
    ]


def test_run_backup_restore_check_dry_run_returns_plan_without_running_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(migration_safety.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    result = migration_safety.run_backup_restore_check(
        backup_path=Path("/tmp/stock_research.dump"),
        source_service="stock_research",
        restore_service="stock_research_restore_check",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["checks"] == []
    assert calls == []


def test_run_backup_restore_check_requires_existing_backup_for_non_dry_run(tmp_path):
    missing_path = tmp_path / "missing.dump"

    result = migration_safety.run_backup_restore_check(
        backup_path=missing_path,
        source_service="stock_research",
        restore_service="stock_research_restore_check",
        dry_run=False,
    )

    assert result["status"] == "failed"
    assert result["checks"][0] == {
        "check": "backup_file_exists",
        "status": "failed",
        "detail": str(missing_path),
    }
