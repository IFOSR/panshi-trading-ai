from trading_agent.auth.passwords import hash_password, verify_password


def test_password_hash_round_trip_uses_random_salt() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first.startswith("scrypt$")
    assert second.startswith("scrypt$")
    assert first != second
    assert verify_password("correct horse battery staple", first) is True
    assert verify_password("wrong password", first) is False


def test_password_verification_rejects_malformed_or_unsupported_hashes() -> None:
    assert verify_password("password", "") is False
    assert verify_password("password", "pbkdf2$1$salt$digest") is False
    assert verify_password("password", "scrypt$bad$8$1$salt$digest") is False
    assert verify_password("password", "scrypt$16384$8$1$%%%$%%%") is False

