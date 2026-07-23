from __future__ import annotations

import pytest

from stock_research.ai_pcb_yanbaoke_evidence_triage import (
    validate_er_disposition,
    validate_primary_classification,
)


def test_rejects_direct_evidence_and_er_sufficiency_states():
    validate_primary_classification("primary_source_lead")
    validate_er_disposition("source_discovery_only")

    with pytest.raises(ValueError, match="unsupported primary classification"):
        validate_primary_classification("direct_evidence")
    with pytest.raises(ValueError, match="unsupported ER disposition"):
        validate_er_disposition("sufficient")
