from pydantic import BaseModel, Field

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.vision.prompts import prompt_sha256


STRATEGY_VERSION = "china-futures-eight-step-v1"
RISK_VERSION = "china-futures-risk-v1"


class AnalysisAudit(BaseModel):
    model_version: str
    prompt_version: str
    prompt_sha256: str
    strategy_id: str
    strategy_version: str
    risk_version: str
    rule_versions: list[str] = Field(min_length=1)
    model_inputs: list["ModelInputAudit"] = Field(min_length=1)


class ModelInputAudit(BaseModel):
    provider: str
    model_version: str
    prompt_version: str
    prompt_sha256: str
    image_sha256: str


def build_analysis_audit(
    evidence: ScreenshotEvidence | list[ScreenshotEvidence],
    milestones: list[MilestoneResult] | list[dict],
    *,
    strategy_id: str = "structure_confirmation",
    strategy_version: str = "1.0.0",
) -> AnalysisAudit:
    evidence_set = evidence if isinstance(evidence, list) else [evidence]
    primary = evidence_set[0]
    rule_versions: list[str] = []
    for milestone in milestones:
        values = (
            milestone.rule_ids
            if isinstance(milestone, MilestoneResult)
            else milestone.get("rule_ids", [])
        )
        rule_versions.extend(str(value) for value in values)
    return AnalysisAudit(
        model_version=primary.model,
        prompt_version=primary.prompt_version,
        prompt_sha256=(
            primary.prompt_sha256 or prompt_sha256(primary.prompt_version)
        ),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        risk_version=RISK_VERSION,
        rule_versions=list(dict.fromkeys(rule_versions)),
        model_inputs=[
            ModelInputAudit(
                provider=item.provider,
                model_version=item.model,
                prompt_version=item.prompt_version,
                prompt_sha256=(
                    item.prompt_sha256 or prompt_sha256(item.prompt_version)
                ),
                image_sha256=item.image_sha256,
            )
            for item in evidence_set
        ],
    )


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
