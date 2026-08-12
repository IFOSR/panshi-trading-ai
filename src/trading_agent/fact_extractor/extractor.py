"""FactExtractor - extracts facts from user messages based on strategy requirements."""

import re

from trading_agent.fact_extractor.models import ExtractionStatus, FactExtractionResult
from trading_agent.strategies.contracts import FactRequirement, StrategyPlugin


class FactExtractor:
    def __init__(self, strategy: StrategyPlugin) -> None:
        self.strategy = strategy
        self.manifest = strategy.manifest

    def extract(
        self,
        message: str,
        conversation_history: list[dict],
        attachments: list[dict],
    ) -> FactExtractionResult:
        required_facts = self.strategy.required_facts(
            self._build_context(conversation_history, attachments),
        )

        # Extract facts from message and context
        extracted: dict[str, str | None] = {}

        for fact in required_facts:
            value = self._extract_field(message, fact, conversation_history)
            if value is None and fact.default:
                value = fact.default
            extracted[fact.field] = value

        # Determine missing required fields
        missing: list[FactRequirement] = []
        questions: list[str] = []
        for fact in required_facts:
            if fact.required and not extracted.get(fact.field):
                missing.append(fact)
                questions.append(
                    f"请提供{fact.label}：{fact.description}"
                )

        status = (
            ExtractionStatus.COMPLETE if not missing
            else ExtractionStatus.MISSING_INFO
        )

        return FactExtractionResult(
            status=status,
            extracted_facts=extracted,
            missing_fields=missing,
            clarification_questions=questions,
            strategy_id=self.manifest.strategy_id,
            version=self.manifest.version,
        )

    def _build_context(
        self,
        history: list[dict],
        attachments: list[dict],
    ) -> dict:
        messages = [
            m.get("content", "")
            for m in history
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        return {
            "message_history": messages,
            "attachment_count": len(attachments),
        }

    def _extract_field(
        self,
        message: str,
        fact: FactRequirement,
        history: list[dict],
    ) -> str | None:
        field = fact.field
        if field == "contract":
            return self._extract_contract(message)
        if field == "position_direction":
            return self._extract_direction(message)
        if field == "timeframe":
            return self._extract_timeframe(message)
        return None

    @staticmethod
    def _extract_contract(message: str) -> str | None:
        # Priority: alphabetic codes first (e.g. rb2610, RB2610)
        m = re.search(r"([A-Za-z]{1,3}\d{3,4})", message)
        if m:
            return m.group(1).lower()
        # Fallback: Chinese contract names
        m = re.search(
            r"(螺纹|热卷|铁矿石|焦煤|焦炭|原油|燃油|橡胶|豆粕|"
            r"豆油|棕榈油|玉米|鸡蛋|生猪|棉花|白糖|PTA|玻璃|"
            r"碳酸锂|黄金|白银|铜|铝|锌|镍|锡|股指|国债)",
            message,
        )
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _extract_direction(message: str) -> str | None:
        if re.search(r"多单|多仓|看多|做多|多头", message):
            return "LONG"
        if re.search(r"空单|空仓|空头|看空|做空", message):
            return "SHORT"
        if re.search(r"空仓|无持仓|观望", message) and not re.search(r"空单|空头", message):
            return "FLAT"
        return None

    @staticmethod
    def _extract_timeframe(message: str) -> str | None:
        if re.search(r"日线|日K|日k|每日", message):
            return "1d"
        if re.search(r"60.?分钟|小时|1h|1H", message):
            return "60m"
        if re.search(r"周线|周K|每周", message):
            return "1w"
        if re.search(r"30.?分钟", message):
            return "30m"
        if re.search(r"15.?分钟", message):
            return "15m"
        if re.search(r"5.?分钟", message):
            return "5m"
        return None
