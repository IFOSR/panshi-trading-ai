from trading_agent.clarification.questions import questions_for_analysis


def analysis_with_blockers(*blockers: str) -> dict:
    return {
        "analysis_id": "analysis-1",
        "milestones": [
            {
                "number": 1,
                "code": "DATA_VALIDITY",
                "blockers": list(blockers),
            },
            {
                "number": 5,
                "code": "POSITION_BEHAVIOR",
                "blockers": ["OPEN_INTEREST_MISSING"],
            },
            {
                "number": 7,
                "code": "PRICE_CONFIRMATION",
                "blockers": ["PRICE_NOT_CONFIRMED"],
            },
            {
                "number": 8,
                "code": "RISK_AND_ACTION",
                "blockers": [
                    "NO_ENABLED_STRATEGY",
                    "OPEN_INTEREST_MISSING",
                    "PRICE_NOT_CONFIRMED",
                ],
            },
        ],
    }


def test_current_case_blockers_become_specific_user_questions() -> None:
    questions = questions_for_analysis(
        analysis_with_blockers(
            "截图未明确标注最后一根日K线是否已经收盘，因此收盘状态无法确认。",
            "截图未明确标注最后一根60分钟K线是否已经收盘。",
            "CCYD末端柱体未显示可可靠读取的数值或明确分类标签，无法确认当前持仓行为。",
            "UNCLOSED_STATE_BAR",
        )
    )

    assert [question.field for question in questions] == [
        "state_bar_closed",
        "execution_bar_closed",
        "position_behavior_state",
        "open_interest_change",
        "price_confirmation",
    ]
    assert questions[0].milestone_number == 1
    assert "日线最后一根 K 线" in questions[0].question
    assert "60 分钟最后一根 K 线" in questions[1].question
    assert "CCYD" in questions[2].question
    assert questions[3].milestone_number == 5
    assert questions[4].milestone_number == 7


def test_duplicate_and_derived_blockers_do_not_create_duplicate_questions() -> None:
    questions = questions_for_analysis(
        analysis_with_blockers(
            "BAR_CLOSE_UNKNOWN",
            "UNCLOSED_STATE_BAR",
            "NO_ENABLED_STRATEGY",
            "MARKET_STATE_UNKNOWN",
        )
    )

    assert [question.field for question in questions].count("state_bar_closed") == 1
    assert all(question.field != "strategy" for question in questions)
    assert len([q for q in questions if q.field == "open_interest_change"]) == 1
    assert len([q for q in questions if q.field == "price_confirmation"]) == 1


def test_unknown_blocker_is_not_presented_as_user_resolvable() -> None:
    analysis = {
        "analysis_id": "analysis-1",
        "milestones": [
            {
                "number": 1,
                "code": "DATA_VALIDITY",
                "blockers": ["PRIVACY_REVIEW_REQUIRED"],
            }
        ],
    }

    assert questions_for_analysis(analysis) == []


def test_structured_negative_confirmation_does_not_ask_the_user() -> None:
    analysis = analysis_with_blockers()
    analysis["evidence_set"] = [
        {
            "image_role": "EXECUTION_60M",
            "allowed_usage": "EXACT",
            "last_bar_closed": True,
            "strategy_facts": {
                "price_confirmation": False,
                "price_confirmation_direction": "UNKNOWN",
                "price_confirmation_type": "UNKNOWN",
            },
            "field_provenance": {
                "strategy_facts.price_confirmation": "structured_market_data",
            },
        }
    ]

    questions = questions_for_analysis(analysis)

    assert all(question.field != "price_confirmation" for question in questions)


def test_known_direction_mismatch_does_not_ask_the_user() -> None:
    analysis = {
        "analysis_id": "analysis-1",
        "milestones": [
            {
                "number": 7,
                "code": "PRICE_CONFIRMATION",
                "blockers": ["CONFIRMATION_DIRECTION_MISMATCH"],
            }
        ],
        "evidence_set": [
            {
                "image_role": "EXECUTION_60M",
                "allowed_usage": "EXACT",
                "last_bar_closed": True,
                "strategy_facts": {
                    "price_confirmation": True,
                    "price_confirmation_direction": "BULLISH",
                    "price_confirmation_type": "PULLBACK",
                },
                "field_provenance": {
                    "strategy_facts.price_confirmation": "structured_market_data",
                    "strategy_facts.price_confirmation_direction": (
                        "structured_market_data"
                    ),
                    "strategy_facts.price_confirmation_type": (
                        "structured_market_data"
                    ),
                },
            }
        ],
    }

    assert questions_for_analysis(analysis) == []


def test_stale_or_unclosed_structured_confirmation_still_asks_the_user() -> None:
    for blocker, last_bar_closed in (
        ("EXECUTION_DATA_STALE", True),
        ("PRICE_NOT_CONFIRMED", False),
    ):
        analysis = analysis_with_blockers(blocker)
        analysis["evidence_set"] = [
            {
                "image_role": "EXECUTION_60M",
                "allowed_usage": "EXACT",
                "last_bar_closed": last_bar_closed,
                "strategy_facts": {
                    "price_confirmation": False,
                    "price_confirmation_direction": "UNKNOWN",
                    "price_confirmation_type": "UNKNOWN",
                },
                "field_provenance": {
                    "strategy_facts.price_confirmation": "structured_market_data",
                },
            }
        ]

        questions = questions_for_analysis(analysis)

        assert any(question.field == "price_confirmation" for question in questions)


def test_incomplete_or_dangling_model_confirmation_still_asks_the_user() -> None:
    for facts, observations in (
        (
            {
                "price_confirmation": True,
                "price_confirmation_direction": "UNKNOWN",
                "price_confirmation_type": "UNKNOWN",
            },
            [{"evidence_id": "confirmation"}],
        ),
        (
            {
                "price_confirmation": False,
                "price_confirmation_direction": "UNKNOWN",
                "price_confirmation_type": "UNKNOWN",
            },
            [],
        ),
    ):
        analysis = analysis_with_blockers()
        analysis["evidence_set"] = [
            {
                "image_role": "EXECUTION_60M",
                "allowed_usage": "EXACT",
                "last_bar_closed": True,
                "strategy_facts": facts,
                "observations": observations,
                "strategy_fact_support": {
                    "price_confirmation": {
                        "confidence": 0.95,
                        "evidence_refs": ["confirmation"],
                    },
                    "price_confirmation_direction": {
                        "confidence": 0.95,
                        "evidence_refs": ["confirmation"],
                    },
                    "price_confirmation_type": {
                        "confidence": 0.95,
                        "evidence_refs": ["confirmation"],
                    },
                },
            }
        ]

        questions = questions_for_analysis(analysis)

        assert any(question.field == "price_confirmation" for question in questions)
