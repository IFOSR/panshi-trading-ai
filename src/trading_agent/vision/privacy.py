from pydantic import BaseModel, Field

from trading_agent.domain.enums import ImageRole


class PrivacyAssessment(BaseModel):
    contains_account_identifiers: bool = False
    sensitive_fields: list[str] = Field(default_factory=list)
    safe_for_model: bool = True


MODEL_SAFE_ROLES = {
    ImageRole.STATE_DAILY,
    ImageRole.EXECUTION_60M,
    ImageRole.MEMBER_POSITION,
    ImageRole.CONTRACT_ROLLOVER,
}


def assess_upload_privacy(
    *,
    image_role: ImageRole,
    role_confirmed: bool,
    privacy_reviewed: bool,
    trusted_review: bool = False,
) -> PrivacyAssessment:
    contains_account_identifiers = image_role == ImageRole.ACCOUNT_POSITION
    safe = (
        role_confirmed
        and privacy_reviewed
        and trusted_review
        and image_role in MODEL_SAFE_ROLES
        and not contains_account_identifiers
    )
    sensitive_fields = ["account_identifiers"] if contains_account_identifiers else []
    return PrivacyAssessment(
        contains_account_identifiers=contains_account_identifiers,
        sensitive_fields=sensitive_fields,
        safe_for_model=safe,
    )
