from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from trading_agent.domain.contracts import contract_identity
from trading_agent.domain.enums import EvidenceUsage


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _structured_evidence_id(field: str) -> str:
    return "structured-" + field.replace(".", "-").replace("_", "-")


def _record_structured_evidence(
    merged: dict[str, Any],
    *,
    field: str,
    value: object,
) -> None:
    evidence_id = _structured_evidence_id(field)
    observation = {
        "evidence_id": evidence_id,
        "kind": field,
        "value": value,
        "confidence": 1.0,
        "provenance": "structured_market_data",
        "visible_text": None,
        "image_path": None,
        "evidence_description": f"结构化行情校验字段 {field}。",
    }
    observations = list(merged.get("observations", []))
    updated = False
    for index, item in enumerate(observations):
        if item.get("evidence_id") == evidence_id:
            observations[index] = observation
            updated = True
            break
    if not updated:
        observations.append(observation)
    merged["observations"] = observations
    refs = dict(merged.get("field_evidence_refs", {}))
    refs[field] = [evidence_id]
    merged["field_evidence_refs"] = refs


def _normalized_timeframe(value: object) -> str | None:
    aliases = {"D1": "1d", "1h": "60m", "H1": "60m"}
    return aliases.get(str(value), str(value)) if value else None


def _cutoff_identity(value: object) -> tuple[str, str] | None:
    if not value:
        return None
    normalized = str(value).replace("/", "-")
    try:
        parsed = datetime.fromisoformat(normalized)
        has_time = "T" in normalized or " " in normalized
        return (
            "datetime" if has_time else "date",
            parsed.isoformat() if has_time else parsed.date().isoformat(),
        )
    except ValueError:
        return ("date", normalized[:10])


def _cutoff_conflicts(
    model_cutoff: tuple[str, str] | None,
    market_cutoff: tuple[str, str] | None,
) -> bool:
    if not model_cutoff or not market_cutoff:
        return False
    if model_cutoff[0] == "datetime" and market_cutoff[0] == "datetime":
        try:
            model_time = datetime.fromisoformat(model_cutoff[1])
            market_time = datetime.fromisoformat(market_cutoff[1])
        except ValueError:
            return model_cutoff[1] != market_cutoff[1]
        if model_time.tzinfo is None:
            model_time = model_time.replace(tzinfo=SHANGHAI)
        if market_time.tzinfo is None:
            market_time = market_time.replace(tzinfo=SHANGHAI)
        return market_time < model_time
    if model_cutoff[1][:10] != market_cutoff[1][:10]:
        try:
            model_date = date.fromisoformat(model_cutoff[1][:10])
            market_date = date.fromisoformat(market_cutoff[1][:10])
        except ValueError:
            return True
        return market_date < model_date
    if model_cutoff[0] == "date":
        return False
    if market_cutoff[0] != "datetime":
        return True
    return False


def _bar_close_blocker(issue: str) -> bool:
    normalized = issue.upper()
    return (
        normalized
        in {
            "BAR_CLOSE_UNKNOWN",
            "UNCLOSED_STATE_BAR",
            "EXECUTION_BAR_CLOSE_UNKNOWN",
            "EXECUTION_CUTOFF_MISSING",
            "EXECUTION_CUTOFF_TIME_MISSING",
        }
        or (
            "收盘" in issue
            and ("K线" in issue or "K 线" in issue or "执行周期" in issue)
        )
    )


def _price_axis_blocker(issue: str) -> bool:
    normalized = issue.upper()
    return (
        normalized == "PRICE_AXIS_UNVERIFIED"
        or "价格轴" in issue
        or ("刻度" in issue and ("价格" in issue or "报价" in issue))
    )


def _position_behavior_blocker(issue: str) -> bool:
    normalized = issue.upper()
    return (
        normalized == "OPEN_INTEREST_MISSING"
        or "CCYD" in normalized
        or "持仓行为" in issue
    )


def _date_axis_blocker(issue: str) -> bool:
    normalized = issue.upper()
    return (
        normalized
        in {
            "DATE_AXIS_UNVERIFIED",
            "DAILY_DATE_TICKS_INCOMPLETE",
            "TIME_AXIS_INCOMPLETE",
            "CUTOFF_MISSING",
            "CUTOFF_TIME_MISSING",
        }
        or (
            "截止" in issue
            and ("时间" in issue or "时刻" in issue)
            and (
                "未显示" in issue
                or "缺少" in issue
                or "无法" in issue
            )
        )
        or (
            ("日期" in issue or "时间轴" in issue or "横轴" in issue)
            and ("刻度" in issue or "标签" in issue)
            and ("逐日" in issue or "完整" in issue or "每个交易日" in issue)
        )
    )


def _valid_cutoff(value: object) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(str(value).replace("/", "-"))
    except ValueError:
        return False
    return True


