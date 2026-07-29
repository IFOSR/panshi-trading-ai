from trading_agent.auth.tokens import digest_session_token, generate_session_token


def test_session_tokens_are_random_and_digest_to_fixed_length_hex() -> None:
    first = generate_session_token()
    second = generate_session_token()

    assert first != second
    assert len(first) >= 40
    assert len(digest_session_token(first)) == 64
    assert digest_session_token(first) == digest_session_token(first)
    assert digest_session_token(first) != digest_session_token(second)

