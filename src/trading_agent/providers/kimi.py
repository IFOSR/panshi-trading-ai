import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
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


def configured_kimi_supports_images() -> bool:
    config_path = Path.home() / ".kimi-code" / "config.toml"
    if not config_path.exists():
        return False
    text = config_path.read_text(encoding="utf-8")
    capability_lists = re.findall(r"capabilities\s*=\s*\[([^\]]*)\]", text)
    return any("image_in" in capabilities for capabilities in capability_lists)


class KimiVisionProvider:
    def __init__(
        self,
        model: str = "default",
        runner: Runner = _run,
        timeout_seconds: float = 120.0,
        capability_checker: Callable[[], bool] = configured_kimi_supports_images,
    ) -> None:
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.capability_checker = capability_checker

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        if not self.capability_checker():
            raise ProviderUnavailable("kimi current model has no verified image capability")
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
            image_list = "\n".join(str(path) for path in isolated_paths)
            user_context = (request.user_context or "").replace("\x00", "")[:2000]
            prompt = (
                CHART_EVIDENCE_PROMPT.replace("不调用任何外部工具，", "")
                + "\n仅允许读取以下隔离目录中的原始图片文件：\n"
                + image_list
                + "\n只输出JSON。"
            )
            if user_context:
                prompt += f"\n用户上下文：{user_context}"
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
            observations=observations,
            blocking_issues=extraction.blocking_issues,
            allowed_usage=enforce_safe_usage(extraction),
            provider="kimi",
            model=self.model,
            prompt_version=request.prompt_version,
            image_sha256=artifacts[0].sha256,
        )