def merge_evidence(
    model: dict[str, Any],
    market_data: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(model)
    blockers = list(model.get("blocking_issues", []))
    market_contract = market_data.get("contract") if market_data else None
    model_contract = model.get("contract")
    provenance = dict(model.get("field_provenance", {}))
    identity_conflict = False

    if (
        market_contract
        and model_contract
        and contract_identity(market_contract) != contract_identity(model_contract)
    ):
        blockers.append("CONTRACT_CONFLICT")
        identity_conflict = True
    elif market_contract and not model_contract:
        merged["contract"] = market_contract
        provenance["contract"] = "structured_market_data"
        _record_structured_evidence(
            merged,
            field="contract",
            value=market_contract,
        )
        blockers = [issue for issue in blockers if issue != "CONTRACT_MISSING"]

    if market_data:
        blockers.extend(
            str(issue) for issue in market_data.get("blocking_issues", [])
        )
        if market_data.get("market_data_sources"):
            blockers = [
                issue for issue in blockers if issue != "MARKET_DATA_UNAVAILABLE"
            ]
        if market_data.get("indicators"):
            blockers = [
                issue
                for issue in blockers
                if issue != "MARKET_HISTORY_INSUFFICIENT"
            ]
        model_timeframe = _normalized_timeframe(model.get("timeframe"))
        market_timeframe = _normalized_timeframe(market_data.get("timeframe"))
        if model_timeframe and market_timeframe and model_timeframe != market_timeframe:
            blockers.append("TIMEFRAME_CONFLICT")
            identity_conflict = True
        model_cutoff = _cutoff_identity(model.get("cutoff_time"))
        market_cutoff = _cutoff_identity(market_data.get("cutoff_time"))
        cutoff_conflict = _cutoff_conflicts(model_cutoff, market_cutoff)
        if cutoff_conflict:
            blockers.append("CUTOFF_CONFLICT")
            identity_conflict = True
        elif market_cutoff is not None:
            blockers = [issue for issue in blockers if issue != "CUTOFF_CONFLICT"]
        if identity_conflict:
            merged["blocking_issues"] = list(dict.fromkeys(blockers))
            merged["field_provenance"] = provenance
            merged["allowed_usage"] = EvidenceUsage.BLOCKED
            return merged
        for field in ("timeframe", "cutoff_time", "last_bar_closed"):
            market_value = market_data.get(field)
            if market_value is not None:
                merged[field] = market_value
                provenance[field] = "structured_market_data"
                _record_structured_evidence(
                    merged,
                    field=field,
                    value=market_value,
                )
        if market_data.get("cutoff_time") is not None:
            blockers = [
                issue
                for issue in blockers
                if issue
                not in {
                    "CUTOFF_MISSING",
                    "EXECUTION_CUTOFF_MISSING",
                    "EXECUTION_CUTOFF_TIME_MISSING",
                    "INTRADAY_CUTOFF_TIME_MISSING",
                }
            ]
        if _valid_cutoff(market_data.get("cutoff_time")):
            blockers = [
                issue for issue in blockers if not _date_axis_blocker(issue)
            ]
        market_indicators = market_data.get("indicators", {})
        if market_indicators:
            merged_indicators = dict(merged.get("indicators", {}))
            for group, values in market_indicators.items():
                merged_group = dict(merged_indicators.get(group) or {})
                for name, value in values.items():
                    merged_group[name] = value
                    field = f"indicators.{group}.{name}"
                    provenance[field] = "structured_market_data"
                    _record_structured_evidence(
                        merged,
                        field=field,
                        value=value,
                    )
                merged_indicators[group] = merged_group
            merged["indicators"] = merged_indicators
        market_facts = market_data.get("strategy_facts", {})
        if market_facts:
            merged_facts = dict(merged.get("strategy_facts", {}))
            for name, value in market_facts.items():
                merged_facts[name] = value
                field = f"strategy_facts.{name}"
                provenance[field] = "structured_market_data"
                _record_structured_evidence(
                    merged,
                    field=field,
                    value=value,
                )
            merged["strategy_facts"] = merged_facts
        for field in (
            "open_interest_change",
            "trend_score",
            "latest_close",
            "rollover_active",
            "near_price_limit",
            "market_data_sources",
            "market_data_validation_sources",
            "market_data_quality_issues",
            "market_contract_metadata",
        ):
            if market_data.get(field) is not None:
                merged[field] = market_data[field]
                provenance[field] = "structured_market_data"
                _record_structured_evidence(
                    merged,
                    field=field,
                    value=market_data[field],
                )
        if market_data.get("last_bar_closed") is True:
            blockers = [
                issue for issue in blockers if not _bar_close_blocker(issue)
            ]
        if market_data.get("open_interest_change") is not None:
            blockers = [
                issue
                for issue in blockers
                if not _position_behavior_blocker(issue)
            ]
        if market_data.get("price_axis_verified") is True:
            blockers = [
                issue for issue in blockers if not _price_axis_blocker(issue)
            ]
        elif market_data.get("price_axis_verified") is False:
            blockers.append("PRICE_AXIS_UNVERIFIED")

    merged["blocking_issues"] = list(dict.fromkeys(blockers))
    merged["field_provenance"] = provenance
    if (
        merged.get("allowed_usage") == EvidenceUsage.BLOCKED
        and merged["blocking_issues"]
    ):
        return merged
    exact_ready = bool(
        market_data
        and market_data.get("price_axis_verified") is True
        and not merged["blocking_issues"]
    )
    merged["allowed_usage"] = (
        EvidenceUsage.EXACT if exact_ready else EvidenceUsage.QUALITATIVE_ONLY
    )
    return merged
