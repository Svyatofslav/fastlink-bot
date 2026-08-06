import base64

import pytest

from utils.crypto import (
    CryptoError,
    decrypt_secret,
    derive_key_from_env,
    encrypt_secret,
)


def _make_key() -> bytes:
    raw_key = "a" * 64  # 32 bytes hex, только для теста
    return derive_key_from_env(raw_key)


def test_encrypt_decrypt_roundtrip() -> None:
    key = _make_key()

    plaintext = "test-secret-token-123"
    cipher = encrypt_secret(plaintext, key)

    assert cipher != plaintext
    assert isinstance(cipher, str)

    decrypted = decrypt_secret(cipher, key)
    assert decrypted == plaintext


def test_decrypt_secret_invalid_base64_raises_crypto_error() -> None:
    key = _make_key()

    with pytest.raises(CryptoError, match="Invalid base64 payload"):
        decrypt_secret("not-valid-base64!!!", key)


def test_decrypt_secret_payload_too_short_raises_crypto_error() -> None:
    key = _make_key()

    # Валидный base64, но короче NONCE_SIZE_BYTES (12 байт) -> должен упасть
    # на проверке длины payload, а не на AES-GCM.
    too_short_payload = base64.b64encode(b"short").decode("ascii")

    with pytest.raises(CryptoError, match="too short"):
        decrypt_secret(too_short_payload, key)


def test_decrypt_secret_truncated_ciphertext_raises_crypto_error() -> None:
    key = _make_key()

    plaintext = "test-secret-token-123"
    cipher = encrypt_secret(plaintext, key)

    payload = base64.b64decode(cipher)
    # Обрезаем последние 5 байт (часть tag/ciphertext), но оставляем
    # payload длиннее NONCE_SIZE_BYTES, чтобы дойти именно до AES-GCM.
    truncated_payload = payload[:-5]
    truncated_cipher = base64.b64encode(truncated_payload).decode("ascii")

    with pytest.raises(CryptoError, match="Failed to decrypt secret"):
        decrypt_secret(truncated_cipher, key)


def test_decrypt_secret_tampered_ciphertext_raises_crypto_error() -> None:
    key = _make_key()

    plaintext = "test-secret-token-123"
    cipher = encrypt_secret(plaintext, key)

    payload = bytearray(base64.b64decode(cipher))
    # Меняем один байт в зашифрованных данных (после nonce) -> AES-GCM tag
    # не совпадёт при проверке аутентичности.
    payload[-1] ^= 0xFF
    tampered_cipher = base64.b64encode(bytes(payload)).decode("ascii")

    with pytest.raises(CryptoError, match="Failed to decrypt secret"):
        decrypt_secret(tampered_cipher, key)


def test_decrypt_secret_wrong_key_raises_crypto_error() -> None:
    key = _make_key()
    wrong_key = derive_key_from_env("b" * 64)

    plaintext = "test-secret-token-123"
    cipher = encrypt_secret(plaintext, key)

    with pytest.raises(CryptoError, match="Failed to decrypt secret"):
        decrypt_secret(cipher, wrong_key)


def test_decrypt_secret_empty_string_returns_empty_string() -> None:
    key = _make_key()

    assert decrypt_secret("", key) == ""


def test_encrypt_secret_empty_string_returns_empty_string() -> None:
    key = _make_key()

    assert encrypt_secret("", key) == ""


def test_derive_key_from_env_invalid_hex_raises() -> None:
    from utils.crypto import InvalidKeyFormatError

    with pytest.raises(InvalidKeyFormatError, match="hex-encoded"):
        derive_key_from_env("not-hex-at-all!!")


def test_derive_key_from_env_wrong_length_raises() -> None:
    from utils.crypto import InvalidKeyFormatError

    with pytest.raises(InvalidKeyFormatError, match="32 bytes"):
        derive_key_from_env("aa" * 10)  # 10 bytes, not 32
