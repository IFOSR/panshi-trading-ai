from collections.abc import Sequence

from trading_agent.clarification.models import ClarificationFact
from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import Evidence, FactSupport, ScreenshotEvidence


def _role_for_field(field: str) -> str:
    if field.startswith("execution_") or field.startswith("price_confirmation"):
        return "EXECUTION_60M"
    return "STATE_DAILY"


def _strategy_field(field: str) -> str | None:
    return {
        "position_behavior_state": "position_behavior",
        "price_confirmation": "price_confirmation",
        "price_confirmation_direction": "price_confirmation_direction",
        "price_confirmation_type": "price_confirmation_type",
    }.get(field)


def _has_supported_fact(evidence: ScreenshotEvidence, field: str) -> bool:
    provenance = evidence.field_provenance.get(f"strategy_facts.{field}")
    if provenance in {"structured_market_data", "user_confirmed"}:
        return True
    support = evidence.strategy_fact_support.get(field)
    observation_ids = {item.evidence_id for item in evidence.observations}
    return bool(
        support
        and support.confidence >= 0.8
        and set(support.evidence_refs) <= observation_ids
    )


def _record_fact(
    evidence: ScreenshotEvidence,
    fact: ClarificationFact,
    *,
    clarification_id: str,
    field_path: str,
) -> None:
    evidence_id = f"user-confirmed-{clarification_id}-{fact.field}"
    evidence.observations.append(
        Evidence(
            evidence_id=evidence_id,
            kind=fact.field,
            value=fact.value,
            confidence=1.0,
            provenance="user_confirmed",
            evidence_description=(
                f"{fact.explanation} 来源澄清记录 {clarification_id}。"
            ),
        )
    )
    evidence.field_provenance[field_path] = "user_confirmed"
    evidence.field_evidence_refs[field_path] = [evidence_id]
    strategy_field = _strategy_field(fact.field)
    if strategy_field:
        evidence.strategy_fact_support[strategy_field] = FactSupport(
            confidence=1.0,
            evidence_refs=[evidence_id],
        )


def _apply_fact(
    evidence: ScreenshotEvidence,
    fact: ClarificationFact,
    *,
    clarification_id: str,
) -> bool:
    strategy_field = _strategy_field(fact.field)
    if fact.field in {"state_bar_closed", "execution_bar_closed"}:
        current_bar_closed = evidence.last_bar_closed
        if current_bar_closed is not None and current_bar_closed != fact.value:
            return False
        evidence.last_bar_closed = bool(fact.value)
        _record_fact(
            evidence,
            fact,
            clarification_id=clarification_id,
            field_path="last_bar_closed",
        )
        return True
    if fact.field == "open_interest_change":
        current_open_interest = evidence.open_interest_change
        open_interest_value = float(fact.value)
        if (
            current_open_interest is not None
            and current_open_interest != open_interest_value
        ):
            return False
        evidence.open_interest_change = open_interest_value
        _record_fact(
            evidence,
            fact,
            clarification_id=clarification_id,
            field_path="open_interest_change",
        )
        return True
    if strategy_field:
        current_strategy_value = getattr(evidence.strategy_facts, strategy_field)
        unknown = current_strategy_value in {None, "UNKNOWN"}
        if not unknown and current_strategy_value != fact.value and _has_supported_fact(
            evidence, strategy_field
        ):
            return False
        setattr(evidence.strategy_facts, strategy_field, fact.value)
        _record_fact(
            evidence,
            fact,
            clarification_id=clarification_id,
            field_path=f"strategy_facts.{strategy_field}",
        )
        return True
    if fact.field in {"contract", "timeframe", "cutoff_time"}:
        current_identity = getattr(evidence, fact.field)
        identity_value = str(fact.value).strip()
        if (
            current_identity not in {None, ""}
            and str(current_identity).strip().casefold()
            != identity_value.casefold()
        ):
            return False
        setattr(evidence, fact.field, identity_value)
        _record_fact(
            evidence,
            fact,
            clarification_id=clarification_id,
            field_path=fact.field,
        )
        return True
    return False


def apply_confirmed_facts(
    evidence_set: Sequence[ScreenshotEvidence],
    facts: Sequence[ClarificationFact],
    *,
    clarification_id: str,
) -> list[ScreenshotEvidence]:
    merged = [item.model_copy(deep=True) for item in evidence_set]
    for fact in facts:
        role = _role_for_field(fact.field)
        target = next(
            (item for item in merged if item.image_role == role),
            None,
        )
        if target is None:
            target = merged[0] if merged else None
        if target is None:
            continue
        applied = _apply_fact(
            target,
            fact,
            clarification_id=clarification_id,
        )
        if not applied:
            target.blocking_issues = list(
                dict.fromkeys(
                    [*target.blocking_issues, "USER_CLARIFICATION_CONFLICT"]
                )
            )
            target.allowed_usage = EvidenceUsage.BLOCKED
            continue
        for evidence in merged:
            evidence.blocking_issues = [
                issue
                for issue in evidence.blocking_issues
                if issue not in fact.resolves_blockers
            ]
    return merged
