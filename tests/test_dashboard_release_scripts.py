import json
import os
import re
import stat
import subprocess
import textwrap
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _sync_env(release_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DASHBOARD_SYNC_ENV": str(release_root / "missing.env"),
        "STOCK_RESEARCH_RELEASE_ROOT": str(release_root),
        "EXPECTED_TRADE_DATE": "2026-07-24",
        "REMOTE_USER": "deploy",
        "REMOTE_HOST": "example.invalid",
        "REMOTE_DIR": "/srv/stock-research",
        "THEME_RESEARCH_REPORT_HOST_ROOT": "/srv/stock-research/theme-research-reports",
    }


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _release_fixture(tmp_path: Path, *, valid_manifest: bool = True) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "release"
    (root / "src" / "stock_research").mkdir(parents=True)
    (root / "src" / "stock_research" / "__init__.py").write_text("", encoding="utf-8")
    (root / "dashboard" / "dist").mkdir(parents=True)
    (root / "dashboard" / "package.json").write_text("{}", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n", encoding="utf-8")
    (root / "deploy").mkdir()
    for name in (
        "validate_strategy_release.py",
        "dashboard-release.compose.yml",
        "dashboard-api.Dockerfile",
        "dashboard-frontend.Dockerfile",
        "dashboard-nginx.conf",
        "dashboard-api-requirements.lock",
        "dashboard-api-requirements.in",
        "check_dashboard_remote_host.sh",
        "check_dashboard_report_mount.sh",
        "check_theme_research_report_runtime.py",
    ):
        source = REPO_ROOT / "deploy" / name
        if source.exists():
            (root / "deploy" / name).write_bytes(source.read_bytes())
    _write_executable(
        root / "deploy" / "check_dashboard_release.sh",
        """
        #!/bin/bash
        printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
          "$EXPECTED_TRADE_DATE" "$EXPECTED_RELEASE_ID" "$EXPECTED_REMOTE_SOURCE_ROOT" \
          "$EXPECTED_FRONTEND_BUILD_ID" "$EXPECTED_STRATEGY_ARTIFACT_DATE" \
          "$EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT" "$EXPECTED_API_BASE_IMAGE" \
          "$EXPECTED_FRONTEND_BASE_IMAGE" "$BASE_URL" \
          >> "$FAKE_RELEASE_GATE_LOG"
        [[ "${FAKE_RELEASE_ALREADY_LIVE:-0}" == "1" ]] && exit 0
        count=0
        [[ -f "$FAKE_RELEASE_GATE_COUNT" ]] && count="$(cat "$FAKE_RELEASE_GATE_COUNT")"
        count=$((count + 1))
        printf '%s\n' "$count" > "$FAKE_RELEASE_GATE_COUNT"
        [[ "$count" -ge 2 ]]
        """,
    )

    output_dir = root / "outputs" / "research" / "strategy_daily_eod" / "2026-07-24"
    output_dir.mkdir(parents=True)
    strategy_ids = ("lhb_shortline", "mid_trend", "tech_bottleneck")
    count = 5 if valid_manifest else 4
    manifest_rows = ["trade_date,strategy_id,rank,asset_id,review_tier,artifact_path"]
    for strategy_id in strategy_ids:
        rows = ["trade_date,strategy_id,rank,asset_id,review_tier"]
        filename = {
            "lhb_shortline": "strategy_lhb_shortline_review.csv",
            "mid_trend": "strategy_mid_trend_review.csv",
            "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
        }[strategy_id]
        for rank in range(1, count + 1):
            asset_id = f"{strategy_id}-{rank}"
            rows.append(f"2026-07-24,{strategy_id},{rank},{asset_id},top5_focus")
            manifest_rows.append(
                f"2026-07-24,{strategy_id},{rank},{asset_id},top5_focus,{filename}"
            )
        (output_dir / filename).write_text("\n".join(rows) + "\n", encoding="utf-8")
    (output_dir / "review_queue_strategy_manifest.csv").write_text(
        "\n".join(manifest_rows) + "\n", encoding="utf-8"
    )
    summary = {
        "trade_date": "2026-07-24",
        "review_rows": count * 3,
        "manifest_modules": [
            "strategy_lhb_shortline",
            "strategy_mid_trend",
            "strategy_tech_bottleneck",
            "review_queue_strategy_manifest",
        ],
        "score_audit": {
            "status": "success",
            "strategy_counts": {strategy_id: count for strategy_id in strategy_ids},
        },
    }
    (output_dir / "strategy_eod_publish_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    fake_bin = tmp_path / "bin"
    log_file = tmp_path / "commands.log"
    _write_executable(
        fake_bin / "python-override",
        """
        #!/bin/bash
        echo "python:$*" >> "$FAKE_COMMAND_LOG"
        if [[ "$*" == *"import stock_research"* ]]; then
          echo "$FAKE_RELEASE_ROOT/src/stock_research/__init__.py"
          exit 0
        fi
        if [[ "$*" == *"load_platform_summary"* || "$*" == *"build_platform_readiness"* ]]; then
          if [[ "${FAKE_PLATFORM_LOADER_FAIL:-0}" == "1" ]]; then exit 1; fi
          echo "${FAKE_STRATEGY_DATE-2026-07-24}"
          exit 0
        fi
        if [[ "$*" == *"stock_research.strategy_manifest_transfer export"* ]]; then
          echo '{"schema_version":"strategy_manifest_transfer_v1","trade_date":"2026-07-24","run_id":"strategy-eod-2026-07-24-local","rows":[]}'
          exit 0
        fi
        exec /usr/bin/python3 "$@"
        """,
    )
    _write_executable(
        fake_bin / "rtk",
        """
        #!/bin/bash
        echo "rtk:CI=${CI-unset}:$*" >> "$FAKE_COMMAND_LOG"
        if [[ "$*" == *" build" ]]; then
          mkdir -p "$FAKE_RELEASE_ROOT/dashboard/dist"
          printf '{"release_id":"%s","api_base_image":"python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7","frontend_base_image":"nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"}\n' "$VITE_RELEASE_ID" > "$FAKE_RELEASE_ROOT/dashboard/dist/release.json"
        fi
        """,
    )
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        echo '{"latest_market_date":"2026-05-18","runtime_provenance":{"release_id":"old-release","source_root":"/old/release","python_package_root":"/old/release/src/stock_research"}}'
        """,
    )
    _write_executable(
        fake_bin / "ssh",
        """
        #!/bin/bash
        echo "ssh:CI=${CI-unset}:$*" >> "$FAKE_COMMAND_LOG"
        if [[ "$*" == *"check_theme_research_report_runtime.py --expected-root"* ]]; then
          printf '%s\n' '{"status":"ok","root":{"path":"/app/reports/theme-research","exists":true,"readable":true,"readonly":true},"schema":{"status":"current","schema_version":"5"},"service_permissions":{"runtime":{"status":"ok","session_user":"runtime_login"},"indexer":{"status":"ok","session_user":"index_login"},"reviewer":{"status":"ok","session_user":"review_login"}},"service_identity":{"status":"ok","server_version_nums":{"runtime":150000,"indexer":160000,"reviewer":160000},"login_attributes":{"runtime":{"rolcanlogin":true,"rolsuper":false,"rolcreatedb":false,"rolcreaterole":false,"rolreplication":false,"rolbypassrls":false},"indexer":{"rolcanlogin":true,"rolsuper":false,"rolcreatedb":false,"rolcreaterole":false,"rolreplication":false,"rolbypassrls":false},"reviewer":{"rolcanlogin":true,"rolsuper":false,"rolcreatedb":false,"rolcreaterole":false,"rolreplication":false,"rolbypassrls":false}}},"scheduler_index_diagnostics":{"status":"ok","invalid":0,"errors":[]}}'
        fi
        """,
    )
    _write_executable(
        fake_bin / "rsync",
        """
        #!/bin/bash
        echo "rsync:CI=${CI-unset}:$*" >> "$FAKE_COMMAND_LOG"
        """,
    )

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DASHBOARD_SYNC_ENV": str(tmp_path / "missing.env"),
        "STOCK_RESEARCH_RELEASE_ROOT": str(root),
        "STOCK_RESEARCH_PYTHON": str(fake_bin / "python-override"),
        "STRATEGY_OUTPUT_ROOT": str(root / "outputs" / "research"),
        "LOCAL_READINESS_URL": "http://local.invalid/api/platform/readiness",
        "FAKE_RELEASE_ROOT": str(root),
        "FAKE_COMMAND_LOG": str(log_file),
        "FAKE_RELEASE_GATE_LOG": str(tmp_path / "release-gates.log"),
        "FAKE_RELEASE_GATE_COUNT": str(tmp_path / "release-gates.count"),
        "THEME_RESEARCH_REPORT_HOST_ROOT": "/srv/stock-research/theme-research-reports",
    }
    env.pop("EXPECTED_TRADE_DATE", None)
    return root, env, log_file


def test_release_sync_rejects_worktrees_dirty_roots_and_import_mismatches():
    script = _read("deploy/sync_dashboard_release.sh")

    assert "set -euo pipefail" in script
    assert "*/.worktrees/*" in script
    assert "Refusing disposable worktree release root" in script
    assert "status --porcelain --untracked-files=all" in script
    assert "Refusing dirty release root" in script
    assert "STOCK_RESEARCH_PYTHON" in script
    assert "import stock_research" in script
    assert "Python import root mismatch" in script


def test_release_sync_versions_compose_images_and_injects_provenance():
    script = _read("deploy/sync_dashboard_release.sh")
    compose = _read("deploy/dashboard-release.compose.yml")
    api_dockerfile = _read("deploy/dashboard-api.Dockerfile")
    frontend_dockerfile = _read("deploy/dashboard-frontend.Dockerfile")
    nginx_config = _read("deploy/dashboard-nginx.conf")

    assert "dashboard-release.compose.yml" in script
    assert "compose_file" not in script
    assert "-f deploy/dashboard-release.compose.yml" in script
    assert "--project-name" in script
    assert "STOCK_RESEARCH_COMPOSE_PROJECT" in script
    assert "docker compose" in script and "build api dashboard" in script
    assert "--force-recreate" in script
    assert "up -d --force-recreate --remove-orphans api dashboard" in script
    assert "STOCK_RESEARCH_RELEASE_ROOT" in compose
    assert "STOCK_RESEARCH_RELEASE_ID" in compose
    assert "STOCK_RESEARCH_FRONTEND_BUILD_ID" in compose
    assert '127.0.0.1:${DASHBOARD_API_BIND_PORT:-8765}:8765' in compose
    assert '127.0.0.1:${DASHBOARD_FRONTEND_BIND_PORT:-5174}:80' in compose
    assert "networks:" in compose
    assert compose.count("context: ..") == 2
    assert "../outputs/research:/app/outputs/research:ro" in compose
    assert "THEME_RESEARCH_REPORT_ROOT: /app/reports/theme-research" in compose
    assert "THEME_RESEARCH_MIGRATION_SERVICE: ${THEME_RESEARCH_MIGRATION_SERVICE:-stock_research}" in compose
    assert "THEME_RESEARCH_RUNTIME_SERVICE: ${THEME_RESEARCH_RUNTIME_SERVICE:-theme_research_runtime}" in compose
    assert "THEME_RESEARCH_REPORT_INDEX_SERVICE: ${THEME_RESEARCH_REPORT_INDEX_SERVICE:-theme_research_report_indexer}" in compose
    assert "THEME_RESEARCH_REPORT_REVIEW_SERVICE: ${THEME_RESEARCH_REPORT_REVIEW_SERVICE:-theme_research_report_reviewer}" in compose
    assert (
        "      - type: bind\n"
        "        source: ${THEME_RESEARCH_REPORT_HOST_ROOT:?required}\n"
        "        target: /app/reports/theme-research\n"
        "        read_only: true\n"
        "        bind:\n"
        "          create_host_path: false\n"
    ) in compose
    assert "COPY src ./src" in api_dockerfile
    assert "COPY dashboard/dist ./dashboard/dist" in api_dockerfile
    assert "COPY dashboard/dist /usr/share/nginx/html" in frontend_dockerfile
    assert "COPY deploy/dashboard-nginx.conf" in frontend_dockerfile
    assert "try_files $uri $uri/ /index.html" in nginx_config
    assert "location /api/" in nginx_config
    assert "proxy_pass http://api:8765" in nginx_config
    for header in ("Host", "X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"):
        assert f"proxy_set_header {header}" in nginx_config


def test_dashboard_nginx_keeps_entrypoints_fresh_and_assets_immutable():
    nginx_config = _read("deploy/dashboard-nginx.conf")

    no_store = 'add_header Cache-Control "no-store, no-cache, must-revalidate" always;'

    assert "location = /index.html" in nginx_config
    assert "location = /release.json" in nginx_config
    assert nginx_config.count(no_store) >= 3
    assert "location /assets/" in nginx_config
    assert 'add_header Cache-Control "public, immutable";' in nginx_config


def test_release_sync_provides_frontend_dist_in_docker_build_context():
    script = _read("deploy/sync_dashboard_release.sh")

    assert (REPO_ROOT / ".dockerignore").is_file()
    dockerignore_rules = {
        line.strip()
        for line in _read(".dockerignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "!dashboard/dist/" in dockerignore_rules
    assert "!dashboard/dist/**" in dockerignore_rules
    assert '"$ROOT/.dockerignore"' in script


def test_release_packages_theme_research_priority_support_without_canonical_artifacts():
    script = _read("deploy/sync_dashboard_release.sh")
    dockerignore = _read(".dockerignore")
    api_dockerfile = _read("deploy/dashboard-api.Dockerfile")

    for relative_dir in (
        "artifacts/theme_decomposition/priority_policies",
        "artifacts/theme_decomposition/tech_bottleneck_crosswalks",
    ):
        assert f"!{relative_dir}/" in dockerignore
        assert f"!{relative_dir}/**" in dockerignore
        assert f'"$ROOT/{relative_dir}/"' in script
        assert f"COPY {relative_dir} ./{relative_dir}" in api_dockerfile

    assert "COPY artifacts/theme_decomposition ./artifacts/theme_decomposition" not in api_dockerfile
    assert (
        "      - type: bind\n"
        "        source: ../artifacts/theme_decomposition\n"
        "        target: /app/artifacts/theme_decomposition\n"
        "        read_only: true\n"
        "        bind:\n"
        "          create_host_path: false\n"
    ) in _read("deploy/dashboard-release.compose.yml")


def test_release_builds_use_lockfiles_and_pinned_base_images():
    script = _read("deploy/sync_dashboard_release.sh")
    api_dockerfile = _read("deploy/dashboard-api.Dockerfile")
    frontend_dockerfile = _read("deploy/dashboard-frontend.Dockerfile")
    requirements = _read("deploy/dashboard-api-requirements.lock")
    requirements_input = _read("deploy/dashboard-api-requirements.in")

    assert 'pnpm --dir "$ROOT/dashboard" install --frozen-lockfile' in script
    assert "python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7" in api_dockerfile
    assert "dashboard-api-requirements.lock" in api_dockerfile
    assert "--require-hashes" in api_dockerfile
    assert "--no-deps ." in api_dockerfile
    assert api_dockerfile.index("--requirement deploy/dashboard-api-requirements.lock") < api_dockerfile.index("COPY src ./src")
    assert "nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10" in frontend_dockerfile
    assert requirements.count("--hash=sha256:") > 30
    assert "akshare==1.18.60" in requirements_input
    assert "akracer==0.0.14" in requirements_input
    assert "akracer==0.0.14" in requirements
    assert "py-mini-racer==0.6.0" in requirements_input
    assert "py-mini-racer==0.6.0" in requirements
    assert "jsonpath==" in requirements
    assert "pydantic-core==" in requirements
    for package in ("fastapi==", "uvicorn==", "pandas==", "psycopg[binary]=="):
        assert package in requirements


def test_release_lock_covers_all_project_runtime_dependencies():
    project = tomllib.loads(_read("pyproject.toml"))["project"]
    requirements_input = _read("deploy/dashboard-api-requirements.in").lower()
    requirements_lock = _read("deploy/dashboard-api-requirements.lock").lower()

    for dependency in project["dependencies"]:
        package = re.split(r"[<>=!~;\[\s]", dependency, maxsplit=1)[0].lower()
        normalized = package.replace("_", "-")
        assert re.search(rf"(?m)^{re.escape(normalized)}(?:\[.*\])?==", requirements_input), package
        assert re.search(rf"(?m)^{re.escape(normalized)}(?:\[.*\])?==", requirements_lock), package


def test_release_sync_validates_and_preserves_read_only_report_root():
    script = _read("deploy/sync_dashboard_release.sh")
    mount_check = _read("deploy/check_dashboard_report_mount.sh")

    assert "THEME_RESEARCH_REPORT_HOST_ROOT" in script
    assert "must be a safe absolute path" in script
    assert "Theme Research report host root" in script
    assert '[[ ! -d "$host_root" || ! -r "$host_root" || ! -x "$host_root" ]]' in mount_check
    assert "mkdir -p ${theme_research_report_host_root_q}" not in script
    assert "THEME_RESEARCH_REPORT_HOST_ROOT=${theme_research_report_host_root_q}" in script
    assert "THEME_RESEARCH_MIGRATION_SERVICE=${theme_research_migration_service_q}" in script
    assert "THEME_RESEARCH_RUNTIME_SERVICE=${theme_research_runtime_service_q}" in script
    assert "THEME_RESEARCH_REPORT_INDEX_SERVICE=${theme_research_report_index_service_q}" in script
    assert "THEME_RESEARCH_REPORT_REVIEW_SERVICE=${theme_research_report_review_service_q}" in script
    assert "check_dashboard_report_mount.sh" in script
    assert 'bash "$ROOT/deploy/check_dashboard_report_mount.sh" --validate-path' in script
    assert "docker inspect" in mount_check
    assert script.index("check_dashboard_report_mount.sh") < script.index("if check_release_state")


def _report_mount_check_env(tmp_path: Path, *, source: Path, rw: bool) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        printf '%s|%s|%s\n' '/app/reports/theme-research' "$FAKE_MOUNT_SOURCE" "$FAKE_MOUNT_RW"
        """,
    )
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_MOUNT_SOURCE": str(source),
        "FAKE_MOUNT_RW": "true" if rw else "false",
    }


