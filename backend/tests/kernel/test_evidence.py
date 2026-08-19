from __future__ import annotations

import pytest
from app.kernel.evidence.model import (
    EvidenceEventType,
    EvidenceLevel,
    IllegalEvidencePromotion,
    promote_evidence,
)


def test_evidence_promotion_legal_steps():
    assert (
        promote_evidence(
            EvidenceLevel.L1_INFERRED,
            EvidenceEventType.ARTIFACT_SUPPORTED,
        )
        == EvidenceLevel.L2_SUPPORTED
    )
    assert (
        promote_evidence(
            EvidenceLevel.L2_SUPPORTED,
            EvidenceEventType.OBSERVATION_RECORDED,
        )
        == EvidenceLevel.L3_OBSERVED
    )
    assert (
        promote_evidence(
            EvidenceLevel.L3_OBSERVED,
            EvidenceEventType.ATTESTATION_RECORDED,
        )
        == EvidenceLevel.L4_ATTESTED
    )


@pytest.mark.parametrize(
    ("current", "event"),
    [
        (EvidenceLevel.L1_INFERRED, EvidenceEventType.OBSERVATION_RECORDED),
        (EvidenceLevel.L1_INFERRED, EvidenceEventType.ATTESTATION_RECORDED),
        (EvidenceLevel.L2_SUPPORTED, EvidenceEventType.ARTIFACT_SUPPORTED),
        (EvidenceLevel.L2_SUPPORTED, EvidenceEventType.ATTESTATION_RECORDED),
        (EvidenceLevel.L3_OBSERVED, EvidenceEventType.ARTIFACT_SUPPORTED),
        (EvidenceLevel.L3_OBSERVED, EvidenceEventType.OBSERVATION_RECORDED),
        (EvidenceLevel.L4_ATTESTED, EvidenceEventType.ATTESTATION_RECORDED),
    ],
)
def test_evidence_invalid_promotion_raises(current, event):
    with pytest.raises(IllegalEvidencePromotion):
        promote_evidence(current, event)
