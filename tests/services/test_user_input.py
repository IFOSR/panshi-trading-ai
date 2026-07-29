from trading_agent.services.user_input import parse_user_message


def test_position_direction_without_quantity_remains_unknown_sized() -> None:
    parsed = parse_user_message("我有多单，接下来该如何操作")

    assert parsed["position"]["direction"] == "LONG"
    assert parsed["position"]["quantity"] is None
