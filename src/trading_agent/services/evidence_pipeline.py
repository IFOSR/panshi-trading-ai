from collections.abc import Mapping, Sequence
from pathlib import Path

from trading_agent.domain.enums import EvidenceUsage, ImageRole
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.resolver import MarketDataResolver, verify_and_merge_evidence
from trading_agent.providers.base import VisionProvider, VisionRequest
from trading_agent.vision.privacy import PrivacyAssessment
from trading_agent.vision.prompts import prompt_sha256


def _replaceable_with_structured_market_data(
    evidence: ScreenshotEvidence,
) -> bool:
    return (
        evidence.provider == "privacy-gate"
        and evidence.allowed_usage == EvidenceUsage.BLOCKED
        and "PRIVACY_REVIEW_REQUIRED" in evidence.blocking_issues
    )


def _contract_is_reusable(evidence: ScreenshotEvidence) -> bool:
    return bool(evidence.contract) and "CONTRACT_CONFLICT" not in {
        issue.upper() for issue in evidence.blocking_issues
    }


def _privacy_blocked_evidence(image: Mapping[str, object]) -> ScreenshotEvidence:
    return ScreenshotEvidence(
        image_role=str(image.get("image_role", ImageRole.AUXILIARY.value)),
        provider="privacy-gate",
        model="none",
        prompt_version="privacy-policy-v1",
        prompt_sha256=prompt_sha256("privacy-policy-v1"),
        image_sha256=str(image.get("sha256", "")),
        source_image_id=str(image.get("image_id") or "") or None,
        source_image_path=str(image.get("path") or "") or None,
        allowed_usage=EvidenceUsage.BLOCKED,
        blocking_issues=["PRIVACY_REVIEW_REQUIRED"],
    )


def _apply_confirmed_role(
    evidence: ScreenshotEvidence,
    image: Mapping[str, object],
) -> ScreenshotEvidence:
    if not image.get("role_confirmed"):
        return evidence
    declared_role = str(image.get("image_role", ImageRole.AUXILIARY.value))
    provenance = dict(evidence.field_provenance)
    provenance["image_role"] = "user_confirmed"
    return evidence.model_copy(
        update={
            "image_role": declared_role,
            "field_provenance": provenance,
            "source_image_id": str(image.get("image_id") or "") or None,
            "source_image_path": str(image.get("path") or "") or None,
        }
    )


def extract_case_evidence(
    *,
    case_state: Mapping[str, object],
    images: Sequence[Mapping[str, object]],
    provider: VisionProvider,
    market_data_resolver: MarketDataResolver,
    storage_root: Path,
    previous_evidence_set: Sequence[Mapping[str, object]] = (),
) -> list[ScreenshotEvidence]:
    extracted = extract_original_images(
        images=images,
        provider=provider,
        storage_root=storage_root,
        previous_evidence_set=previous_evidence_set,
    )
    return merge_case_market_data(
        case_state=case_state,
        evidence_set=extracted,
        market_data_resolver=market_data_resolver,
    )


def extract_original_images(
    *,
    images: Sequence[Mapping[str, object]],
    provider: VisionProvider,
    storage_root: Path,
    previous_evidence_set: Sequence[Mapping[str, object]] = (),
) -> list[ScreenshotEvidence]:
    active_by_role: dict[str, Mapping[str, object]] = {}
    for image in images:
        active_by_role[str(image.get("image_role", ImageRole.AUXILIARY.value))] = image
    active_images = [
        image for image in images if image in active_by_role.values()
    ]
    cached_by_image_id = {
        str(item.get("source_image_id")): ScreenshotEvidence.model_validate(item)
        for item in previous_evidence_set
        if item.get("source_image_id")
    }
    results: list[ScreenshotEvidence] = []
    for image in active_images:
        image_id = str(image.get("image_id") or "")
        if image_id and image_id in cached_by_image_id:
            results.append(cached_by_image_id[image_id])
            continue
        if not bool(image.get("safe_for_model")):
            results.append(_privacy_blocked_evidence(image))
            continue
        declared_role = str(image.get("image_role", ImageRole.AUXILIARY.value))
        evidence = provider.analyze(
            VisionRequest(
                prompt_version="chart-evidence-v2",
                image_paths=[Path(str(image["path"]))],
                storage_root=storage_root,
                privacy_assessment=PrivacyAssessment(safe_for_model=True),
                user_context=(
                    f"用户确认的截图角色：{declared_role}。"
                    "该角色仅作为元数据，不得覆盖图片中可见事实。"
                ),
            )
        )
        evidence = _apply_confirmed_role(evidence, image)
        results.append(evidence)
    return results


def merge_case_market_data(
    *,
    case_state: Mapping[str, object],
    evidence_set: Sequence[ScreenshotEvidence],
    market_data_resolver: MarketDataResolver,
) -> list[ScreenshotEvidence]:
    merged = [
        verify_and_merge_evidence(
            evidence,
            market_data_resolver.resolve(case_state, evidence),
        )
        for evidence in evidence_set
    ]
    existing_roles = {
        evidence.image_role
        for evidence in merged
        if not _replaceable_with_structured_market_data(evidence)
    }
    contract = str(case_state.get("contract") or "").strip()
    if not contract:
        contract = next(
            (
                str(evidence.contract).strip()
                for evidence in reversed(merged)
                if (
                    evidence.image_role == ImageRole.STATE_DAILY.value
                    and _contract_is_reusable(evidence)
                )
            ),
            "",
        )
    if not contract:
        contract = next(
            (
                str(evidence.contract).strip()
                for evidence in reversed(merged)
                if _contract_is_reusable(evidence)
            ),
            "",
        )
    resolved_contract = contract or None
    for role, timeframe in (
        (ImageRole.STATE_DAILY.value, "1d"),
        (ImageRole.EXECUTION_60M.value, "60m"),
    ):
        if role in existing_roles:
            continue
        structured = ScreenshotEvidence(
            image_role=role,
            contract=resolved_contract,
            timeframe=timeframe,
            provider="structured-market-data",
            model="deterministic",
            prompt_version="market-data-v1",
            image_sha256=(
                f"structured-market-data:{resolved_contract or 'unknown'}:{role}"
            ),
        )
        snapshot = market_data_resolver.resolve(case_state, structured)
        if snapshot is None:
            continue
        merged = [
            evidence
            for evidence in merged
            if not (
                evidence.image_role == role
                and _replaceable_with_structured_market_data(evidence)
            )
        ]
        merged.append(verify_and_merge_evidence(structured, snapshot))
        existing_roles.add(role)
    return merged


def primary_evidence(evidence_set: Sequence[ScreenshotEvidence]) -> ScreenshotEvidence:
    return next(
        (
            evidence
            for evidence in reversed(evidence_set)
            if evidence.image_role == ImageRole.STATE_DAILY.value
        ),
        evidence_set[-1],
    )
