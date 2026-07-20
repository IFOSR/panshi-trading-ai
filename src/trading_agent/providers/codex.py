import json
import subprocess
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import Evidence, ScreenshotEvidence
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import CHART_EVIDENCE_PROMPT


Runner = Callable[[list[str], float], CompletedProcess[str]]


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BollExtraction(StrictExtractionModel):
    period: int | None
    mid: float | None
    upper: float | None
    lower: float | None


class MacdExtraction(StrictExtractionModel):
    fast: int | None
    slow: int | None
    signal: int | None
    dif: float | None
    dea: float | None
    histogram: float | None


class VolumeExtraction(StrictExtractionModel):
    current: float | None
    ma_short: float | None
    ma_long: float | None


class PositionBehaviorExtraction(StrictExtractionModel):
    label: str | None
    value: float | None
    interpretation: str | None


class IndicatorExtraction(StrictExtractionModel):
    boll: BollExtraction | None
    macd: MacdExtraction | None
    volume: VolumeExtraction | None
    position_behavior: PositionBehaviorExtraction | None
    notes: list[str]


class ObservationExtraction(StrictExtractionModel):
    evidence_id: str
    kind: str
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    visible_text: str | None
    evidence_description: str


class ScreenshotExtraction(StrictExtractionModel):
    image_role: str
    instrument: str | None
    contract: str | None
    timeframe: str | None
    cutoff_time: str | None
    last_bar_closed: bool | None
    indicators: IndicatorExtraction
    observations: list[ObservationExtraction]
    blocking_issues: list[str]
    allowed_usage: EvidenceUsage


def enforce_safe_usage(extraction: ScreenshotExtraction) -> EvidenceUsage:
    critical_fields_present = (
        extraction.contract is not None
        and extraction.timeframe is not None
        and extraction.cutoff_time is not None
        and extraction.last_bar_closed is True
    )
    if extraction.allowed_usage == EvidenceUsage.EXACT and not critical_fields_present:
        return EvidenceUsage.QUALITATIVE_ONLY
    return extraction.allowed_usage


def _run(command: list[str], timeout: float) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
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
            "--sandbox",
            "read-only",
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
                CHART_EVIDENCE_PROMPT
                + (
                    f"\n用户上下文：{request.user_context}"
                    if request.user_context
                    else ""
                ),
            ]
        )
        return command

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        artifacts = [inspect_original_image(path) for path in request.image_paths]
        with tempfile.TemporaryDirectory(prefix="trading-agent-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "output.json"
            schema_path.write_text(
                json.dumps(ScreenshotExtraction.model_json_schema(), ensure_ascii=False),
                encoding="utf-8",
            )
            command = self.build_command(request, schema_path, output_path)
            try:
                completed = self.runner(command, self.timeout_seconds)
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
            provider="codex",
            model=self.model,
            prompt_version=request.prompt_version,
            image_sha256=artifacts[0].sha256,
        )
