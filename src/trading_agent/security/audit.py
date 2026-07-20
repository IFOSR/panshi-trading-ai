from pydantic import BaseModel, Field


class AnalysisAudit(BaseModel):
    model_version: str
    prompt_version: str
    strategy_version: str
    risk_version: str
    rule_versions: list[str] = Field(min_length=1)


def build_model_trace(
    prompt_version: str,
    model: str,
    user_context: str,
    sensitive_values: list[str],
) -> dict[str, str]:
    scrubbed = user_context
    for value in sensitive_values:
        scrubbed = scrubbed.replace(value, "[REDACTED]")
    return {
        "prompt_version": prompt_version,
        "model": model,
        "user_context": scrubbed,
    }
