from utils.crypto import derive_key_from_env, encrypt_secret, decrypt_secret


def test_encrypt_decrypt_roundtrip() -> None:
    raw_key = "a" * 64  # 32 bytes hex, только для теста
    key = derive_key_from_env(raw_key)

    plaintext = "test-secret-token-123"
    cipher = encrypt_secret(plaintext, key)

    assert cipher != plaintext
    assert isinstance(cipher, str)

    decrypted = decrypt_secret(cipher, key)
    assert decrypted == plaintext
