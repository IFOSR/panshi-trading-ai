from trading_agent.domain.enums import EvidenceUsage
from trading_agent.vision.evidence_merger import merge_evidence


def test_conflicting_model_and_market_contract_values_create_a_blocker() -> None:
    merged = merge_evidence(
        model={"contract": "rb2605", "blocking_issues": []},
        market_data={"contract": "rb2610"},
    )

    assert "CONTRACT_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_verified_market_contract_fills_missing_model_contract() -> None:
    merged = merge_evidence(
        model={"contract": None, "blocking_issues": ["CONTRACT_MISSING"]},
        market_data={"contract": "rb2610"},
    )

    assert merged["contract"] == "rb2610"
    assert "CONTRACT_MISSING" not in merged["blocking_issues"]
