from pydantic import ValidationError

from trading_agent.domain.decision import ActionDecision
from trading_agent.rendering.models import RenderedDecision, ValidationResult


def validate_rendered_response(
    decision: ActionDecision,
    payload: dict[str, object],
) -> ValidationResult:
    try:
        rendered = RenderedDecision.model_validate(payload)
    except ValidationError:
        return ValidationResult(is_valid=False, errors=["SCHEMA_INVALID"])
    errors = []
    if rendered.action != decision.action:
        errors.append("ACTION_MISMATCH")
    for name in (
        "supporting_steps", "blocking_steps", "upgrade_conditions",
        "invalidation_conditions", "next_milestone",
    ):
        if getattr(rendered, name) != getattr(decision, name):
            errors.append(f"{name.upper()}_MISMATCH")
    return ValidationResult(is_valid=not errors, errors=errors)
