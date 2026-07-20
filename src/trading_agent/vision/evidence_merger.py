from typing import Any

from trading_agent.domain.enums import EvidenceUsage


def merge_evidence(
    model: dict[str, Any],
    market_data: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(model)
    blockers = list(model.get("blocking_issues", []))
    market_contract = market_data.get("contract") if market_data else None
    model_contract = model.get("contract")

    if market_contract and model_contract and market_contract != model_contract:
        blockers.append("CONTRACT_CONFLICT")
        merged["allowed_usage"] = EvidenceUsage.BLOCKED
    elif market_contract and not model_contract:
        merged["contract"] = market_contract
        blockers = [issue for issue in blockers if issue != "CONTRACT_MISSING"]

    merged["blocking_issues"] = list(dict.fromkeys(blockers))
    if merged["blocking_issues"] and "allowed_usage" not in merged:
        merged["allowed_usage"] = EvidenceUsage.QUALITATIVE_ONLY
    return merged
