from collections.abc import Mapping
from typing import TypedDict

from trading_agent.clarification.models import (
    ClarificationField,
    ClarificationQuestion,
)


class _QuestionCopy(TypedDict):
    question_id: str
    uncertainty: str
    question: str
    answer_examples: list[str]
    allowed_fact_fields: list[str]


class _QuestionGroup(TypedDict):
    milestone_number: int
    blocking_issues: list[str]


_FIELD_ORDER: tuple[ClarificationField, ...] = (
    "state_bar_closed",
    "execution_bar_closed",
    "position_behavior_state",
    "open_interest_change",
    "price_confirmation",
)

_QUESTION_COPY: dict[ClarificationField, _QuestionCopy] = {
    "state_bar_closed": {
        "question_id": "clarify-state-bar-closed",
        "allowed_fact_fields": ["state_bar_closed"],
        "uncertainty": "日线最后一根 K 线的收盘状态无法从截图可靠确认。",
        "question": "请确认：日线最后一根 K 线是否已经收盘？",
        "answer_examples": ["日线已收盘", "日线尚未收盘"],
    },
    "execution_bar_closed": {
        "question_id": "clarify-execution-bar-closed",
        "allowed_fact_fields": ["execution_bar_closed"],
        "uncertainty": "执行周期最后一根 K 线的收盘状态无法从截图可靠确认。",
        "question": "请确认：60 分钟最后一根 K 线是否已经收盘？",
        "answer_examples": ["60 分钟 K 线已收盘", "60 分钟 K 线尚未收盘"],
    },
    "position_behavior_state": {
        "question_id": "clarify-position-behavior",
        "allowed_fact_fields": ["position_behavior_state"],
        "uncertainty": "CCYD 或持仓行为标签无法可靠读取。",
        "question": "请说明 CCYD 当前显示的持仓行为和可见数值。",
        "answer_examples": ["多头减仓 4425", "空头增仓 3200"],
    },
    "open_interest_change": {
        "question_id": "clarify-open-interest-change",
        "allowed_fact_fields": ["open_interest_change"],
        "uncertainty": "策略缺少可验证的持仓量变化。",
        "question": "请提供当前可见的持仓量变化数值，增加为正数，减少为负数。",
        "answer_examples": ["持仓量增加 1200", "持仓量减少 4425"],
    },
    "price_confirmation": {
        "question_id": "clarify-price-confirmation",
        "allowed_fact_fields": [
            "price_confirmation",
            "price_confirmation_direction",
            "price_confirmation_type",
        ],
        "uncertainty": "执行周期尚未形成可验证的价格确认。",
        "question": "请确认已收盘执行周期是否出现突破、守住、回踩或结构失效，并说明方向。",
        "answer_examples": ["向下突破后回踩未站回", "向上突破并守住", "尚未确认"],
    },
}


def _field_for_blocker(blocker: str) -> ClarificationField | None:
    normalized = blocker.upper()
    if (
        normalized in {"BAR_CLOSE_UNKNOWN", "UNCLOSED_STATE_BAR"}
        or ("日K线" in blocker and "收盘" in blocker)
        or ("日线" in blocker and "收盘" in blocker)
    ):
        return "state_bar_closed"
    if (
        normalized in {
            "EXECUTION_CUTOFF_TIME_MISSING",
            "EXECUTION_CUTOFF_MISSING",
        }
        or ("60分钟" in blocker and "收盘" in blocker)
        or ("60 分钟" in blocker and "收盘" in blocker)
    ):
        return "execution_bar_closed"
    if "CCYD" in normalized or "持仓行为" in blocker:
        return "position_behavior_state"
    if normalized == "OPEN_INTEREST_MISSING" or "持仓量" in blocker:
        return "open_interest_change"
    if normalized == "PRICE_NOT_CONFIRMED":
        return "price_confirmation"
    return None


