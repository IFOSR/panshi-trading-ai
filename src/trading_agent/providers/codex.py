import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import (
    Evidence,
    FactSupport,
    ScreenshotEvidence,
    StrategyEvidenceFacts,
)
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import provider_prompt_sha256, render_provider_prompt


Runner = Callable[
    [list[str], float, Path, str, dict[str, str]],
    CompletedProcess[str],
]


_PROVIDER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_PROVIDER_FIELDS = {
    "name",
    "base_url",
    "wire_api",
    "requires_openai_auth",
    "env_key",
}
ProviderConfig = tuple[str, dict[str, str | bool]]


def _machine_default_provider() -> ProviderConfig | None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return None
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    provider = config.get("model_provider")
    providers = config.get("model_providers")
    if (
        not isinstance(provider, str)
        or not _PROVIDER_NAME_PATTERN.fullmatch(provider)
        or not isinstance(providers, dict)
    ):
        return None
    selected = providers.get(provider)
    if not isinstance(selected, dict):
        return None
    safe: dict[str, str | bool] = {}
    for key in _SAFE_PROVIDER_FIELDS:
        value = selected.get(key)
        if isinstance(value, (str, bool)):
            safe[key] = value
    env_key = safe.get("env_key")
    if env_key is not None and (
        not isinstance(env_key, str) or not _ENV_KEY_PATTERN.fullmatch(env_key)
    ):
        return None
    return provider, safe


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported TOML value: {type(value)!r}")


def _isolated_codex_config(
    provider: ProviderConfig | None,
) -> str:
    lines = [
        'default_permissions = "vision-read"',
        'approval_policy = "never"',
    ]
    if provider is not None:
        name, values = provider
        lines.insert(0, f"model_provider = {_toml_value(name)}")
        lines.extend(["", f"[model_providers.{name}]"])
        for key in ("name", "base_url", "wire_api", "requires_openai_auth", "env_key"):
            if key in values:
                lines.append(f"{key} = {_toml_value(values[key])}")
    lines.extend(
        [
            "",
            "[shell_environment_policy]",
            'inherit = "none"',
            "",
            "[permissions.vision-read]",
            'description = "Read only isolated workspace"',
            "",
            "[permissions.vision-read.filesystem]",
            '":minimal" = "read"',
            '":workspace_roots" = "read"',
            "",
            "[permissions.vision-read.network]",
            "enabled = false",
            "",
        ]
    )
    return "\n".join(lines)


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


class StrategyFactsExtraction(StrictExtractionModel):
    trend_bias: str = Field(pattern="^(BULLISH|BEARISH|RANGE|UNKNOWN)$")
    price_location: str = Field(
        pattern=(
            "^(ABOVE_BOLL_UPPER|BETWEEN_UPPER_AND_MID|"
            "BELOW_BOLL_MID_ABOVE_LOWER|BELOW_BOLL_LOWER|"
            "AT_RANGE_SUPPORT|AT_RANGE_RESISTANCE|UNKNOWN)$"
        )
    )
    volume_state: str = Field(
        pattern="^(ABOVE_BOTH_AVERAGES|BETWEEN_AVERAGES|BELOW_BOTH_AVERAGES|UNKNOWN)$"
    )
    momentum_state: str = Field(
        pattern=(
            "^(BULLISH_STRENGTHENING|BEARISH_STRENGTHENING|"
            "BULLISH_RECOVERY|BEARISH_RECOVERY|DIVERGENCE|UNKNOWN)$"
        )
    )
    position_behavior: str = Field(
        pattern=(
            "^(LONG_BUILD_SHORT_COVER|SHORT_BUILD_LONG_EXIT|"
            "POSITION_BUILDING|POSITION_LIQUIDATION|UNKNOWN)$"
        )
    )
    price_confirmation: bool | None
    price_confirmation_direction: str = Field(
        pattern="^(BULLISH|BEARISH|UNKNOWN)$"
    )
    price_confirmation_type: str = Field(
        pattern="^(BREAKOUT|HOLD|PULLBACK|STRUCTURAL_FAILURE|UNKNOWN)$"
    )


