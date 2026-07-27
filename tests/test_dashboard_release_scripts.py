import os
import json
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
    ):
        source = REPO_ROOT / "deploy" / name
        if source.exists():
            (root / "deploy" / name).write_bytes(source.read_bytes())
    _write_executable(root / "deploy" / "check_dashboard_release.sh", "#!/bin/bash\nexit 0\n")

    output_dir = root / "outputs" / "research" / "strategy_daily_eod" / "2026-07-24"
    output_dir.mkdir(parents=True)
    strategy_ids = ("lhb_shortline", "mid_trend", "tech_bottleneck")
    count = 5 if valid_manifest else 4
    manifest_rows = ["trade_date,strategy_id,rank,review_tier"]
    for strategy_id in strategy_ids:
        rows = ["trade_date,strategy_id,rank,review_tier"]
        for rank in range(1, count + 1):
            row = f"2026-07-24,{strategy_id},{rank},top5_focus"
            manifest_rows.append(row)
            rows.append(row)
        filename = {
            "lhb_shortline": "strategy_lhb_shortline_review.csv",
            "mid_trend": "strategy_mid_trend_review.csv",
            "tech_bottleneck": "strategy_tech_bottleneck_review.csv",
        }[strategy_id]
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
        exec /usr/bin/python3 "$@"
        """,
    )
    _write_executable(
        fake_bin / "rtk",
        """
        #!/bin/bash
        echo "rtk:$*" >> "$FAKE_COMMAND_LOG"
        if [[ "$1" == "pnpm" ]]; then
          mkdir -p "$FAKE_RELEASE_ROOT/dashboard/dist"
          printf '{"release_id":"%s"}\n' "$VITE_RELEASE_ID" > "$FAKE_RELEASE_ROOT/dashboard/dist/release.json"
        fi
        """,
    )
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        echo '{"latest_market_date":"2026-07-24"}'
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
    assert "docker compose" in script and "build api dashboard" in script
    assert "--force-recreate api dashboard" in script
    assert "STOCK_RESEARCH_RELEASE_ROOT" in compose
    assert "STOCK_RESEARCH_RELEASE_ID" in compose
    assert "STOCK_RESEARCH_FRONTEND_BUILD_ID" in compose
    assert "COPY src ./src" in api_dockerfile
    assert "COPY dashboard/dist ./dashboard/dist" in api_dockerfile
    assert "COPY dashboard/dist /usr/share/nginx/html" in frontend_dockerfile
    assert "COPY deploy/dashboard-nginx.conf" in frontend_dockerfile
    assert "try_files $uri $uri/ /index.html" in nginx_config


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
    assert "Resolved EXPECTED_TRADE_DATE=2026-07-24" in result.stdout
    assert json.loads((root / "dashboard" / "dist" / "release.json").read_text())["release_id"]
    commands = log_file.read_text(encoding="utf-8")
    assert "python:" in commands
    assert "docker compose" in commands
    assert "build api dashboard" in commands
    assert "STOCK_RESEARCH_RELEASE_ID=" in commands
    assert "STOCK_RESEARCH_FRONTEND_BUILD_ID=" in commands
    assert "2026-07-24" in commands
    assert "jqz@192.168.3.185" in commands
    assert "/home/jqz/code/stock-research-platform-main" in commands


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
    assert "dashboard-release.compose.yml up -d --force-recreate api dashboard" in script
    assert "deploy/check_dashboard_release.sh" in script
    assert "deploy/validate_strategy_release.py" in script
    assert "release.json" in script


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


def _release_gate_env(tmp_path: Path, *, frontend_release_id: str) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
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
          printf '%s\n' '{"latest_market_date":"2026-07-24","runtime_provenance":{"release_id":"new-release","frontend_build_id":"new-release","strategy_artifact_date":"2026-07-24","source_root":"/app","python_package_root":"/app/src/stock_research"}}' > "$output"
        elif [[ "$url" == */release.json ]]; then
          printf '{"release_id":"%s"}\n' "$FAKE_FRONTEND_RELEASE_ID" > "$output"
        else
          printf '%s\n' '{"requested_trade_date":"2026-07-24","trade_date":"2026-07-24","groups":[{"strategy_id":"lhb_shortline","count":5,"data_trade_date":"2026-07-24","freshness_status":"current"},{"strategy_id":"mid_trend","count":5,"data_trade_date":"2026-07-24","freshness_status":"current"},{"strategy_id":"tech_bottleneck","count":5,"data_trade_date":"2026-07-24","freshness_status":"current"}]}' > "$output"
        fi
        printf '200'
        """,
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


def test_vite_build_emits_release_metadata():
    config = _read("dashboard/vite.config.ts")

    assert "VITE_RELEASE_ID" in config
    assert "release.json" in config
    assert "release_id" in config


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
        "DASHBOARD_AUTH",
        "回滚",
    ):
        assert expected in runbook
    assert "唯一入口" in runbook
    assert "deploy/sync_dashboard_release.sh" in canonical
    assert "release_id" in canonical
