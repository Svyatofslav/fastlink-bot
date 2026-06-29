from utils.password import hash_password, verify_password, needs_rehash


def test_argon2_roundtrip() -> None:
    password = "super-secure-password-123"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)

    # Со свежими параметрами needs_rehash обычно False
    assert needs_rehash(hashed) is False