def test_report_mount_check_rejects_missing_configured_host_root(tmp_path):
    missing = tmp_path / "stock-research" / "theme-research-reports"
    env = _report_mount_check_env(tmp_path, source=missing, rw=False)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--host-only",
            str(missing),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must already exist" in result.stderr


@pytest.mark.parametrize(
    "unsafe_root",
    [
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/home",
        "/lib",
        "/lib64",
        "/media",
        "/mnt",
        "/opt",
        "/proc",
        "/root",
        "/run",
        "/sbin",
        "/srv",
        "/sys",
        "/tmp",
        "/usr",
        "/var",
        "/srv/theme-research",
        "/srv/stock-research/reports",
    ],
)
def test_report_mount_path_validation_rejects_system_or_non_dedicated_roots(unsafe_root):
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--validate-path",
            unsafe_root,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert any(
        marker in result.stderr.lower()
        for marker in ("dedicated", "safe", "system root")
    )


def test_report_mount_path_validation_accepts_recommended_dedicated_root():
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--validate-path",
            "/srv/stock-research/theme-research-reports",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_report_mount_check_rejects_dedicated_name_symlinked_to_system_root(tmp_path):
    disguised = tmp_path / "stock-research" / "theme-research-reports"
    disguised.parent.mkdir()
    disguised.symlink_to("/etc", target_is_directory=True)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--host-only",
            str(disguised),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "resolved" in result.stderr.lower() or "dedicated" in result.stderr.lower()


