from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


FIXTURE_PREFIX = "theme-report-playwright-e2e"
THEME_ID = f"{FIXTURE_PREFIX}-theme"
NODE_ID = f"{FIXTURE_PREFIX}-node-transformer"
ADMIN_USER_ID = f"{FIXTURE_PREFIX}-admin"
NORMAL_USER_ID = f"{FIXTURE_PREFIX}-user"
ADMIN_USERNAME = "theme_report_e2e_admin"
NORMAL_USERNAME = "theme_report_e2e_user"
ADMIN_PASSWORD = "theme-report-admin-password"
NORMAL_PASSWORD = "theme-report-user-password"
V1 = "2026-07-31.1"
V2 = "2026-08-01.1"
LOCK_KEY = 7_171_271_448_728_574_941


@dataclass
class FixtureLifecycleState:
    connection: Any | None = None
    database_verified: bool = False
    lock_acquired: bool = False
    fixture_seed_started: bool = False
    fixture_seeded: bool = False
    cleaned: bool = False


def _verify_test_database(state: FixtureLifecycleState) -> str:
    if state.connection is None:
        raise RuntimeError("database connection is unavailable")
    database_name = str(state.connection.execute("SELECT current_database()").fetchone()[0])
    if not database_name.endswith("_test"):
        raise RuntimeError(f"refusing to run Playwright fixture against {database_name}")
    state.database_verified = True
    return database_name


def _cleanup_fixture_resources(state: FixtureLifecycleState, temp_root: Path) -> list[BaseException]:
    if state.cleaned:
        return []
    state.cleaned = True
    errors: list[BaseException] = []
    connection = state.connection
    try:
        if connection is not None and state.database_verified and state.lock_acquired and state.fixture_seed_started:
            try:
                connection.rollback()
                _cleanup_database(connection)
            except BaseException as exc:  # cleanup must not mask the startup failure
                errors.append(exc)
        if connection is not None and state.lock_acquired:
            try:
                connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
                connection.commit()
            except BaseException as exc:
                errors.append(exc)
    finally:
        if connection is not None:
            try:
                connection.close()
            except BaseException as exc:
                errors.append(exc)
            state.connection = None
        configured_service_file = os.environ.get("PGSERVICEFILE", "")
        try:
            shutil.rmtree(temp_root)
        except FileNotFoundError:
            pass
        except BaseException as exc:
            errors.append(exc)
        finally:
            try:
                if configured_service_file and Path(configured_service_file).is_relative_to(temp_root):
                    os.environ.pop("PGSERVICEFILE", None)
            except (OSError, ValueError):
                os.environ.pop("PGSERVICEFILE", None)
    return errors


def _report_cleanup_errors(errors: list[BaseException]) -> None:
    for error in errors:
        print(f"theme report E2E cleanup warning: {error}", file=sys.stderr)


def _source_service_file() -> Path:
    configured = os.environ.get("PGSERVICEFILE", "").strip()
    return Path(configured) if configured else Path.home() / ".pg_service.conf"