def _price_confirmation_known(analysis: Mapping[str, object]) -> bool:
    milestones = analysis.get("milestones")
    if isinstance(milestones, list):
        blockers: set[str] = set()
        for milestone in milestones:
            if not isinstance(milestone, Mapping):
                continue
            milestone_blockers = milestone.get("blockers")
            if not isinstance(milestone_blockers, list):
                continue
            blockers.update(str(blocker).upper() for blocker in milestone_blockers)
        if blockers & {
            "EXECUTION_CUTOFF_MISSING",
            "EXECUTION_CUTOFF_IN_FUTURE",
            "EXECUTION_CUTOFF_TIME_MISSING",
            "EXECUTION_CUTOFF_INVALID",
            "EXECUTION_DATA_STALE",
        }:
            return False
    evidence_set = analysis.get("evidence_set")
    if not isinstance(evidence_set, list):
        return False
    for raw_evidence in evidence_set:
        if not isinstance(raw_evidence, Mapping):
            continue
        if raw_evidence.get("image_role") != "EXECUTION_60M":
            continue
        if raw_evidence.get("allowed_usage") == "BLOCKED":
            continue
        if raw_evidence.get("last_bar_closed") is not True:
            continue
        evidence_blockers = raw_evidence.get("blocking_issues")
        if isinstance(evidence_blockers, list) and {
            str(item).upper() for item in evidence_blockers
        } & {
            "EXECUTION_CUTOFF_MISSING",
            "EXECUTION_CUTOFF_IN_FUTURE",
            "EXECUTION_CUTOFF_TIME_MISSING",
            "EXECUTION_CUTOFF_INVALID",
            "EXECUTION_DATA_STALE",
        }:
            continue
        facts = raw_evidence.get("strategy_facts")
        if not isinstance(facts, Mapping):
            continue
        if not isinstance(facts.get("price_confirmation"), bool):
            continue
        confirmation = facts.get("price_confirmation")
        required_fields = ["price_confirmation"]
        if confirmation is True:
            if facts.get("price_confirmation_direction") == "UNKNOWN":
                continue
            if facts.get("price_confirmation_type") == "UNKNOWN":
                continue
            required_fields.extend(
                ["price_confirmation_direction", "price_confirmation_type"]
            )
        provenance = raw_evidence.get("field_provenance")
        if isinstance(provenance, Mapping) and all(
            provenance.get(f"strategy_facts.{field}")
            in {"structured_market_data", "user_confirmed"}
            for field in required_fields
        ):
            return True
        support = raw_evidence.get("strategy_fact_support")
        if not isinstance(support, Mapping):
            continue
        observations = raw_evidence.get("observations")
        observation_ids = {
            str(item.get("evidence_id"))
            for item in observations
            if isinstance(item, Mapping) and item.get("evidence_id")
        } if isinstance(observations, list) else set()
        supports_all_fields = True
        for field in required_fields:
            field_support = support.get(field)
            if not isinstance(field_support, Mapping):
                supports_all_fields = False
                break
            confidence = field_support.get("confidence")
            refs = field_support.get("evidence_refs")
            if (
                not isinstance(confidence, (int, float))
                or confidence < 0.8
                or not isinstance(refs, list)
                or not refs
                or not {str(ref) for ref in refs} <= observation_ids
            ):
                supports_all_fields = False
                break
        if supports_all_fields:
            return True
    return False


def questions_for_analysis(
    analysis: Mapping[str, object],
) -> list[ClarificationQuestion]:
    grouped: dict[ClarificationField, _QuestionGroup] = {}
    milestones = analysis.get("milestones")
    if not isinstance(milestones, list):
        return []
    for milestone in milestones:
        if not isinstance(milestone, Mapping):
            continue
        number = milestone.get("number")
        blockers = milestone.get("blockers")
        if not isinstance(number, int) or not isinstance(blockers, list):
            continue
        for raw_blocker in blockers:
            blocker = str(raw_blocker)
            field = _field_for_blocker(blocker)
            if field is None:
                continue
            if field == "price_confirmation" and _price_confirmation_known(analysis):
                continue
            item = grouped.setdefault(
                field,
                {
                    "milestone_number": number,
                    "blocking_issues": [],
                },
            )
            issues = item["blocking_issues"]
            if blocker not in issues:
                issues.append(blocker)
    questions: list[ClarificationQuestion] = []
    for field in _FIELD_ORDER:
        group = grouped.get(field)
        if group is None:
            continue
        question_copy = _QUESTION_COPY[field]
        questions.append(
            ClarificationQuestion(
                field=field,
                milestone_number=group["milestone_number"],
                blocking_issues=group["blocking_issues"],
                **question_copy,
            )
        )
    return questions
