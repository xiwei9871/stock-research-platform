from __future__ import annotations

from stock_research.research_project_v2_1.acquisition_doctor import build_provider_diagnostic


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:doctor-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


def test_doctor_redacts_proxy_credentials_and_endpoint() -> None:
    diagnostic = build_provider_diagnostic(
        generated_at="2026-07-20T08:00:00Z",
        provenance=PROVENANCE,
        environment={"HTTPS_PROXY": "http://user:secret@10.1.2.3:7890"},
        system_proxies={"https": "http://192.168.3.213:7897"},
        browser_runtime_status="available",
        search_provider_status="unavailable",
        checks=[],
    )
    rendered = str(diagnostic)
    assert "secret" not in rendered
    assert "user" not in rendered
    assert "10.1.2.3" not in rendered
    assert "192.168.3.213" not in rendered
    assert diagnostic["environment_proxy_detected"] is True
    assert diagnostic["system_proxy_detected"] is True
    assert diagnostic["proxy_endpoint_class"] == "private"
    assert diagnostic["proxy_endpoint_redacted"] == "private-proxy:789x"
    assert diagnostic["content_hash"] != "0" * 64
    assert diagnostic["diagnostic_id"].startswith("provider_diagnostic:")


def test_doctor_dry_diagnostic_marks_network_checks_not_run() -> None:
    diagnostic = build_provider_diagnostic(
        generated_at="2026-07-20T08:00:00Z",
        provenance=PROVENANCE,
        environment={},
        system_proxies={},
        browser_runtime_status="unavailable",
        search_provider_status="unavailable",
        checks=[],
    )
    assert diagnostic["dns_status"] == "unknown"
    assert diagnostic["direct_html_status"] == "not_run"
    assert diagnostic["requests_trust_mode"] == "explicit_direct"
