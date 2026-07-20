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
    provenance: dict[str, str] = {}

    if market_contract and model_contract and market_contract != model_contract:
        blockers.append("CONTRACT_CONFLICT")
        merged["allowed_usage"] = EvidenceUsage.BLOCKED
    elif market_contract and not model_contract:
        merged["contract"] = market_contract
        provenance["contract"] = "structured_market_data"
        blockers = [issue for issue in blockers if issue != "CONTRACT_MISSING"]

    if market_data:
        for field in ("timeframe", "cutoff_time", "last_bar_closed"):
            market_value = market_data.get(field)
            if market_value is not None:
                merged[field] = market_value
                provenance[field] = "structured_market_data"
        market_indicators = market_data.get("indicators", {})
        if market_indicators:
            merged_indicators = dict(merged.get("indicators", {}))
            for group, values in market_indicators.items():
                merged_group = dict(merged_indicators.get(group) or {})
                for name, value in values.items():
                    merged_group[name] = value
                    provenance[f"indicators.{group}.{name}"] = "structured_market_data"
                merged_indicators[group] = merged_group
            merged["indicators"] = merged_indicators
        if market_data.get("last_bar_closed") is True:
            blockers = [issue for issue in blockers if issue != "BAR_CLOSE_UNKNOWN"]
        if market_data.get("price_axis_verified") is False:
            blockers.append("PRICE_AXIS_UNVERIFIED")

    merged["blocking_issues"] = list(dict.fromkeys(blockers))
    merged["field_provenance"] = provenance
    if merged.get("allowed_usage") == EvidenceUsage.BLOCKED:
        return merged
    exact_ready = bool(
        market_data
        and market_data.get("price_axis_verified") is True
        and not merged["blocking_issues"]
    )
    merged["allowed_usage"] = (
        EvidenceUsage.EXACT if exact_ready else EvidenceUsage.QUALITATIVE_ONLY
    )
    return merged
