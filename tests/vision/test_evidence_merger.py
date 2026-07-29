from trading_agent.domain.enums import EvidenceUsage
from trading_agent.vision.evidence_merger import merge_evidence


def test_conflicting_model_and_market_contract_values_create_a_blocker() -> None:
    merged = merge_evidence(
        model={"contract": "rb2605", "blocking_issues": []},
        market_data={"contract": "rb2610"},
    )

    assert "CONTRACT_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_contract_identity_comparison_ignores_case_and_whitespace() -> None:
    merged = merge_evidence(
        model={"contract": " CF2609 ", "blocking_issues": []},
        market_data={"contract": "cf2609", "price_axis_verified": True},
    )

    assert "CONTRACT_CONFLICT" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT
    assert merged["contract"] == " CF2609 "


def test_verified_market_contract_fills_missing_model_contract() -> None:
    merged = merge_evidence(
        model={"contract": None, "blocking_issues": ["CONTRACT_MISSING"]},
        market_data={"contract": "rb2610"},
    )

    assert merged["contract"] == "rb2610"
    assert "CONTRACT_MISSING" not in merged["blocking_issues"]


def test_structured_market_fields_override_model_with_provenance() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T15:00:00+08:00",
            "last_bar_closed": None,
            "indicators": {"boll": {"mid": 3500.0}},
            "blocking_issues": ["BAR_CLOSE_UNKNOWN"],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T15:00:00+08:00",
            "last_bar_closed": True,
            "indicators": {"boll": {"mid": 3512.0}},
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T15:00:00+08:00"
    assert merged["indicators"]["boll"]["mid"] == 3512.0
    assert merged["field_provenance"]["indicators.boll.mid"] == "structured_market_data"
    assert "BAR_CLOSE_UNKNOWN" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT
    structured_ref = merged["field_evidence_refs"]["indicators.boll.mid"][0]
    assert any(
        item["evidence_id"] == structured_ref
        and item["provenance"] == "structured_market_data"
        for item in merged["observations"]
    )


def test_structured_merge_preserves_unmodified_model_provenance() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "strategy_facts": {"position_behavior": "SHORT_BUILD_LONG_EXIT"},
            "field_provenance": {
                "image_role": "user_confirmed",
                "strategy_facts.position_behavior": "codex_multimodal",
            },
            "blocking_issues": [],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "last_bar_closed": True,
            "price_axis_verified": True,
        },
    )

    assert merged["field_provenance"]["image_role"] == "user_confirmed"
    assert (
        merged["field_provenance"]["strategy_facts.position_behavior"]
        == "codex_multimodal"
    )
    assert merged["field_provenance"]["last_bar_closed"] == "structured_market_data"


def test_missing_verified_price_axis_blocks_exact_trade_levels() -> None:
    merged = merge_evidence(
        model={"contract": "rb2610", "blocking_issues": []},
        market_data={"contract": "rb2610", "price_axis_verified": False},
    )

    assert "PRICE_AXIS_UNVERIFIED" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.QUALITATIVE_ONLY


def test_verified_market_prices_clear_visual_price_axis_uncertainty() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "blocking_issues": [
                "右侧最新价格轴仅显示部分刻度，但布林带及最新报价的可见数值完整。"
            ],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "price_axis_verified": True,
            "latest_close": 16005,
        },
    )

    assert merged["blocking_issues"] == []
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_structured_cutoff_clears_missing_daily_tick_labels() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23",
            "blocking_issues": [
                "截图未显示完整逐日日期刻度，仅明确显示区间端点及右端日期。"
            ],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
        },
    )

    assert merged["blocking_issues"] == []
    assert merged["cutoff_time"] == "2026-07-24T15:00:00+08:00"
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_conflicting_timeframes_block_structured_merge() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "1d",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "60m",
            "price_axis_verified": True,
        },
    )

    assert "TIMEFRAME_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_newer_structured_trading_date_supersedes_visual_cutoff() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-19T15:00:00+08:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T15:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T15:00:00+08:00"
    assert "CUTOFF_CONFLICT" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_structured_cutoff_clears_visual_exact_time_blocker() -> None:
    blocker = "截图仅显示右端日期 2026/07/27，未显示日线数据的精确截止时刻。"
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-27",
            "blocking_issues": [blocker],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-28T15:00:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-28T15:00:00+08:00"
    assert blocker not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_older_structured_trading_date_blocks_merge() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-20T15:00:00+08:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "1d",
            "cutoff_time": "2026-07-19T15:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert "CUTOFF_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_successful_reverification_clears_stale_cutoff_block() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "last_bar_closed": True,
            "blocking_issues": ["CUTOFF_CONFLICT"],
            "allowed_usage": EvidenceUsage.BLOCKED,
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
        },
    )

    assert merged["blocking_issues"] == []
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_newer_intraday_structured_cutoff_supersedes_visual_cutoff() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T10:00:00+08:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T11:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T11:00:00+08:00"
    assert "CUTOFF_CONFLICT" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_older_intraday_structured_cutoff_still_blocks_merge() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T11:00:00+08:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T10:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert "CUTOFF_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_newer_daily_structured_cutoff_supersedes_same_day_visual_cutoff() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23T11:29:00+08:00",
            "last_bar_closed": False,
            "blocking_issues": [
                "日线最后一根K线对应2026/07/23，截图未明确标示该日K线已经收盘。",
                "UNCLOSED_STATE_BAR",
            ],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23T15:00:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
            "market_data_sources": ["akshare"],
            "market_data_validation_sources": ["SHFE_OFFICIAL_DAILY"],
        },
    )

    assert merged["cutoff_time"] == "2026-07-23T15:00:00+08:00"
    assert merged["last_bar_closed"] is True
    assert "CUTOFF_CONFLICT" not in merged["blocking_issues"]
    assert "UNCLOSED_STATE_BAR" not in merged["blocking_issues"]
    assert "日线最后一根K线" not in "；".join(merged["blocking_issues"])
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_timezone_less_visual_cutoff_uses_china_market_timezone() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23T11:29:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23T15:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-23T15:00:00+08:00"
    assert "CUTOFF_CONFLICT" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_aware_cutoffs_are_compared_as_instants_before_calendar_dates() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "60m",
            "cutoff_time": "2026-07-23T23:30:00+00:00",
            "blocking_issues": [],
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "60m",
            "cutoff_time": "2026-07-24T06:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert "CUTOFF_CONFLICT" in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.BLOCKED


