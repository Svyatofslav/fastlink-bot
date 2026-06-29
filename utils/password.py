from __future__ import annotations

from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError


# Параметры Argon2id можно позже усилить, если нужно.
# Сейчас они подобраны как разумный баланс для админских паролей.
_ARGON2_TIME_COST: Final[int] = 3
_ARGON2_MEMORY_COST: Final[int] = 64 * 1024  # 64 MB
_ARGON2_PARALLELISM: Final[int] = 2
_ARGON2_HASH_LENGTH: Final[int] = 32


_password_hasher = PasswordHasher(
    time_cost=_ARGON2_TIME_COST,
    memory_cost=_ARGON2_MEMORY_COST,
    parallelism=_ARGON2_PARALLELISM,
    hash_len=_ARGON2_HASH_LENGTH,
)


def hash_password(plaintext: str) -> str:
    """
    Хешировать пароль/секретное слово с помощью Argon2id.

    Возвращает строку формата `$argon2id$v=19$m=...$...`, которую можно хранить в БД.
    """
    if not plaintext:
        raise ValueError("Password/secret word must not be empty")

    return _password_hasher.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Проверить пароль/секретное слово против хеша.

    Возвращает True/False, не выбрасывая исключения при несоответствии.
    """
    if not hashed:
        return False

    try:
        _password_hasher.verify(hashed, plaintext)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHash:
        # Старые или повреждённые хеши.
        return False


def needs_rehash(hashed: str) -> bool:
    """
    Проверить, нужно ли пересчитать хеш по текущим параметрам Argon2id.

    Если True, при успешном логине стоит пересчитать хеш и обновить его в БД.
    """
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except InvalidHash:
        # Если формат хеша неизвестен, лучше пересчитать при возможности.
        return True
