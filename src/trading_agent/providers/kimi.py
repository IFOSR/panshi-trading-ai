import json
import subprocess
from subprocess import CompletedProcess
from typing import Callable

from pydantic import ValidationError

from trading_agent.domain.evidence import Evidence, ScreenshotEvidence
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.providers.codex import ScreenshotExtraction, enforce_safe_usage
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import CHART_EVIDENCE_PROMPT


Runner = Callable[[list[str], float], CompletedProcess[str]]
UNSUPPORTED_IMAGE_MARKERS = (
    "不支持图像输入",
    "无法读取和分析该图片",
    "does not support image",
    "cannot read the image",
)


def _run(command: list[str], timeout: float) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class KimiVisionProvider:
    def __init__(
        self,
        model: str = "default",
        runner: Runner = _run,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        artifacts = [inspect_original_image(path) for path in request.image_paths]
        image_list = "\n".join(str(path) for path in request.image_paths)
        prompt = (
            CHART_EVIDENCE_PROMPT
            + "\n请直接读取以下工作区原始图片文件：\n"
            + image_list
            + "\n只输出JSON。"
        )
        command = ["kimi", "-p", prompt, "--output-format", "text"]
        if self.model != "default":
            command.extend(["--model", self.model])

        try:
            completed = self.runner(command, self.timeout_seconds)
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
                image_path=str(request.image_paths[0]),
            )
            for observation in extraction.observations
        ]
        return ScreenshotEvidence(
            image_role=extraction.image_role,
            instrument=extraction.instrument,
            contract=extraction.contract,
            timeframe=extraction.timeframe,
            cutoff_time=extraction.cutoff_time,
            last_bar_closed=extraction.last_bar_closed,
            indicators=extraction.indicators.model_dump(),
            observations=observations,
            blocking_issues=extraction.blocking_issues,
            allowed_usage=enforce_safe_usage(extraction),
            provider="kimi",
            model=self.model,
            prompt_version=request.prompt_version,
            image_sha256=artifacts[0].sha256,
        )
