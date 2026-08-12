import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
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
from trading_agent.providers.extraction import ScreenshotExtraction, enforce_safe_usage
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import provider_prompt_sha256, render_provider_prompt


Runner = Callable[
    [list[str], float, Path, str, dict[str, str]],
    CompletedProcess[str],
]
UNSUPPORTED_IMAGE_MARKERS = (
    "不支持图像输入",
    "无法读取和分析该图片",
    "does not support image",
    "cannot read the image",
)


def _run(
    command: list[str],
    timeout: float,
    cwd: Path,
    stdin: str,
    env: dict[str, str],
) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
        env=env,
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


def trusted_external_isolation_checker(
    *,
    verified: bool,
    provider: str | None,
) -> Callable[[], bool]:
    provider_name = provider.strip().lower() if provider else ""
    externally_isolated = (
        verified
        and bool(provider_name)
        and not provider_name.startswith("kimi")
    )
    return lambda: externally_isolated


class KimiVisionProvider:
    def __init__(
        self,
        model: str = "default",
        runner: Runner = _run,
        timeout_seconds: float = 120.0,
        capability_checker: Callable[[], bool] = configured_kimi_supports_images,
        isolation_checker: Callable[[], bool] = lambda: False,
    ) -> None:
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.capability_checker = (
            capability_checker
            if capability_checker is not configured_kimi_supports_images
            else lambda: configured_kimi_supports_images(model=self.model)
        )
        self.isolation_checker = isolation_checker

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        if not self.capability_checker():
            raise ProviderUnavailable("kimi current model has no verified image capability")
        if not self.isolation_checker():
            raise ProviderUnavailable(
                "kimi image provider requires a verified tool isolation boundary"
            )
        if not request.privacy_assessment.safe_for_model:
            raise ValueError("privacy assessment blocks model transmission")
        artifacts = [
            inspect_original_image(path, storage_root=request.storage_root)
            for path in request.image_paths
        ]
        with tempfile.TemporaryDirectory(prefix="trading-agent-kimi-") as temp_dir:
            isolated_root = Path(temp_dir)
            empty_skills = isolated_root / "skills"
            empty_skills.mkdir()
            isolated_paths: list[Path] = []
            for index, artifact in enumerate(artifacts):
                isolated_path = isolated_root / f"image-{index}{artifact.path.suffix.lower()}"
                shutil.copyfile(artifact.path, isolated_path)
                isolated_paths.append(isolated_path)
            image_suffixes = [path.suffix for path in isolated_paths]
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
            command = [
                "kimi",
                "-p",
                prompt,
                "--output-format",
                "text",
                "--skills-dir",
                str(empty_skills),
            ]
            if self.model != "default":
                command.extend(["--model", self.model])
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}
            }

            try:
                completed = self.runner(
                    command,
                    self.timeout_seconds,
                    isolated_root,
                    "",
                    environment,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable(f"kimi image provider unavailable: {exc}") from exc

        output = completed.stdout.strip()
        if completed.returncode != 0:
            raise ProviderUnavailable(
                f"kimi image provider failed with exit {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
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