def _write_isolated_service_file(temp_root: Path) -> Path:
    source = _source_service_file()
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(source, encoding="utf-8"):
        raise RuntimeError(f"PostgreSQL service file is unavailable: {source}")
    required = ("theme_research_test_migration", "theme_research_test_runtime")
    missing = [name for name in required if not parser.has_section(name)]
    if missing:
        raise RuntimeError(f"dedicated PostgreSQL test services are missing: {', '.join(missing)}")

    path = temp_root / "pg_service.conf"
    with path.open("w", encoding="utf-8") as stream:
        for alias, source_name, role_name in (
            ("stock_research", "theme_research_test_migration", None),
            ("theme_research_runtime", "theme_research_test_runtime", None),
            (
                "theme_research_report_indexer",
                "theme_research_test_migration",
                "theme_research_report_indexer",
            ),
            (
                "theme_research_report_reviewer",
                "theme_research_test_migration",
                "theme_research_report_reviewer",
            ),
        ):
            stream.write(f"[{alias}]\n")
            for key, value in parser[source_name].items():
                if role_name is not None and key == "options":
                    continue
                if "\n" in key or "\n" in value:
                    raise RuntimeError("PostgreSQL service entries must be single-line values")
                stream.write(f"{key}={value}\n")
            if role_name is not None:
                existing_options = parser[source_name].get("options", "").strip()
                options = f"{existing_options} -c role={role_name}".strip()
                stream.write(f"options={options}\n")
            stream.write("\n")
    path.chmod(0o600)
    return path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_report_version(report_root: Path, version: str) -> Path:
    is_v2 = version == V2
    version_dir = report_root / THEME_ID / version
    version_dir.mkdir(parents=True, exist_ok=False)
    markdown = (
        "# AI供电产业链分析报告（第二版）\n\n"
        "## 第二版核心结论\n\n液冷与电网侧证据已经补强。\n"
        if is_v2
        else "# AI供电产业链分析报告（第一版）\n\n"
        "## 第一版核心结论\n\n服务器电源价值量持续提升。\n"
    ).encode("utf-8")
    pdf = f"%PDF-1.4\nreal-e2e-{version}\n".encode("ascii")
    (version_dir / "report.md").write_bytes(markdown)
    (version_dir / "report.pdf").write_bytes(pdf)
    manifest = {
        "schema_version": "theme_research_report_manifest_v1",
        "theme_id": THEME_ID,
        "version": version,
        "title": "AI供电产业链分析报告（第二版）" if is_v2 else "AI供电产业链分析报告（第一版）",
        "summary": "第二版补充液冷与电网侧证据。" if is_v2 else "第一版覆盖电源、液冷与价值量。",
        "generated_at": "2026-08-01T11:00:00+08:00" if is_v2 else "2026-07-31T11:00:00+08:00",
        "generator": {"name": "theme-report-playwright-e2e", "version": "1.0.0"},
        "artifacts": {
            "markdown": {"path": "report.md", "sha256": _sha256(markdown)},
            "pdf": {"path": "report.pdf", "sha256": _sha256(pdf)},
        },
        "metadata": {"fixture_prefix": FIXTURE_PREFIX},
    }
    (version_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return version_dir


def _reset_report_fixture(report_root: Path, mutation_service: str, scan_service: str) -> dict[str, Any]:
    import psycopg
    from stock_research.config import SETTINGS
    from stock_research.theme_research_report_index import (
        limits_from_settings,
        scan_theme_research_report_root,
    )
    from stock_research.theme_research_report_store import report_version_id

    report_root.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".reset-", dir=report_root))
    target = report_root / THEME_ID
    backup = report_root / f".backup-{THEME_ID}"
    try:
        _write_report_version(staging_root, V1)
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            os.replace(target, backup)
        os.replace(staging_root / THEME_ID, target)
        try:
            with psycopg.connect(f"service={mutation_service}") as connection:
                connection.execute(
                    """
                    DELETE FROM research.theme_research_report_review_event
                    WHERE report_version_id IN (
                        SELECT report_version_id
                        FROM research.theme_research_report_version
                        WHERE theme_id = %s
                    )
                    """,
                    (THEME_ID,),
                )
                connection.execute(
                    "DELETE FROM research.theme_research_report_version WHERE theme_id = %s",
                    (THEME_ID,),
                )
            result = scan_theme_research_report_root(
                report_root,
                limits=limits_from_settings(SETTINGS),
                service=scan_service,
            )
            if result.invalid or result.indexed != 1:
                raise RuntimeError(f"fixture reset indexing failed: {result.to_dict()}")
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        with psycopg.connect(f"service={mutation_service}") as connection:
            row = connection.execute(
                """
                SELECT status
                FROM research.theme_research_report_version
                WHERE report_version_id = %s
                """,
                (report_version_id(THEME_ID, V1),),
            ).fetchone()
            v2_exists = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM research.theme_research_report_version
                    WHERE theme_id = %s AND version = %s
                )
                """,
                (THEME_ID, V2),
            ).fetchone()[0]
        return {"v1_status": row[0] if row else None, "v2_exists": bool(v2_exists)}
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _cleanup_database(connection: Any) -> None:
    connection.execute(
        """
        DELETE FROM identity.user_session
        WHERE user_id IN (%s, %s)
        """,
        (ADMIN_USER_ID, NORMAL_USER_ID),
    )
    connection.execute(
        """
        DELETE FROM research.theme_research_report_review_event
        WHERE report_version_id IN (
            SELECT report_version_id
            FROM research.theme_research_report_version
            WHERE theme_id = %s
        )
        """,
        (THEME_ID,),
    )
    connection.execute(
        "DELETE FROM research.theme_research_report_version WHERE theme_id = %s",
        (THEME_ID,),
    )
    connection.execute(
        "DELETE FROM research.theme_research_node WHERE theme_id = %s",
        (THEME_ID,),
    )
    connection.execute(
        "DELETE FROM research.theme_research_theme WHERE theme_id = %s",
        (THEME_ID,),
    )
    connection.execute(
        "DELETE FROM identity.user_account WHERE user_id IN (%s, %s)",
        (ADMIN_USER_ID, NORMAL_USER_ID),
    )
    connection.commit()


def _seed_database(connection: Any) -> None:
    from stock_research.dashboard.auth_service import hash_password

    connection.execute(
        """
        INSERT INTO identity.user_account (
            user_id, username, display_name, role, password_hash
        ) VALUES
            (%s, %s, 'Theme Report E2E Admin', 'admin', %s),
            (%s, %s, 'Theme Report E2E User', 'user', %s)
        """,
        (
            ADMIN_USER_ID,
            ADMIN_USERNAME,
            hash_password(ADMIN_PASSWORD),
            NORMAL_USER_ID,
            NORMAL_USERNAME,
            hash_password(NORMAL_PASSWORD),
        ),
    )
    connection.execute(
        """
        INSERT INTO research.theme_research_theme (
            theme_id, theme_name, theme_type, summary, status, created_from,
            last_updated, content_sha256, created_by, updated_by
        ) VALUES (
            %s, 'AI供电测试产业链', 'ai_power',
            '真实隔离Playwright报告发布测试主题。', 'reviewed', 'manual',
            '2026-08-01', %s, %s, %s
        )
        """,
        (THEME_ID, _sha256(THEME_ID.encode("utf-8")), ADMIN_USER_ID, ADMIN_USER_ID),
    )
    connection.execute(
        """
        INSERT INTO research.theme_research_node (
            node_id, theme_id, parent_node_id, node_name, node_type, description,
            value_capture_score, bottleneck_score, localization_gap_score,
            supply_tightness_score, evidence_strength, node_review_status,
            created_by, updated_by
        ) VALUES (
            %s, %s, NULL, '变压器', 'infrastructure', '真实E2E节点',
            4, 4, 3, 3, 2, 'needs_evidence', %s, %s
        )
        """,
        (NODE_ID, THEME_ID, ADMIN_USER_ID, ADMIN_USER_ID),
    )
    connection.commit()


def _build_test_app(report_root: Path, token: str, cleanup: Callable[[], None]):
    from fastapi import FastAPI, Header, HTTPException
    from stock_research.dashboard.app import app as production_app
    from stock_research.theme_research_report_index import (
        limits_from_settings,
        scan_theme_research_report_root,
    )
    from stock_research.theme_research_report_store import report_version_id
    from stock_research.config import SETTINGS

    @asynccontextmanager
    async def lifespan(_app):
        yield
        cleanup()

    outer = FastAPI(lifespan=lifespan)
    fixture_lock = threading.Lock()

    def require_token(value: str) -> None:
        if value != token:
            raise HTTPException(status_code=404, detail="not_found")

    @outer.get("/__test__/theme-report-fixture/status")
    def fixture_status(x_theme_report_e2e_token: str = Header(default="")):
        require_token(x_theme_report_e2e_token)
        return {
            "theme_id": THEME_ID,
            "v1_report_version_id": report_version_id(THEME_ID, V1),
        }

    @outer.post("/__test__/theme-report-fixture/index-v2")
    def index_v2(x_theme_report_e2e_token: str = Header(default="")):
        require_token(x_theme_report_e2e_token)
        with fixture_lock:
            version_dir = report_root / THEME_ID / V2
            if not version_dir.exists():
                _write_report_version(report_root, V2)
            result = scan_theme_research_report_root(
                report_root,
                limits=limits_from_settings(SETTINGS),
                service=SETTINGS.theme_research_report_index_service,
            )
        if result.invalid:
            raise HTTPException(status_code=500, detail="fixture_index_failed")
        return result.to_dict()

    @outer.post("/__test__/theme-report-fixture/reset")
    def reset_fixture(x_theme_report_e2e_token: str = Header(default="")):
        require_token(x_theme_report_e2e_token)
        with fixture_lock:
            return _reset_report_fixture(
                report_root,
                SETTINGS.theme_research_migration_service,
                SETTINGS.theme_research_report_index_service,
            )

    # AppShell fetches these unrelated market summaries on every page. The dedicated
    # report database intentionally contains only identity/theme/report schemas, so
    # keep those shell reads inside this test-only process while target APIs continue
    # through the mounted production application.
    @outer.get("/api/platform/readiness")
    def platform_readiness_fixture():
        return {"display_trade_date": "2026-08-01", "latest_market_date": "2026-08-01"}

    @outer.get("/api/platform/summary")
    def platform_summary_fixture():
        return {"latest_market_date": "2026-08-01"}

    @outer.get("/api/market-monitor/eod")
    def market_monitor_eod_fixture():
        return {
            "trade_date": "2026-08-01",
            "freshness": {"mode": "eod", "label": "Last Completed Trading Day", "is_realtime": False},
            "coverage": {"market_assets": 0, "score_assets": 0, "factor_count": 0},
            "market_breadth": {"status": "pending_source"},
            "index_snapshot": [],
            "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
            "unusual_moves": [],
            "watchlist_alerts": [],
            "strategy_signal_summary": {"topn_preview_count": 0, "topn_preview": [], "risk_filter_counts": {}},
            "generated_reports": [],
            "market_emotion": {"summary": {"status": "missing"}, "components": []},
            "emotion_stock_lists": {"limit_up": [], "limit_down": []},
            "warnings": [],
        }

    @outer.get("/api/public-news")
    def public_news_fixture():
        return {"items": [], "total": 0, "limit": 100, "offset": 0, "warnings": []}

    @outer.get("/api/public-news/status")
    def public_news_status_fixture():
        return {"enabled": False, "running": False, "interval_seconds": 0}

    outer.mount("/", production_app)
    return outer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    token = os.environ.get("PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN", "")
    if len(token) < 20:
        raise RuntimeError("PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN must be random and at least 20 characters")

    temp_root = Path(tempfile.mkdtemp(prefix=f"{FIXTURE_PREFIX}-"))
    state = FixtureLifecycleState()

    def cleanup() -> None:
        _report_cleanup_errors(_cleanup_fixture_resources(state, temp_root))

    try:
        report_root = temp_root / "reports"
        service_file = _write_isolated_service_file(temp_root)
        os.environ.update(
            {
                "PGSERVICEFILE": str(service_file),
                "THEME_RESEARCH_MIGRATION_SERVICE": "stock_research",
                "THEME_RESEARCH_RUNTIME_SERVICE": "theme_research_runtime",
                "THEME_RESEARCH_REPORT_ROOT": str(report_root),
                "THEME_RESEARCH_READ_SOURCE": "db",
                "STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED": "true",
                "STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE": "false",
                "STOCK_RESEARCH_NEWS_SCHEDULER_ENABLED": "false",
            }
        )

        import psycopg
        import uvicorn
        from stock_research.config import SETTINGS
        from stock_research.dashboard.auth_schema import DASHBOARD_AUTH_SCHEMA_SQL
        from stock_research.theme_research_db_schema import THEME_RESEARCH_SCHEMA_SQL
        from stock_research.theme_research_report_index import (
            limits_from_settings,
            scan_theme_research_report_root,
        )
        from stock_research.theme_research_report_schema import apply_theme_research_report_schema

        state.connection = psycopg.connect("service=stock_research")
        _verify_test_database(state)
        state.connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        state.lock_acquired = True
        state.connection.execute(DASHBOARD_AUTH_SCHEMA_SQL)
        state.connection.execute(THEME_RESEARCH_SCHEMA_SQL)
        state.connection.commit()
        apply_theme_research_report_schema(service="stock_research")
        state.fixture_seed_started = True
        _cleanup_database(state.connection)
        _seed_database(state.connection)
        _write_report_version(report_root, V1)
        scan_result = scan_theme_research_report_root(
            report_root,
            limits=limits_from_settings(SETTINGS),
            service="theme_research_report_indexer",
        )
        if scan_result.indexed != 1 or scan_result.invalid:
            raise RuntimeError(f"v1 report fixture indexing failed: {scan_result.to_dict()}")
        state.fixture_seeded = True
        app = _build_test_app(report_root, token, cleanup)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
