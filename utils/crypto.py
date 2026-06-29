import base64
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# AES-GCM стандартно использует 96-битный (12 байт) nonce.
NONCE_SIZE_BYTES: Final[int] = 12
KEY_SIZE_BYTES: Final[int] = 32  # AES-256


class CryptoError(Exception):
    """Base exception for crypto-related errors."""


class InvalidKeyFormatError(CryptoError):
    """Raised when the master key from env has invalid format or length."""


def derive_key_from_env(raw: str) -> bytes:
    """
    Parse hex-encoded master key from env and validate its length.

    Expected format: 64 hex characters (32 bytes).
    """
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise InvalidKeyFormatError(
            "FASTLINK_CRYPTO_MASTER_KEY must be hex-encoded"
        ) from exc

    if len(key) != KEY_SIZE_BYTES:
        raise InvalidKeyFormatError(
            f"FASTLINK_CRYPTO_MASTER_KEY must be {KEY_SIZE_BYTES} bytes, got {len(key)} bytes",
        )
    return key


def encrypt_secret(plaintext: str, master_key: bytes) -> str:
    """
    Encrypt a plaintext string with AES-256-GCM using the given master key.

    Returns: base64-encoded string containing nonce + ciphertext + tag.
    """
    if not plaintext:
        # Для пустых значений можно договориться: возвращаем пустую строку,
        # а на уровне repo трактуем это как "нет секрета".
        return ""

    nonce = os.urandom(NONCE_SIZE_BYTES)
    aesgcm = AESGCM(master_key)

    # associated_data=None — нам достаточно аутентификации самого ciphertext
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    payload = nonce + ciphertext_with_tag
    return base64.b64encode(payload).decode("ascii")


def decrypt_secret(cipher: str, master_key: bytes) -> str:
    """
    Decrypt a base64-encoded (nonce + ciphertext + tag) payload.

    Returns: plaintext string.

    Raises CryptoError on any failure (invalid format, auth error, etc.).
    """
    if not cipher:
        # Трактуем пустую строку как "секрета нет".
        return ""

    try:
        payload = base64.b64decode(cipher)
    except (ValueError, TypeError) as exc:
        raise CryptoError("Invalid base64 payload for encrypted secret") from exc

    if len(payload) <= NONCE_SIZE_BYTES:
        raise CryptoError(
            "Encrypted payload is too short to contain nonce and ciphertext"
        )

    nonce = payload[:NONCE_SIZE_BYTES]
    ciphertext_with_tag = payload[NONCE_SIZE_BYTES:]

    try:
        aesgcm = AESGCM(master_key)
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except Exception as exc:
        # cryptography выбрасывает разные исключения (InvalidTag и др.)
        raise CryptoError("Failed to decrypt secret") from exc

    return plaintext_bytes.decode("utf-8")
