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


def test_structured_market_fields_override_model_with_provenance() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T14:59:00+08:00",
            "last_bar_closed": None,
            "indicators": {"boll": {"mid": 3500.0}},
            "blocking_issues": ["BAR_CLOSE_UNKNOWN"],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T15:00:00+08:00",
            "last_bar_closed": True,
            "indicators": {"boll": {"mid": 3512.0}},
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T15:00:00+08:00"
    assert merged["indicators"]["boll"]["mid"] == 3512.0
    assert merged["field_provenance"]["indicators.boll.mid"] == "structured_market_data"
    assert "BAR_CLOSE_UNKNOWN" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_missing_verified_price_axis_blocks_exact_trade_levels() -> None:
    merged = merge_evidence(
        model={"contract": "rb2610", "blocking_issues": []},
        market_data={"contract": "rb2610", "price_axis_verified": False},
    )

    assert "PRICE_AXIS_UNVERIFIED" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.QUALITATIVE_ONLY
