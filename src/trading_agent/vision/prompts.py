from hashlib import sha256


_CHART_EVIDENCE_V1 = """版本：chart-evidence-v1
你是中国期货交易截图证据抽取器。
直接分析附带的原始截图，不调用任何外部工具，不给交易建议。
只输出符合给定 JSON Schema 的对象。

规则：
1. 只报告截图中可见或可由可见数值直接验证的事实。
2. 无法确认的字段必须为 null，不得猜测合约、价格或日期。
3. 识别图片角色、周期、合约、数据截止时间、K线是否收盘、指标值和视觉关系。
4. 观察结果必须包含置信度、可见文本和证据描述。
5. 缺少合约、收盘状态、完整价格轴或关键数据时写入 blocking_issues。
6. 不输出买入、卖出、持有、加仓、减仓或退出建议。
7. 不展示隐藏思维过程。
8. strategy_facts 无法确认时使用 UNKNOWN 或 null。
9. strategy_fact_support 必须引用 observations 中存在的 evidence_id。
"""

_CHART_EVIDENCE_V2 = """版本：chart-evidence-v2
你是中国期货交易截图证据抽取器。
直接分析附带的原始截图，不调用任何外部工具，不给交易建议。
只输出符合给定 JSON Schema 的对象。

规则：
1. 只报告截图中可见或可由可见数值直接验证的事实。
2. 无法确认的字段必须为 null，不得猜测合约、价格或日期。
3. 识别图片角色、周期、合约、数据截止时间、K线是否收盘、指标值和视觉关系。
4. 观察结果必须包含置信度、可见文本和证据描述。
5. 缺少合约、收盘状态、完整价格轴或关键数据时写入 blocking_issues。
6. 不输出买入、卖出、持有、加仓、减仓或退出建议。
7. 不展示隐藏思维过程。
8. strategy_facts 只表达可见的结构关系，不表达交易动作；无法确认时使用 UNKNOWN 或 null。
9. price_confirmation 只有执行周期截图明确显示突破、守住或回踩确认时才可为 true，
   并必须同时输出 BULLISH/BEARISH 方向和 BREAKOUT/HOLD/PULLBACK 结构类型。
10. strategy_fact_support 必须为每个非 UNKNOWN 或非 null 事实提供置信度和
    observations 中存在的 evidence_id；价格确认、确认方向和确认结构类型必须分别提供支持。
11. 日线图不要求逐一显示每个交易日的日期刻度。若右端日期、合约和周期可识别，
    缺少逐日日期刻度本身不得写入 blocking_issues；结构化行情将校验精确截止时间和收盘状态。
"""

_PRIVACY_POLICY_V1 = """版本：privacy-policy-v1
未经可信隐私审查的原始截图不得发送给多模态模型。
阻断结果只记录隐私门禁状态、原图哈希和用户确认的图片角色。
"""

_MARKET_DATA_V1 = """版本：market-data-v1
该证据由结构化中国期货行情生成，不调用多模态模型。
只使用带来源、时间戳、收盘状态和质量标记的标准化行情字段。
指标、持仓量变化和价格确认均由版本化确定性公式计算。
"""

PROMPT_REGISTRY = {
    "chart-evidence-v1": _CHART_EVIDENCE_V1,
    "chart-evidence-v2": _CHART_EVIDENCE_V2,
    "privacy-policy-v1": _PRIVACY_POLICY_V1,
    "market-data-v1": _MARKET_DATA_V1,
}


def resolve_prompt(version: str) -> str:
    try:
        return PROMPT_REGISTRY[version]
    except KeyError as exc:
        raise ValueError(f"unknown prompt version: {version}") from exc


def prompt_sha256(version: str) -> str:
    return sha256(resolve_prompt(version).encode("utf-8")).hexdigest()


def render_provider_prompt(
    version: str,
    *,
    provider: str,
    image_suffixes: list[str] | None = None,
) -> str:
    template = resolve_prompt(version)
    if provider == "deepseek":
        return template
    if provider == "kimi":
        suffixes = image_suffixes or []
        image_names = "\n".join(
            f"image-{index}{suffix.lower()}"
            for index, suffix in enumerate(suffixes)
        )
        return (
            template.replace("不调用任何外部工具，", "")
            + "\n仅允许读取以下隔离目录中的原始图片文件：\n"
            + image_names
            + "\n只输出JSON。"
        )
    raise ValueError(f"unsupported prompt provider: {provider}")


def provider_prompt_sha256(
    version: str,
    *,
    provider: str,
    image_suffixes: list[str] | None = None,
) -> str:
    prompt = render_provider_prompt(
        version,
        provider=provider,
        image_suffixes=image_suffixes,
    )
    return sha256(prompt.encode("utf-8")).hexdigest()


CHART_EVIDENCE_PROMPT = _CHART_EVIDENCE_V2