@pytest.mark.parametrize(
    ("different_source", "rw"),
    [(True, False), (False, True)],
)
def test_report_mount_check_rejects_different_source_or_writable_mount(
    tmp_path, different_source, rw
):
    expected = tmp_path / "expected" / "theme-research-reports"
    actual = tmp_path / "different" / "theme-research-reports"
    expected.mkdir(parents=True)
    actual.mkdir(parents=True)
    env = _report_mount_check_env(
        tmp_path,
        source=actual if different_source else expected,
        rw=rw,
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--require-mount",
            str(expected),
            "stock_research_dashboard-api-1",
            "/app/reports/theme-research",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "mount" in result.stderr.lower()


def test_report_mount_check_accepts_matching_canonical_read_only_mount(tmp_path):
    expected = tmp_path / "expected" / "theme-research-reports"
    expected.mkdir(parents=True)
    env = _report_mount_check_env(tmp_path, source=expected, rw=False)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_report_mount.sh"),
            "--require-mount",
            str(expected),
            "stock_research_dashboard-api-1",
            "/app/reports/theme-research",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_release_sync_applies_report_schema_and_gates_runtime_health():
    script = _read("deploy/sync_dashboard_release.sh")
    checker = _read("deploy/check_theme_research_report_runtime.py")

    assert "stock_research.theme_research_report_schema --apply" in script
    assert "THEME_RESEARCH_MIGRATION_SERVICE" in script
    assert "--runtime-service ${theme_research_runtime_service_q}" in script
    assert "--index-service ${theme_research_report_index_service_q}" in script
    assert "--review-service ${theme_research_report_review_service_q}" in script
    assert "check_theme_research_report_runtime.py --schema-only" in script
    assert "check_theme_research_report_runtime.py --expected-root" in script
    assert "has_function_privilege" in checker
    assert "has_table_privilege" in checker
    assert script.index("theme_research_report_schema --apply") < script.index("up -d --force-recreate")
    assert script.index("check_theme_research_report_runtime.py --expected-root") < script.index("Running bounded external release gate")


def test_release_sync_transfers_trusted_strategy_manifest_before_external_gate():
    script = _read("deploy/sync_dashboard_release.sh")

    assert "stock_research.strategy_manifest_transfer export" in script
    assert "stock_research.strategy_manifest_transfer import" in script
    assert script.index("strategy_manifest_transfer import") < script.index("Running bounded external release gate")


def test_release_frontend_pnpm_commands_enable_ci_without_leaking_to_remote_commands(
    tmp_path,
):
    _root, env, log_file = _release_fixture(tmp_path)
    env["CI"] = "caller-value"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    commands = log_file.read_text(encoding="utf-8")
    command_lines = commands.splitlines()
    script = _read("deploy/sync_dashboard_release.sh")
    build_command = 'rtk pnpm --dir "$ROOT/dashboard" build'
    build_index = script.index(build_command)
    assert "CI=true" in script[build_index - 200 : build_index]
    install_line = next(
        line
        for line in command_lines
        if line.startswith("rtk:CI=") and " install --frozen-lockfile" in line
    )
    build_line = next(
        line
        for line in command_lines
        if line.startswith("rtk:CI=") and line.endswith(" build")
    )
    ssh_lines = [line for line in command_lines if line.startswith("ssh:CI=")]
    rsync_lines = [line for line in command_lines if line.startswith("rsync:CI=")]

    assert install_line.startswith("rtk:CI=true:")
    assert build_line.startswith("rtk:CI=true:")
    assert ssh_lines and all(
        line.startswith("ssh:CI=caller-value:") for line in ssh_lines
    )
    assert rsync_lines and all(
        line.startswith("rsync:CI=caller-value:") for line in rsync_lines
    )


def test_release_sync_defaults_to_batch_mode_and_validates_ssh_options():
    script = _read("deploy/sync_dashboard_release.sh")
    preflight = _read("deploy/check_dashboard_remote_host.sh")

    assert "BatchMode=yes" in script
    assert "STOCK_RESEARCH_SSH_CONFIG" in script
    assert "Unsupported SSH option token" in script
    assert "docker compose version" in preflight
    assert "check_dashboard_remote_host.sh" in script
    assert script.index("check_dashboard_remote_host.sh") < script.index('rsync -az --delete')


def test_remote_host_preflight_rejects_ports_owned_by_another_project(tmp_path):
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
        if [[ "$1 $2" == "compose ls" ]]; then echo '[]'; exit 0; fi
        if [[ "$1" == "ps" && "$*" == *" -a "* ]]; then exit 0; fi
        if [[ "$1" == "ps" ]]; then echo 'abc123|legacy_dashboard|api|legacy-api'; exit 0; fi
        exit 1
        """,
    )
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/check_dashboard_remote_host.sh"),
            "stock_research_dashboard",
            "8765",
            "5174",
        ],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "legacy_dashboard" in result.stderr
    assert "migration required" in result.stderr


def test_remote_host_preflight_rejects_same_project_orphan_service(tmp_path):
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
        if [[ "$1 $2" == "compose ls" ]]; then echo '[]'; exit 0; fi
        if [[ "$1" == "ps" && "$*" == *" -a "* ]]; then echo 'abc123|worker|orphan-worker|Exited (0)'; exit 0; fi
        if [[ "$1" == "ps" ]]; then exit 0; fi
        exit 1
        """,
    )
    _write_executable(fake_bin / "ss", "#!/bin/bash\nexit 1\n")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_remote_host.sh"), "stock_research_dashboard", "8765", "5174"],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "orphan-worker" in result.stderr
    assert "manual migration required" in result.stderr


