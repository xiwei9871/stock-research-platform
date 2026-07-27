import json
import os
import stat
import subprocess
import textwrap
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
        exec /usr/bin/python3 "$@"
        """,
    )
    _write_executable(
        fake_bin / "rtk",
        """
        #!/bin/bash
        echo "rtk:$*" >> "$FAKE_COMMAND_LOG"
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
    for command in ("ssh", "rsync"):
        _write_executable(
            fake_bin / command,
            f"#!/bin/bash\necho \"{command}:$*\" >> \"$FAKE_COMMAND_LOG\"\n",
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
    assert "COPY src ./src" in api_dockerfile
    assert "COPY dashboard/dist ./dashboard/dist" in api_dockerfile
    assert "COPY dashboard/dist /usr/share/nginx/html" in frontend_dockerfile
    assert "COPY deploy/dashboard-nginx.conf" in frontend_dockerfile
    assert "try_files $uri $uri/ /index.html" in nginx_config
    assert "location /api/" in nginx_config
    assert "proxy_pass http://api:8765" in nginx_config
    for header in ("Host", "X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"):
        assert f"proxy_set_header {header}" in nginx_config


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
    assert "nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10" in frontend_dockerfile
    assert requirements.count("--hash=sha256:") > 30
    assert "akshare==1.18.60" in requirements_input
    assert "jsonpath==" in requirements
    assert "pydantic-core==" in requirements
    for package in ("fastapi==", "uvicorn==", "pandas==", "psycopg[binary]=="):
        assert package in requirements


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


def test_release_sync_prefers_publishable_date_from_matching_local_readiness(tmp_path):
    root, env, _log_file = _release_fixture(tmp_path)
    fake_bin = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        release_id="$(git -C "$FAKE_RELEASE_ROOT" rev-parse HEAD)"
        printf '{"latest_market_date":"2026-07-27","display_trade_date":"2026-07-24","runtime_provenance":{"release_id":"%s","source_root":"%s","python_package_root":"%s/src/stock_research","strategy_artifact_date":"2026-07-24"}}\n' \
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

    assert result.returncode == 0, result.stderr
    assert "Resolved EXPECTED_TRADE_DATE=2026-07-24" in result.stdout
    assert "Resolved EXPECTED_TRADE_DATE=2026-07-27" not in result.stdout


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
    assert "ssh:" not in commands
    assert " build" not in commands


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

    assert "set -euo pipefail" in script
    assert "120" in script
    assert "/api/platform/readiness" in script
    assert "/api/review-queue" in script
    assert "/release.json" in script
    assert "latest_market_date" in script
    assert "runtime_provenance" in script
    assert "frontend_build_id" in script
    assert "python_package_root" in script
    assert "source_root" in script
    assert "requested_trade_date" in script
    assert "data_trade_date" in script
    assert "count == 5" in script
    assert "freshness_status == \"current\"" in script
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
        output=''
        url=''
        while (( $# )); do
          case "$1" in
            -o) output="$2"; shift 2 ;;
            -w|--connect-timeout|--max-time|-u) shift 2 ;;
            -*) shift ;;
            *) url="$1"; shift ;;
          esac
        done
        if [[ "$url" == */api/platform/readiness ]]; then
          printf '%s\n' "$FAKE_READINESS_JSON" > "$output"
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
        "FAKE_CURL_LOG": str(tmp_path / "curl.log"),
    }


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
        display_trade_date="2026-07-24",
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


def test_launchd_template_uses_canonical_repo_not_worktree():
    plist = _read("deploy/launchd/com.stockresearch.dashboard-daily-sync.plist")

    assert "/Users/xiwei/stock_research/deploy/sync_dashboard_release.sh" in plist
    assert ".worktrees" not in plist
    assert "/Users/xiwei/stock_research" in plist
    assert "EXPECTED_TRADE_DATE" not in plist


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
        "回滚",
    ):
        assert expected in runbook
    assert "唯一入口" in runbook
    assert "deploy/sync_dashboard_release.sh" in canonical
    assert "release_id" in canonical
