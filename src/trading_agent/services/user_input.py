import re
from typing import Any


def parse_user_message(message: str) -> dict[str, Any]:
    contract_match = re.search(r"\b([A-Za-z]{1,2}\d{3,4})\b", message)
    quantity_match = re.search(r"(\d+)\s*手", message)
    cost_match = re.search(r"成本\s*([0-9]+(?:\.[0-9]+)?)", message)
    stop_match = re.search(r"止损\s*([0-9]+(?:\.[0-9]+)?)", message)
    holding_match = re.search(r"持有\s*(\d+\s*(?:天|日|小时|周))", message)
    risk_match = re.search(r"(?:单笔)?风险\s*([0-9]+(?:\.[0-9]+)?)\s*%", message)
    direction = (
        "LONG" if re.search(r"多单|多仓", message)
        else "SHORT" if re.search(r"空单|空头持仓", message)
        else "FLAT" if "空仓" in message
        else "UNKNOWN"
    )
    intent = (
        "POSITION_MANAGEMENT"
        if re.search(r"持仓管理|止损|加仓|减仓|退出", message)
        else "ENTRY"
        if re.search(r"入场|开仓|买入|卖出", message)
        else "MARKET_ANALYSIS"
    )
    quantity = (
        int(quantity_match.group(1))
        if quantity_match
        else 0
        if direction == "FLAT"
        else None
    )
    return {
        "raw_message": message,
        "decision_intent": intent,
        "contract": contract_match.group(1).lower() if contract_match else None,
        "holding_period": holding_match.group(1).replace(" ", "") if holding_match else None,
        "position": {
            "direction": direction,
            "quantity": quantity,
            "average_cost": float(cost_match.group(1)) if cost_match else None,
            "stop_price": float(stop_match.group(1)) if stop_match else None,
        },
        "risk": {
            "account_risk_limit": float(risk_match.group(1)) / 100
            if risk_match
            else None,
        },
    }