def test_reverification_updates_cached_structured_observation_values() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-23T15:00:00+08:00",
            "blocking_issues": [],
            "observations": [
                {
                    "evidence_id": "structured-cutoff-time",
                    "kind": "cutoff_time",
                    "value": "2026-07-23T15:00:00+08:00",
                    "confidence": 1.0,
                    "provenance": "structured_market_data",
                }
            ],
            "field_evidence_refs": {
                "cutoff_time": ["structured-cutoff-time"],
            },
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    cutoff_observation = next(
        item
        for item in merged["observations"]
        if item["evidence_id"] == "structured-cutoff-time"
    )
    assert cutoff_observation["value"] == "2026-07-24T15:00:00+08:00"


def test_reverification_clears_cached_market_data_failure() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "blocking_issues": ["MARKET_DATA_UNAVAILABLE"],
            "market_data_sources": [],
            "market_data_quality_issues": ["AKSHARE_UNAVAILABLE"],
            "allowed_usage": EvidenceUsage.QUALITATIVE_ONLY,
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "1d",
            "cutoff_time": "2026-07-24T15:00:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
            "market_data_sources": ["akshare"],
            "market_data_quality_issues": ["CZCE_OFFICIAL_DAILY_UNAVAILABLE"],
        },
    )

    assert merged["blocking_issues"] == []
    assert merged["allowed_usage"] == EvidenceUsage.EXACT
    assert merged["market_data_sources"] == ["akshare"]
    assert merged["market_data_quality_issues"] == [
        "CZCE_OFFICIAL_DAILY_UNAVAILABLE"
    ]


def test_reverification_clears_cached_insufficient_history() -> None:
    merged = merge_evidence(
        model={
            "contract": "cf2609",
            "timeframe": "60m",
            "blocking_issues": ["MARKET_HISTORY_INSUFFICIENT"],
            "allowed_usage": EvidenceUsage.QUALITATIVE_ONLY,
        },
        market_data={
            "contract": "cf2609",
            "timeframe": "60m",
            "cutoff_time": "2026-07-27T14:15:00+08:00",
            "last_bar_closed": True,
            "price_axis_verified": True,
            "market_data_sources": ["akshare"],
            "indicators": {
                "price_confirmation": {
                    "confirmed": False,
                    "direction": "UNKNOWN",
                    "kind": "UNKNOWN",
                }
            },
        },
    )

    assert merged["blocking_issues"] == []
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_structured_intraday_cutoff_replaces_date_only_visual_value() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20",
            "blocking_issues": [],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T11:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T11:00:00+08:00"
    assert "INTRADAY_CUTOFF_TIME_MISSING" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT


def test_structured_intraday_cutoff_fills_missing_visual_value() -> None:
    merged = merge_evidence(
        model={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": None,
            "blocking_issues": ["CUTOFF_MISSING"],
        },
        market_data={
            "contract": "rb2610",
            "timeframe": "60m",
            "cutoff_time": "2026-07-20T11:00:00+08:00",
            "price_axis_verified": True,
        },
    )

    assert merged["cutoff_time"] == "2026-07-20T11:00:00+08:00"
    assert "CUTOFF_MISSING" not in merged["blocking_issues"]
    assert merged["allowed_usage"] == EvidenceUsage.EXACT