class FactSupportExtraction(StrictExtractionModel):
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1)


class StrategyFactSupportExtraction(StrictExtractionModel):
    trend_bias: FactSupportExtraction | None
    price_location: FactSupportExtraction | None
    volume_state: FactSupportExtraction | None
    momentum_state: FactSupportExtraction | None
    position_behavior: FactSupportExtraction | None
    price_confirmation: FactSupportExtraction | None
    price_confirmation_direction: FactSupportExtraction | None
    price_confirmation_type: FactSupportExtraction | None


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
    strategy_facts: StrategyFactsExtraction
    strategy_fact_support: StrategyFactSupportExtraction
    observations: list[ObservationExtraction]
    blocking_issues: list[str]
    allowed_usage: EvidenceUsage

    @field_validator("cutoff_time")
    @classmethod
    def validate_cutoff_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import date, datetime

        normalized = value.replace("/", "-")
        if len(normalized) == 10:
            date.fromisoformat(normalized)
            return normalized
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            from zoneinfo import ZoneInfo

            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return parsed.isoformat()


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
        model_provider: str | None = None,
        provider_base_url: str | None = None,
        provider_env_key: str | None = None,
    ) -> None:
        override_values = (model_provider, provider_base_url, provider_env_key)
        if any(override_values) and not all(override_values):
            raise ValueError(
                "Codex provider override requires provider, base URL, and env key"
            )
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.model_provider = model_provider
        self.provider_base_url = provider_base_url
        self.provider_env_key = provider_env_key

    def build_command(
        self,
        request: VisionRequest,
        schema_path: Path,
        output_path: Path,
    ) -> list[str]:
        command = [
            "codex",
            "exec",
            "--strict-config",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-rules",
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
        prompt = render_provider_prompt(
            request.prompt_version,
            provider="codex",
        )
        prompt_hash = provider_prompt_sha256(
            request.prompt_version,
            provider="codex",
        )
        if (
            self.provider_env_key is not None
            and not os.environ.get(self.provider_env_key)
        ):
            raise ProviderUnavailable(
                f"codex provider credential {self.provider_env_key} is not configured"
            )
        artifacts = [
            inspect_original_image(path, storage_root=request.storage_root)
            for path in request.image_paths
        ]
        provider_config: ProviderConfig | None
        if self.model_provider is not None:
            assert self.provider_base_url is not None
            assert self.provider_env_key is not None
            provider_config = (
                self.model_provider,
                {
                    "name": self.model_provider,
                    "base_url": self.provider_base_url,
                    "wire_api": "responses",
                    "requires_openai_auth": False,
                    "env_key": self.provider_env_key,
                },
            )
        else:
            provider_config = _machine_default_provider()
        with tempfile.TemporaryDirectory(prefix="trading-agent-codex-") as temp_dir:
            isolated_root = Path(temp_dir)
            isolated_codex_home = isolated_root / ".codex"
            isolated_tmp = isolated_root / "tmp"
            isolated_codex_home.mkdir()
            isolated_tmp.mkdir()
            (isolated_codex_home / "config.toml").write_text(
                _isolated_codex_config(provider_config),
                encoding="utf-8",
            )
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
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "LANG", "LC_ALL"}
            }
            environment.update(
                {
                    "HOME": str(isolated_root),
                    "CODEX_HOME": str(isolated_codex_home),
                    "TMPDIR": str(isolated_tmp),
                }
            )
            provider_env_key = None
            if provider_config is not None:
                raw_env_key = provider_config[1].get("env_key")
                if isinstance(raw_env_key, str):
                    provider_env_key = raw_env_key
            if provider_env_key and provider_env_key in os.environ:
                environment[provider_env_key] = os.environ[provider_env_key]
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
                evidence_description=observation.evidence_description,
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
            strategy_facts=StrategyEvidenceFacts.model_validate(
                extraction.strategy_facts.model_dump()
            ),
            strategy_fact_support={
                key: FactSupport.model_validate(value)
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
            provider="codex",
            model=self.model,
            prompt_version=request.prompt_version,
            prompt_sha256=prompt_hash,
            image_sha256=artifacts[0].sha256,
        )
