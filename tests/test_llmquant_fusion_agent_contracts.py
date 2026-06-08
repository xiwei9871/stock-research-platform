from stock_research.agents.contracts import AgentObservation, AgentReport, EvidenceReference
from stock_research.agents.review import ReviewAgent


def test_llmquant_fusion_risk_review_observation_passes_existing_review_agent():
    report = AgentReport(
        trade_date="2026-06-08",
        mode="watchlist",
        observations=[
            AgentObservation(
                agent_role="risk",
                subject="risk-review:2026-06-08:000001.SZ",
                decision_label="谨慎",
                data_facts=[
                    "risk alert severity is high",
                    "market state report marks liquidity as neutral",
                ],
                factor_results=[
                    "sector concentration is above the configured review threshold",
                ],
                backtest_findings=[
                    "shadow outcome review shows elevated drawdown in comparable cases",
                ],
                agent_reasoning=[
                    "risk evidence supports a human follow-up before watchlist escalation",
                ],
                unverified_hypotheses=[
                    "latest post-close announcement has not been reviewed",
                ],
                evidence=[
                    EvidenceReference(
                        artifact_id="risk_alert:2026-06-08:000001.SZ",
                        evidence_type="risk_alert_report",
                        path="reports/daily_research/risk_alerts/risk_alert_report_2026-06-08.md",
                        summary="Daily risk alert report for the reviewed candidate",
                    )
                ],
            )
        ],
    )

    result = ReviewAgent().review(report)

    assert result.status == "passed"
    assert result.blocker_count == 0


def test_llmquant_fusion_watchlist_memo_without_evidence_is_rejected():
    report = AgentReport(
        trade_date="2026-06-08",
        mode="watchlist",
        observations=[
            AgentObservation(
                agent_role="watchlist",
                subject="watchlist-memo:2026-06-08:000002.SZ",
                decision_label="观察",
                data_facts=[
                    "candidate appears in the daily TopN artifact",
                ],
                factor_results=[
                    "factor rank is within the review band",
                ],
                backtest_findings=[
                    "retention evidence is not attached to this memo",
                ],
                agent_reasoning=[
                    "candidate should remain under review until missing evidence is attached",
                ],
                unverified_hypotheses=[
                    "stock report coverage freshness still needs review",
                ],
                evidence=[],
            )
        ],
    )

    result = ReviewAgent().review(report)

    assert result.status == "rejected"
    assert "missing_evidence" in {issue.code for issue in result.issues}


def test_llmquant_fusion_trading_instruction_is_rejected_even_with_evidence():
    report = AgentReport(
        trade_date="2026-06-08",
        mode="watchlist",
        observations=[
            AgentObservation(
                agent_role="watchlist",
                subject="watchlist-memo:2026-06-08:000003.SZ",
                decision_label="候选",
                data_facts=[
                    "candidate appears in the daily TopN artifact",
                ],
                factor_results=[
                    "factor rank is within the review band",
                ],
                backtest_findings=[
                    "run card is available for the reviewed daily score",
                ],
                agent_reasoning=[
                    "必须买入 because the score is high",
                ],
                unverified_hypotheses=[],
                evidence=[
                    EvidenceReference(
                        artifact_id="topn:2026-06-08:000003.SZ",
                        evidence_type="daily_topn_report",
                        path="reports/daily_research/topn/daily_topn_2026-06-08.md",
                        summary="Daily TopN report for the reviewed candidate",
                    )
                ],
            )
        ],
    )

    result = ReviewAgent().review(report)

    assert result.status == "rejected"
    assert "banned_trading_instruction" in {issue.code for issue in result.issues}