def test_remote_host_preflight_rejects_non_docker_listener(tmp_path):
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
        if [[ "$1 $2" == "compose ls" ]]; then echo '[]'; exit 0; fi
        if [[ "$1" == "ps" ]]; then exit 0; fi
        exit 1
        """,
    )
    _write_executable(
        fake_bin / "ss",
        """
        #!/bin/bash
        echo 'LISTEN 0 128 127.0.0.1:8765 0.0.0.0:* users:(("python",pid=99,fd=3))'
        """,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_remote_host.sh"), "stock_research_dashboard", "8765", "5174"],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "non-Docker listener" in result.stderr


def test_remote_host_preflight_allows_expected_project_services(tmp_path):
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
        if [[ "$1 $2" == "compose ls" ]]; then echo '[]'; exit 0; fi
        if [[ "$1" == "ps" && "$*" == *"publish=8765"* ]]; then echo 'api1|stock_research_dashboard|api|canonical-api'; exit 0; fi
        if [[ "$1" == "ps" && "$*" == *"publish=5174"* ]]; then echo 'web1|stock_research_dashboard|dashboard|canonical-dashboard'; exit 0; fi
        exit 0
        """,
    )
    _write_executable(fake_bin / "ss", "#!/bin/bash\necho LISTEN\n")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_remote_host.sh"), "stock_research_dashboard", "8765", "5174"],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_release_sync_fails_before_side_effects_for_worktree_root(tmp_path):
    root = tmp_path / ".worktrees" / "candidate"
    root.mkdir(parents=True)

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=_sync_env(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Refusing disposable worktree release root" in result.stderr


def test_release_sync_executes_with_dynamic_date_python_override_and_compose_provenance(tmp_path):
    root, env, log_file = _release_fixture(tmp_path)

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    gates = (tmp_path / "release-gates.log").read_text(encoding="utf-8").splitlines()
    assert len(gates) == 2
    assert gates[0] == gates[1]
    assert "|/app|" in gates[0]
    assert "|2026-07-24|/app/src/stock_research|python:3.12.11-slim-bookworm@sha256:" in gates[0]
    assert "|nginx:1.27.5-alpine@sha256:" in gates[0]
    assert "Resolved EXPECTED_TRADE_DATE=2026-07-24" in result.stdout
    assert "Resolved EXPECTED_TRADE_DATE=2026-05-18" not in result.stdout
    assert json.loads((root / "dashboard" / "dist" / "release.json").read_text())["release_id"]
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "python:" in commands
    assert "docker compose" in commands
    assert "build api dashboard" in commands
    assert "STOCK_RESEARCH_RELEASE_ID=" in commands
    assert "STOCK_RESEARCH_FRONTEND_BUILD_ID=" in commands
    assert "2026-07-24" in commands
    assert "jqz@192.168.3.185" in commands
    assert "/home/jqz/code/stock-research-platform-main" in commands
    assert "BatchMode=yes" in commands


def test_release_sync_rejects_stale_date_from_matching_local_readiness(tmp_path):
    root, env, log_file = _release_fixture(tmp_path)
    env["FAKE_PLATFORM_LOADER_FAIL"] = "1"
    fake_bin = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        release_id="$(git -C "$FAKE_RELEASE_ROOT" rev-parse HEAD)"
        printf '{"latest_market_date":"2026-07-27","display_trade_date":"2026-07-27","runtime_provenance":{"release_id":"%s","source_root":"%s","python_package_root":"%s/src/stock_research","strategy_artifact_date":"2026-07-24"}}\n' \
          "$release_id" "$FAKE_RELEASE_ROOT" "$FAKE_RELEASE_ROOT"
        """,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unable to resolve a valid EXPECTED_TRADE_DATE" in result.stderr
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "rsync" not in commands


def test_release_sync_skips_all_mutations_when_desired_state_is_already_live(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    env["EXPECTED_TRADE_DATE"] = "2026-07-24"
    env["FAKE_RELEASE_ALREADY_LIVE"] = "1"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "deployment skipped" in result.stdout
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "rsync:" not in commands
    ssh_lines = [line for line in commands.splitlines() if line.startswith("ssh:")]
    assert len(ssh_lines) == 3
    assert "--host-only /srv/stock-research/theme-research-reports" in ssh_lines[0]
    assert "--require-mount /srv/stock-research/theme-research-reports" in ssh_lines[1]
    assert "check_theme_research_report_runtime.py --expected-root" in ssh_lines[2]
    assert all(" compose " not in line for line in ssh_lines)
    assert " build" not in commands


@pytest.mark.parametrize(
    "unsafe_root",
    ["/", "/etc", "/home", "/root", "/usr", "/var", "/opt", "/srv"],
)
def test_release_sync_rejects_broad_report_roots_before_remote_access(
    tmp_path, unsafe_root
):
    _root, env, log_file = _release_fixture(tmp_path)
    env["THEME_RESEARCH_REPORT_HOST_ROOT"] = unsafe_root

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "safe dedicated path" in result.stderr
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "ssh:" not in commands
    assert "rsync:" not in commands


@pytest.mark.parametrize(
    ("runtime_service", "index_service", "review_service"),
    [
        ("shared", "shared", "reviewer"),
        ("shared", "indexer", "shared"),
        ("runtime", "shared", "shared"),
        ("", "indexer", "reviewer"),
    ],
)
def test_release_sync_rejects_empty_or_duplicate_capability_services_before_remote_access(
    tmp_path, runtime_service, index_service, review_service
):
    _root, env, log_file = _release_fixture(tmp_path)
    env["THEME_RESEARCH_RUNTIME_SERVICE"] = runtime_service
    env["THEME_RESEARCH_REPORT_INDEX_SERVICE"] = index_service
    env["THEME_RESEARCH_REPORT_REVIEW_SERVICE"] = review_service

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "distinct non-empty" in result.stderr
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_invalid_strategy_contract_fails_before_remote_or_restart(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path, valid_manifest=False)

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_platform_date_without_exact_strategy_artifact_fails_before_remote(tmp_path):
    root, env, log_file = _release_fixture(tmp_path)
    source = root / "outputs" / "research" / "strategy_daily_eod" / "2026-07-24"
    stale = source.parent / "2026-06-01"
    source.rename(stale)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root), "-c", "user.name=Test", "-c",
            "user.email=test@example.invalid", "commit", "-qm", "stale-artifact",
        ],
        check=True,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "2026-07-24" in result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_loader_failure_does_not_scan_stale_strategy_artifacts(tmp_path):
    root, env, log_file = _release_fixture(tmp_path)
    source = root / "outputs" / "research" / "strategy_daily_eod" / "2026-07-24"
    stale = source.parent / "2026-06-01"
    source.rename(stale)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root), "-c", "user.name=Test", "-c",
            "user.email=test@example.invalid", "commit", "-qm", "stale-only",
        ],
        check=True,
    )
    env["FAKE_PLATFORM_LOADER_FAIL"] = "1"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unable to resolve" in result.stderr
    assert "2026-06-01" not in result.stdout
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_rejects_impossible_explicit_calendar_date_before_remote(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    env["EXPECTED_TRADE_DATE"] = "2026-02-30"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Invalid EXPECTED_TRADE_DATE" in result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_fails_closed_when_current_readiness_has_no_publishable_date(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    env["FAKE_STRATEGY_DATE"] = ""

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unable to resolve a valid EXPECTED_TRADE_DATE" in result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_same_project_unpublished_worker_fails_before_rsync_and_up(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    fake_bin = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_bin / "docker",
        """
        #!/bin/bash
        if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
        if [[ "$1 $2" == "compose ls" ]]; then echo '[]'; exit 0; fi
        if [[ "$1" == "ps" && "$*" == *" -a "* ]]; then echo 'worker1|worker|hidden-worker|Up 1 hour'; exit 0; fi
        if [[ "$1" == "ps" ]]; then exit 0; fi
        exit 1
        """,
    )
    _write_executable(
        fake_bin / "ssh",
        """
        #!/bin/bash
        echo "ssh:$*" >> "$FAKE_COMMAND_LOG"
        if [[ "$*" == *"--host-only"* || "$*" == *"--require-mount"* ]]; then
          exit 0
        fi
        if [[ "$*" == *"bash -s --"* ]]; then
          exec /bin/bash -s -- stock_research_dashboard 8765 5174
        fi
        exit 0
        """,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "hidden-worker" in result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "rsync:" not in commands
    assert " build api dashboard" not in commands
    assert " up -d " not in commands


def test_release_sync_rejects_dangerous_ssh_options_before_remote_access(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    env["SSH_OPTS"] = "-o ProxyCommand=touch/tmp/owned"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unsupported SSH option token" in result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_accepts_explicit_legacy_simple_ssh_options(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    env["SSH_OPTS"] = "-o PreferredAuthentications=password -o PubkeyAuthentication=no"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    commands = log_file.read_text(encoding="utf-8")
    assert "PreferredAuthentications=password" in commands
    assert "PubkeyAuthentication=no" in commands


@pytest.mark.parametrize(
    ("key", "value"),
    [("REMOTE_USER", "-oProxy"), ("REMOTE_HOST", "-malicious.example")],
)
def test_release_sync_rejects_option_like_remote_targets(tmp_path, key, value):
    _root, env, log_file = _release_fixture(tmp_path)
    env[key] = value

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "unsupported characters" in result.stderr
    commands = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "ssh:" not in commands
    assert "rsync:" not in commands


def test_release_sync_builds_and_syncs_one_identified_release():
    script = _read("deploy/sync_dashboard_release.sh")

    assert "release_id=" in script
    assert "STOCK_RESEARCH_RELEASE_ID" in script
    assert "VITE_RELEASE_ID" in script
    assert '"$ROOT/src/"' in script
    assert '"$ROOT/dashboard/dist/"' in script
    assert 'strategy_daily_eod/${EXPECTED_TRADE_DATE}' in script
    for variable in ("REMOTE_USER", "REMOTE_HOST", "REMOTE_DIR", "SSH_OPTS"):
        assert variable in script
    assert "STRATEGY_OUTPUT_ROOT" in script
    assert "dashboard-release.compose.yml up -d --force-recreate --remove-orphans api dashboard" in script
    assert "deploy/check_dashboard_release.sh" in script
    assert "deploy/validate_strategy_release.py" in script
    assert "release.json" in script
    assert "build_platform_readiness" in script
    assert "platform_daily_summary_v1" not in script
    assert "resolve-latest" not in script


def test_release_gate_checks_readiness_provenance_and_review_queue_contract():
    script = _read("deploy/check_dashboard_release.sh")
    schema_source = _read("src/stock_research/theme_research_report_schema.py")
    schema_version = re.search(
        r'^THEME_RESEARCH_REPORT_SCHEMA_VERSION = "([^"]+)"$',
        schema_source,
        re.MULTILINE,
    ).group(1)

    assert "set -euo pipefail" in script
    assert "120" in script
    assert "/api/platform/readiness" in script
    assert "/api/review-queue" in script
    assert "/release.json" in script
    assert "THEME_RESEARCH_REPORT_HEALTH_JSON" in script
    assert "schema_version" in script
    assert f'EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION:-{schema_version}' in script
    assert f'EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION="{schema_version}"' in _read(
        "deploy/sync_dashboard_release.sh"
    )
    assert "scheduler_index_diagnostics" in script
    assert "service_permissions" in script
    assert "service_identity" in script
    assert "server_version_nums" in script
    for attribute in (
        "rolcanlogin",
        "rolsuper",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
        "rolbypassrls",
    ):
        assert attribute in script
    assert "readonly" in script
    assert "latest_market_date" in script
    assert "runtime_provenance" in script
    assert "frontend_build_id" in script
    assert "python_package_root" in script
    assert "source_root" in script
    assert "requested_trade_date" in script
    assert "data_trade_date" in script
    assert "count == 5" in script
    assert "freshness_status == \"current\"" in script
    assert '-u "$DASHBOARD_AUTH"' not in script
    assert "curl_auth=(-u" not in script
    assert "umask 077" in script
    assert "chmod 600" in script
    assert "trap 'rm -rf \"$tmp_dir\"' EXIT" in script
    assert '--config "$curl_config"' in script
    for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck"):
        assert strategy_id in script


def _release_gate_env(
    tmp_path: Path,
    *,
    frontend_release_id: str,
    latest_market_date: str = "2026-07-24",
    display_trade_date: str | None = "2026-07-24",
    strategy_artifact_date: str = "2026-07-24",
    queue_trade_date: str = "2026-07-24",
) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        [[ -n "${FAKE_CURL_LOG:-}" ]] && printf 'curl\n' >> "$FAKE_CURL_LOG"
        [[ -n "${FAKE_CURL_ARGV_LOG:-}" ]] && printf '%s\n' "$*" >> "$FAKE_CURL_ARGV_LOG"
        output=''
        url=''
        config=''
        while (( $# )); do
          case "$1" in
            -o) output="$2"; shift 2 ;;
            --config) config="$2"; shift 2 ;;
            -w|--connect-timeout|--max-time|-u) shift 2 ;;
            -*) shift ;;
            *) url="$1"; shift ;;
          esac
        done
        if [[ -n "${FAKE_CURL_CONFIG_CAPTURE:-}" ]]; then
          [[ -n "$config" && -f "$config" ]] || exit 90
          cp "$config" "$FAKE_CURL_CONFIG_CAPTURE"
          if stat -f '%Lp' "$config" >/dev/null 2>&1; then
            stat -f '%Lp' "$config" > "$FAKE_CURL_CONFIG_MODE"
          else
            stat -c '%a' "$config" > "$FAKE_CURL_CONFIG_MODE"
          fi
        fi
        if [[ "$url" == */api/platform/readiness ]]; then
          printf '%s\n' "$FAKE_READINESS_JSON" > "$output"
        elif [[ "$url" == */api/research/theme-decomposition/themes ]]; then
          printf '%s\n' "$FAKE_THEME_RESEARCH_JSON" > "$output"
        elif [[ "$url" == */release.json ]]; then
          printf '{"release_id":"%s","api_base_image":"python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7","frontend_base_image":"nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"}\n' "$FAKE_FRONTEND_RELEASE_ID" > "$output"
        else
          printf '%s\n' "$FAKE_QUEUE_JSON" > "$output"
        fi
        printf '200'
        """,
    )
    readiness = {
        "latest_market_date": latest_market_date,
        "runtime_provenance": {
            "release_id": "new-release",
            "frontend_build_id": "new-release",
            "strategy_artifact_date": strategy_artifact_date,
            "source_root": "/app",
            "python_package_root": "/app/src/stock_research",
        },
    }
    if display_trade_date is not None:
        readiness["display_trade_date"] = display_trade_date
    queue = {
        "requested_trade_date": queue_trade_date,
        "trade_date": queue_trade_date,
        "groups": [
            {
                "strategy_id": strategy_id,
                "count": 5,
                "data_trade_date": queue_trade_date,
                "freshness_status": "current",
            }
            for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck")
        ],
    }
    themes = {
        "total": 25,
        "items": [
            {"theme_id": "ai_compute_infrastructure_value_chain_v1"},
            *[{"theme_id": f"theme_{index:02d}"} for index in range(1, 25)],
        ],
    }
    report_health_path = tmp_path / "theme-research-report-health.json"
    report_health_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "root": {
                    "path": "/app/reports/theme-research",
                    "exists": True,
                    "readable": True,
                    "readonly": True,
                },
                "schema": {"status": "current", "schema_version": "5"},
                "service_permissions": {
                    "runtime": {"status": "ok", "session_user": "runtime_login"},
                    "indexer": {"status": "ok", "session_user": "index_login"},
                    "reviewer": {"status": "ok", "session_user": "review_login"},
                },
                "service_identity": {
                    "status": "ok",
                    "server_version_nums": {
                        "runtime": 150000,
                        "indexer": 160000,
                        "reviewer": 160000,
                    },
                    "login_attributes": {
                        profile: {
                            "rolcanlogin": True,
                            "rolsuper": False,
                            "rolcreatedb": False,
                            "rolcreaterole": False,
                            "rolreplication": False,
                            "rolbypassrls": False,
                        }
                        for profile in ("runtime", "indexer", "reviewer")
                    },
                },
                "scheduler_index_diagnostics": {
                    "status": "ok",
                    "invalid": 0,
                    "errors": [],
                },
            }
        ),
        encoding="utf-8",
    )
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BASE_URL": "http://release.invalid",
        "EXPECTED_TRADE_DATE": "2026-07-24",
        "EXPECTED_RELEASE_ID": "new-release",
        "EXPECTED_REMOTE_SOURCE_ROOT": "/app",
        "RELEASE_CHECK_TIMEOUT_SECONDS": "1",
        "RELEASE_CHECK_RETRY_SECONDS": "1",
        "FAKE_FRONTEND_RELEASE_ID": frontend_release_id,
        "FAKE_READINESS_JSON": json.dumps(readiness),
        "FAKE_QUEUE_JSON": json.dumps(queue),
        "FAKE_THEME_RESEARCH_JSON": json.dumps(themes),
        "FAKE_CURL_LOG": str(tmp_path / "curl.log"),
        "FAKE_CURL_ARGV_LOG": str(tmp_path / "curl-argv.log"),
        "THEME_RESEARCH_REPORT_HEALTH_JSON": str(report_health_path),
    }


