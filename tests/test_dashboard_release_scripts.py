import os
import stat
import subprocess
from pathlib import Path


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


def test_release_sync_rejects_worktrees_dirty_roots_and_import_mismatches():
    script = _read("deploy/sync_dashboard_release.sh")

    assert "set -euo pipefail" in script
    assert "*/.worktrees/*" in script
    assert "Refusing disposable worktree release root" in script
    assert "status --porcelain --untracked-files=all" in script
    assert "Refusing dirty release root" in script
    assert '"$ROOT/.venv/bin/python"' in script
    assert "import stock_research" in script
    assert "Python import root mismatch" in script


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
    assert "docker compose up -d --force-recreate api dashboard" in script
    assert "deploy/check_dashboard_release.sh" in script


def test_release_gate_checks_readiness_provenance_and_review_queue_contract():
    script = _read("deploy/check_dashboard_release.sh")

    assert "set -euo pipefail" in script
    assert "120" in script
    assert "/api/platform/readiness" in script
    assert "/api/review-queue" in script
    assert "latest_market_date" in script
    assert "runtime_provenance" in script
    assert "frontend_build_id" in script
    assert "requested_trade_date" in script
    assert "data_trade_date" in script
    assert "count == 5" in script
    assert "freshness_status == \"current\"" in script
    for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck"):
        assert strategy_id in script


def test_launchd_template_uses_canonical_repo_not_worktree():
    plist = _read("deploy/launchd/com.stockresearch.dashboard-daily-sync.plist")

    assert "/Users/xiwei/stock_research/deploy/sync_dashboard_release.sh" in plist
    assert ".worktrees" not in plist
    assert "/Users/xiwei/stock_research" in plist


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
        "DASHBOARD_AUTH",
        "回滚",
    ):
        assert expected in runbook
    assert "唯一入口" in runbook
    assert "deploy/sync_dashboard_release.sh" in canonical
    assert "release_id" in canonical
