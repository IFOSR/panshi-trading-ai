import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import Evidence, ScreenshotEvidence
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import CHART_EVIDENCE_PROMPT


Runner = Callable[
    [list[str], float, Path, str, dict[str, str]],
    CompletedProcess[str],
]


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BollExtraction(StrictExtractionModel):
    period: int | None
    mid: float | None = Field(allow_inf_nan=False)
    upper: float | None = Field(allow_inf_nan=False)
    lower: float | None = Field(allow_inf_nan=False)


class MacdExtraction(StrictExtractionModel):
    fast: int | None
    slow: int | None
    signal: int | None
    dif: float | None = Field(allow_inf_nan=False)
    dea: float | None = Field(allow_inf_nan=False)
    histogram: float | None = Field(allow_inf_nan=False)


class VolumeExtraction(StrictExtractionModel):
    current: float | None = Field(allow_inf_nan=False)
    ma_short: float | None = Field(allow_inf_nan=False)
    ma_long: float | None = Field(allow_inf_nan=False)


class PositionBehaviorExtraction(StrictExtractionModel):
    label: str | None = Field(max_length=80)
    value: float | None = Field(allow_inf_nan=False)
    interpretation: str | None = Field(max_length=500)


class IndicatorExtraction(StrictExtractionModel):
    boll: BollExtraction | None
    macd: MacdExtraction | None
    volume: VolumeExtraction | None
    position_behavior: PositionBehaviorExtraction | None
    notes: list[str]


class ObservationExtraction(StrictExtractionModel):
    evidence_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    conclusion: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    visible_text: str | None = Field(max_length=500)
    evidence_description: str = Field(min_length=1, max_length=1000)
    source_image_index: int = Field(ge=0)


class ScreenshotExtraction(StrictExtractionModel):
    image_role: str = Field(pattern="^(STATE_DAILY|EXECUTION_60M|MEMBER_POSITION|CONTRACT_ROLLOVER|ACCOUNT_POSITION|AUXILIARY)$")
    instrument: str | None = Field(max_length=80)
    contract: str | None = Field(max_length=40)
    timeframe: str | None = Field(pattern="^(1d|D1|60m|1h|H1)$")
    cutoff_time: str | None = Field(max_length=40)
    last_bar_closed: bool | None
    indicators: IndicatorExtraction
    observations: list[ObservationExtraction]
    blocking_issues: list[str]
    allowed_usage: EvidenceUsage

    @field_validator("cutoff_time")
    @classmethod
    def validate_cutoff_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import datetime

        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("cutoff_time must include timezone")
        return value


def enforce_safe_usage(extraction: ScreenshotExtraction) -> EvidenceUsage:
    if extraction.allowed_usage == EvidenceUsage.EXACT:
        return EvidenceUsage.QUALITATIVE_ONLY
    return extraction.allowed_usage


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
        input=stdin,
        env=env,
    )


class CodexVisionProvider:
    def __init__(
        self,
        model: str = "gpt-5.6-sol",
        runner: Runner = _run,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def build_command(
        self,
        request: VisionRequest,
        schema_path: Path,
        output_path: Path,
    ) -> list[str]:
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "-C",
            str(schema_path.parent),
            "--model",
            self.model,
        ]
        for image_path in request.image_paths:
            command.extend(["--image", str(image_path)])
        command.extend(
            [
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
        )
        return command

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        if not request.privacy_assessment.safe_for_model:
            raise ValueError("privacy assessment blocks model transmission")
        artifacts = [
            inspect_original_image(path, storage_root=request.storage_root)
            for path in request.image_paths
        ]
        with tempfile.TemporaryDirectory(prefix="trading-agent-codex-") as temp_dir:
            isolated_root = Path(temp_dir)
            isolated_paths: list[Path] = []
            for index, artifact in enumerate(artifacts):
                isolated_path = isolated_root / f"image-{index}{artifact.path.suffix.lower()}"
                shutil.copyfile(artifact.path, isolated_path)
                isolated_paths.append(isolated_path)

            schema_path = isolated_root / "schema.json"
            output_path = isolated_root / "output.json"
            schema_path.write_text(
                json.dumps(ScreenshotExtraction.model_json_schema(), ensure_ascii=False),
                encoding="utf-8",
            )
            isolated_request = request.model_copy(
                update={
                    "image_paths": isolated_paths,
                    "storage_root": isolated_root,
                }
            )
            command = self.build_command(isolated_request, schema_path, output_path)
            user_context = (request.user_context or "").replace("\x00", "")[:2000]
            prompt = CHART_EVIDENCE_PROMPT
            if user_context:
                prompt += f"\n用户上下文：{user_context}"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "TMPDIR"}
            }
            try:
                completed = self.runner(
                    command,
                    self.timeout_seconds,
                    isolated_root,
                    prompt,
                    environment,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable(f"codex image provider unavailable: {exc}") from exc

            if completed.returncode != 0:
                raise ProviderUnavailable(
                    f"codex image provider failed with exit {completed.returncode}: "
                    f"{completed.stderr.strip()}"
                )
            if not output_path.exists():
                raise ProviderResponseError("codex did not produce an output message")

            try:
                extraction = ScreenshotExtraction.model_validate_json(
                    output_path.read_text(encoding="utf-8")
                )
            except ValidationError as exc:
                raise ProviderResponseError("codex returned invalid screenshot evidence") from exc

        observations = [
            Evidence(
                evidence_id=observation.evidence_id,
                kind=observation.kind,
                value=observation.conclusion,
                confidence=observation.confidence,
                provenance=f"codex:{self.model}",
                visible_text=observation.visible_text,
                image_path=str(artifacts[observation.source_image_index].path),
            )
            for observation in extraction.observations
            if observation.source_image_index < len(artifacts)
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
            provider="codex",
            model=self.model,
            prompt_version=request.prompt_version,
            image_sha256=artifacts[0].sha256,
        )