def test_release_gate_keeps_basic_auth_secret_out_of_curl_argv(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env["RELEASE_CHECK_TIMEOUT_SECONDS"] = "5"
    auth = 'deploy:p@ ss#\"\\word'
    capture = tmp_path / "curl-auth.conf"
    mode = tmp_path / "curl-auth.mode"
    env.update(
        {
            "DASHBOARD_AUTH": auth,
            "FAKE_CURL_CONFIG_CAPTURE": str(capture),
            "FAKE_CURL_CONFIG_MODE": str(mode),
        }
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    argv = Path(env["FAKE_CURL_ARGV_LOG"]).read_text(encoding="utf-8")
    assert auth not in argv
    assert "-u " not in argv
    assert "--config " in argv
    assert capture.read_text(encoding="utf-8") == 'user = "deploy:p@ ss#\\\"\\\\word"\n'
    assert mode.read_text(encoding="utf-8").strip() == "600"


def test_release_gate_logs_in_and_uses_session_cookie_for_protected_apis(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    fake_curl = tmp_path / "bin" / "curl"
    _write_executable(
        fake_curl,
        """
        #!/bin/bash
        printf '%s\n' "$*" >> "$FAKE_CURL_ARGV_LOG"
        output=''
        url=''
        cookie_jar=''
        cookie_file=''
        data_file=''
        while (( $# )); do
          case "$1" in
            -o) output="$2"; shift 2 ;;
            --config|-w|--connect-timeout|--max-time|-H|-X) shift 2 ;;
            --cookie-jar|-c) cookie_jar="$2"; shift 2 ;;
            --cookie|-b) cookie_file="$2"; shift 2 ;;
            --data-binary) data_file="${2#@}"; shift 2 ;;
            -*) shift ;;
            *) url="$1"; shift ;;
          esac
        done
        if [[ "$url" == */api/auth/login ]]; then
          attempts=0
          [[ -f "$FAKE_LOGIN_ATTEMPTS" ]] && attempts="$(cat "$FAKE_LOGIN_ATTEMPTS")"
          attempts=$((attempts + 1))
          printf '%s\n' "$attempts" > "$FAKE_LOGIN_ATTEMPTS"
          if (( attempts <= FAKE_LOGIN_FAILURES )); then
            printf '{"detail":"service_starting"}\n' > "$output"
            printf '503'
            exit 0
          fi
          jq -e \
            --arg username "$FAKE_LOGIN_USERNAME" \
            --arg password "$FAKE_LOGIN_PASSWORD" \
            '.username == $username and .password == $password' \
            "$data_file" >/dev/null || exit 91
          printf '# Netscape HTTP Cookie File\nrelease.invalid\tFALSE\t/\tFALSE\t0\tstock_research_session\tsession-token\n' > "$cookie_jar"
          printf '{"user":{"username":"admin"}}\n' > "$output"
          printf '200'
          exit 0
        fi
        if [[ "$url" == */release.json ]]; then
          printf '{"release_id":"%s","api_base_image":"python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7","frontend_base_image":"nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"}\n' "$FAKE_FRONTEND_RELEASE_ID" > "$output"
          printf '200'
          exit 0
        fi
        if [[ ! -f "$cookie_file" ]] || ! grep -q 'stock_research_session.*session-token' "$cookie_file"; then
          printf '{"detail":"not_authenticated"}\n' > "$output"
          printf '401'
          exit 0
        fi
        if [[ "$url" == */api/platform/readiness ]]; then
          printf '%s\n' "$FAKE_READINESS_JSON" > "$output"
        elif [[ "$url" == */api/research/theme-decomposition/themes ]]; then
          printf '%s\n' "$FAKE_THEME_RESEARCH_JSON" > "$output"
        else
          printf '%s\n' "$FAKE_QUEUE_JSON" > "$output"
        fi
        printf '200'
        """,
    )
    env.update(
        {
            "DASHBOARD_AUTH": "mqkj:outer-secret",
            "DASHBOARD_LOGIN_USERNAME": "admin",
            "DASHBOARD_LOGIN_PASSWORD": "session-secret",
            "FAKE_LOGIN_USERNAME": "admin",
            "FAKE_LOGIN_PASSWORD": "session-secret",
            "FAKE_LOGIN_ATTEMPTS": str(tmp_path / "login-attempts"),
            "FAKE_LOGIN_FAILURES": "1",
            "RELEASE_CHECK_TIMEOUT_SECONDS": "5",
        }
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    argv = Path(env["FAKE_CURL_ARGV_LOG"]).read_text(encoding="utf-8")
    assert "/api/auth/login" in argv
    assert "--cookie-jar" in argv
    assert "--cookie" in argv
    assert "outer-secret" not in argv
    assert "session-secret" not in argv


def test_release_gate_rejects_report_root_or_index_health_errors(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    health_path = Path(env["THEME_RESEARCH_REPORT_HEALTH_JSON"])
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    payload["scheduler_index_diagnostics"] = {
        "status": "error",
        "invalid": 1,
        "errors": [{"code": "INVALID_MANIFEST"}],
    }
    health_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


def test_release_gate_rejects_incomplete_theme_research_artifacts(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env["RELEASE_CHECK_TIMEOUT_SECONDS"] = "2"
    env["FAKE_THEME_RESEARCH_JSON"] = json.dumps(
        {
            "total": 24,
            "items": [{"theme_id": f"theme_{index:02d}"} for index in range(24)],
        }
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


def test_release_gate_rejects_missing_database_server_version(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    health_path = Path(env["THEME_RESEARCH_REPORT_HEALTH_JSON"])
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    payload["service_identity"]["server_version_nums"]["runtime"] = 0
    health_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


@pytest.mark.parametrize(
    ("map_name", "mutation"),
    [
        ("server_version_nums", "empty"),
        ("server_version_nums", "missing"),
        ("server_version_nums", "extra"),
        ("login_attributes", "empty"),
        ("login_attributes", "missing"),
        ("login_attributes", "extra"),
    ],
)
def test_release_gate_requires_exact_service_identity_profile_maps(
    tmp_path, map_name, mutation
):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    health_path = Path(env["THEME_RESEARCH_REPORT_HEALTH_JSON"])
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    identity_map = payload["service_identity"][map_name]
    if mutation == "empty":
        identity_map.clear()
    elif mutation == "missing":
        identity_map.pop("reviewer")
    else:
        identity_map["unexpected"] = identity_map["runtime"]
    health_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


def test_release_gate_rejects_non_object_login_attribute_profile(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    health_path = Path(env["THEME_RESEARCH_REPORT_HEALTH_JSON"])
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    payload["service_identity"]["login_attributes"]["runtime"] = None
    health_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


def test_release_gate_rejects_old_public_dist_even_when_api_reports_new_release(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="old-release")

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Dashboard release check failed" in result.stderr


def test_release_gate_accepts_matching_public_dist_api_and_queue(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env["RELEASE_CHECK_TIMEOUT_SECONDS"] = "5"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Dashboard release check passed" in result.stdout


def test_release_gate_accepts_market_date_after_expected_strategy_date(tmp_path):
    env = _release_gate_env(
        tmp_path,
        frontend_release_id="new-release",
        latest_market_date="2026-07-27",
        display_trade_date="2026-07-27",
        strategy_artifact_date="2026-07-24",
    )
    env["RELEASE_CHECK_TIMEOUT_SECONDS"] = "5"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("latest_market_date", "display_trade_date", "strategy_artifact_date"),
    [
        ("2026-07-23", "2026-07-24", "2026-07-24"),
        ("2026-07-27", "2026-07-24", "2026-06-01"),
        ("2026-07-27", "2026-06-01", "2026-07-24"),
        ("2026-98-98", "2026-07-24", "2026-07-24"),
        ("2026-07-99", "2026-07-24", "2026-07-24"),
        ("2026-7-27", "2026-07-24", "2026-07-24"),
        ("not-a-date", "2026-07-24", "2026-07-24"),
    ],
)
def test_release_gate_rejects_invalid_or_inconsistent_release_dates(
    tmp_path, latest_market_date, display_trade_date, strategy_artifact_date
):
    env = _release_gate_env(
        tmp_path,
        frontend_release_id="new-release",
        latest_market_date=latest_market_date,
        display_trade_date=display_trade_date,
        strategy_artifact_date=strategy_artifact_date,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_release_gate_accepts_missing_display_date_when_artifact_date_is_exact(tmp_path):
    env = _release_gate_env(
        tmp_path,
        frontend_release_id="new-release",
        latest_market_date="2026-07-27",
        display_trade_date=None,
        strategy_artifact_date="2026-07-24",
    )
    env["RELEASE_CHECK_TIMEOUT_SECONDS"] = "5"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_release_gate_rejects_display_date_before_expected_strategy_date(tmp_path):
    env = _release_gate_env(
        tmp_path,
        frontend_release_id="new-release",
        latest_market_date="2026-07-27",
        display_trade_date="2026-07-23",
        strategy_artifact_date="2026-07-24",
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_release_gate_rejects_malformed_expected_strategy_artifact_date(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env["EXPECTED_STRATEGY_ARTIFACT_DATE"] = "2026-7-24"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Invalid EXPECTED_STRATEGY_ARTIFACT_DATE" in result.stderr


@pytest.mark.parametrize(
    ("key", "value", "expected_error"),
    [
        ("EXPECTED_TRADE_DATE", "2026-02-30", "Invalid EXPECTED_TRADE_DATE"),
        (
            "EXPECTED_STRATEGY_ARTIFACT_DATE",
            "2026-02-30",
            "Invalid EXPECTED_STRATEGY_ARTIFACT_DATE",
        ),
    ],
)
def test_release_gate_rejects_impossible_calendar_dates_before_network(
    tmp_path, key, value, expected_error
):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env[key] = value

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr
    assert not Path(env["FAKE_CURL_LOG"]).exists()


def test_release_gate_rejects_mismatched_queue_and_artifact_dates_before_network(tmp_path):
    env = _release_gate_env(tmp_path, frontend_release_id="new-release")
    env["EXPECTED_TRADE_DATE"] = "2026-07-24"
    env["EXPECTED_STRATEGY_ARTIFACT_DATE"] = "2026-07-23"

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must equal EXPECTED_TRADE_DATE" in result.stderr
    assert not Path(env["FAKE_CURL_LOG"]).exists()


def test_release_gate_rejects_queue_date_rewrite(tmp_path):
    env = _release_gate_env(
        tmp_path,
        frontend_release_id="new-release",
        latest_market_date="2026-07-27",
        display_trade_date="2026-07-24",
        strategy_artifact_date="2026-07-24",
        queue_trade_date="2026-07-27",
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/check_dashboard_release.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_vite_build_emits_release_metadata():
    config = _read("dashboard/vite.config.ts")

    assert "VITE_RELEASE_ID" in config
    assert "release.json" in config
    assert "release_id" in config
    assert "api_base_image" in config
    assert "frontend_base_image" in config


def test_strategy_release_validator_accepts_current_official_contract():
    output_dir = Path(
        "/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-07-24"
    )
    if not output_dir.exists():
        pytest.skip("local official artifact fixture is unavailable")

    result = subprocess.run(
        [
            "/Users/xiwei/stock_research/.venv/bin/python",
            str(REPO_ROOT / "deploy/validate_strategy_release.py"),
            "--output-dir",
            str(output_dir),
            "--trade-date",
            "2026-07-24",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "strategy release contract valid" in result.stdout


@pytest.mark.parametrize(
    ("old", "new", "expected_error"),
    [
        ("lhb_shortline-2", "lhb_shortline-1", "duplicate asset"),
        ("lhb_shortline-2", "", "empty asset"),
        ("lhb_shortline-2", "lhb_shortline-99", "does not match manifest"),
        ("strategy_lhb_shortline_review.csv", "../escape.csv", "escapes release directory"),
    ],
)
def test_strategy_release_validator_rejects_duplicate_assets_and_path_traversal(
    tmp_path, old, new, expected_error
):
    root, _env, _log = _release_fixture(tmp_path)
    output_dir = root / "outputs" / "research" / "strategy_daily_eod" / "2026-07-24"
    manifest = output_dir / "review_queue_strategy_manifest.csv"
    content = manifest.read_text(encoding="utf-8")
    content = content.replace(old, new, 1)
    manifest.write_text(content, encoding="utf-8")

    result = subprocess.run(
        [
            "/Users/xiwei/stock_research/.venv/bin/python",
            str(REPO_ROOT / "deploy/validate_strategy_release.py"),
            "--output-dir",
            str(output_dir),
            "--trade-date",
            "2026-07-24",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr


def test_launchd_template_uses_selected_release_root_not_worktree():
    plist = _read("deploy/launchd/com.stockresearch.dashboard-daily-sync.plist")

    assert "/Users/xiwei/stock_research_release_20260727/deploy/sync_dashboard_release.sh" in plist
    assert ".worktrees" not in plist
    assert "/Users/xiwei/stock_research_release_20260727" in plist
    assert "<key>DASHBOARD_REMOTE_ENV_FILE</key>" in plist
    assert "<string>.env</string>" in plist
    assert "<key>STRATEGY_OUTPUT_ROOT</key>" in plist
    assert "EXPECTED_TRADE_DATE" not in plist
    assert "<integer>22</integer>" in plist
    assert "<integer>15</integer>" in plist
    assert "<integer>18</integer>" not in plist


def test_release_scripts_are_executable():
    for relative_path in (
        "deploy/sync_dashboard_release.sh",
        "deploy/check_dashboard_release.sh",
    ):
        assert (REPO_ROOT / relative_path).stat().st_mode & stat.S_IXUSR


def test_release_docs_define_single_entrypoint_environment_and_rollback():
    runbook = _read("docs/platform_external_access_runbook.md")
    canonical = _read("docs/canonical-frontend.md")

    for expected in (
        "deploy/sync_dashboard_release.sh",
        "STOCK_RESEARCH_RELEASE_ROOT",
        "EXPECTED_TRADE_DATE",
        "REMOTE_USER",
        "REMOTE_HOST",
        "REMOTE_DIR",
        "SSH_OPTS",
        "STRATEGY_OUTPUT_ROOT",
        "STOCK_RESEARCH_PYTHON",
        "LOCAL_READINESS_URL",
        "STOCK_RESEARCH_SSH_CONFIG",
        "DASHBOARD_REMOTE_ENV_FILE",
        "STOCK_RESEARCH_COMPOSE_PROJECT",
        "migration",
        "sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7",
        "sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10",
        "DASHBOARD_AUTH",
        "DASHBOARD_LOGIN_USERNAME",
        "DASHBOARD_LOGIN_PASSWORD",
        "THEME_RESEARCH_REPORT_HOST_ROOT",
        "THEME_RESEARCH_REPORT_INDEX_SERVICE",
        "THEME_RESEARCH_REPORT_REVIEW_SERVICE",
        "/srv/stock-research/theme-research-reports",
        "THEME_RESEARCH_REPORT_ROOT=/app/reports/theme-research",
        "theme_research_report_schema --apply",
        "report-index/status",
        "回滚",
    ):
        assert expected in runbook
    assert "depth 3" in runbook
    assert "0600 temporary curl configuration" in runbook
    assert "process arguments" in runbook
    assert "runtime, indexer, and reviewer aliases" in runbook
    assert "NOLOGIN role membership" in runbook
    assert "independent LOGIN credentials" in runbook
    assert "session_user" in runbook
    assert "pg_has_role" in runbook
    assert "pg_auth_members" in runbook
    assert "PostgreSQL 15" in runbook
    assert "server_version_num" in runbook
    assert "no additional role membership" in runbook
    assert "唯一入口" in runbook
    assert "deploy/sync_dashboard_release.sh" in canonical
    assert "release_id" in canonical
