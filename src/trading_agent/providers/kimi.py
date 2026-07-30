import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

from trading_agent.domain.evidence import Evidence, ScreenshotEvidence, StrategyEvidenceFacts
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.providers.codex import ScreenshotExtraction, enforce_safe_usage
from trading_agent.providers.kimi_acp import AcpCompletionClient, KimiAcpClient
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import provider_prompt_sha256, render_provider_prompt


UNSUPPORTED_IMAGE_MARKERS = (
    "不支持图像输入",
    "无法读取和分析该图片",
    "does not support image",
    "cannot read the image",
)


def configured_kimi_supports_images(
    config_path: Path | None = None,
    model: str = "default",
) -> bool:
    config_path = config_path or Path.home() / ".kimi-code" / "config.toml"
    if not config_path.exists():
        return False
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    selected_model = config.get("default_model") if model == "default" else model
    models = config.get("models")
    if not isinstance(selected_model, str) or not isinstance(models, dict):
        return False
    selected = models.get(selected_model)
    if not isinstance(selected, dict):
        return False
    capabilities = selected.get("capabilities")
    return (
        isinstance(capabilities, list)
        and all(isinstance(capability, str) for capability in capabilities)
        and "image_in" in capabilities
    )


class KimiVisionProvider:
    def __init__(
        self,
        model: str = "default",
        client: AcpCompletionClient | None = None,
        timeout_seconds: float = 120.0,
        capability_checker: Callable[[], bool] = configured_kimi_supports_images,
    ) -> None:
        self.model = model
        self.client = client or KimiAcpClient(
            model=model,
            timeout_seconds=timeout_seconds,
        )
        self.capability_checker = (
            capability_checker
            if capability_checker is not configured_kimi_supports_images
            else lambda: configured_kimi_supports_images(model=self.model)
        )

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        if not self.capability_checker():
            raise ProviderUnavailable("kimi current model has no verified image capability")
        if not request.privacy_assessment.safe_for_model:
            raise ValueError("privacy assessment blocks model transmission")
        artifacts = [
            inspect_original_image(path, storage_root=request.storage_root)
            for path in request.image_paths
        ]
        image_suffixes = [artifact.path.suffix.lower() for artifact in artifacts]
        prompt = render_provider_prompt(
            request.prompt_version,
            provider="kimi",
            image_suffixes=image_suffixes,
        )
        prompt_hash = provider_prompt_sha256(
            request.prompt_version,
            provider="kimi",
            image_suffixes=image_suffixes,
        )
        output = self.client.complete(
            prompt,
            image_paths=[artifact.path for artifact in artifacts],
        ).strip()
        if any(marker.lower() in output.lower() for marker in UNSUPPORTED_IMAGE_MARKERS):
            raise ProviderUnavailable("kimi current model does not support image input")

        try:
            extraction = ScreenshotExtraction.model_validate(json.loads(output))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderResponseError("kimi returned invalid screenshot evidence") from exc

        observations = [
            Evidence(
                evidence_id=observation.evidence_id,
                kind=observation.kind,
                value=observation.conclusion,
                confidence=observation.confidence,
                provenance=f"kimi:{self.model}",
                visible_text=observation.visible_text,
                image_path=str(request.image_paths[observation.source_image_index]),
                evidence_description=observation.evidence_description,
            )
            for observation in extraction.observations
            if observation.source_image_index < len(request.image_paths)
        ]
        return ScreenshotEvidence(
            image_role=extraction.image_role,
            instrument=extraction.instrument,
            contract=extraction.contract,
            timeframe=extraction.timeframe,
            cutoff_time=extraction.cutoff_time,
            last_bar_closed=extraction.last_bar_closed,
            indicators=extraction.indicators.model_dump(),
            strategy_facts=StrategyEvidenceFacts.model_validate(
                extraction.strategy_facts.model_dump()
            ),
            strategy_fact_support={
                key: value
                for key, value in extraction.strategy_fact_support.model_dump(
                    exclude_none=True
                ).items()
            },
            field_evidence_refs={
                f"strategy_facts.{key}": value["evidence_refs"]
                for key, value in extraction.strategy_fact_support.model_dump(
                    exclude_none=True
                ).items()
            },
            observations=observations,
            blocking_issues=extraction.blocking_issues,
            allowed_usage=enforce_safe_usage(extraction),
            provider="kimi",
            model=self.model,
            prompt_version=request.prompt_version,
            prompt_sha256=prompt_hash,
            image_sha256=artifacts[0].sha256,
        )
