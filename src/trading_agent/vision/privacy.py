from pydantic import BaseModel, Field


class PrivacyAssessment(BaseModel):
    contains_account_identifiers: bool = False
    sensitive_fields: list[str] = Field(default_factory=list)
    safe_for_model: bool = True
