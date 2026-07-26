from argon2 import PasswordHasher

from utils.password import hash_password, verify_password, needs_rehash


def test_argon2_roundtrip() -> None:
    password = "super-secure-password-123"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)

    # Со свежими параметрами needs_rehash обычно False
    assert needs_rehash(hashed) is False


def test_needs_rehash_true_for_outdated_time_cost() -> None:
    """
    Хеш, сгенерированный со старым (более слабым) time_cost, должен
    считаться устаревшим относительно текущих параметров хэшера.
    """
    outdated_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=64 * 1024,
        parallelism=2,
        hash_len=32,
    )
    outdated_hash = outdated_hasher.hash("super-secure-password-123")

    assert needs_rehash(outdated_hash) is True


def test_needs_rehash_true_for_outdated_memory_cost() -> None:
    """
    Хеш со старым (более слабым) memory_cost также должен требовать rehash.
    """
    outdated_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=8 * 1024,
        parallelism=2,
        hash_len=32,
    )
    outdated_hash = outdated_hasher.hash("super-secure-password-123")

    assert needs_rehash(outdated_hash) is True


def test_needs_rehash_true_for_outdated_parallelism() -> None:
    """
    Изменение parallelism тоже должно приводить к необходимости rehash,
    так как это часть параметров, зашитых в сам хеш.
    """
    outdated_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=64 * 1024,
        parallelism=1,
        hash_len=32,
    )
    outdated_hash = outdated_hasher.hash("super-secure-password-123")

    assert needs_rehash(outdated_hash) is True


def test_needs_rehash_true_for_stronger_params_too() -> None:
    """
    needs_rehash реагирует на любое отличие параметров от текущих —
    не только на "более слабые", но и на "более сильные" хеши, потому что
    check_needs_rehash сравнивает точное совпадение параметров, а не
    "хеш слабее текущего".
    """
    stronger_hasher = PasswordHasher(
        time_cost=10,
        memory_cost=128 * 1024,
        parallelism=2,
        hash_len=32,
    )
    stronger_hash = stronger_hasher.hash("super-secure-password-123")

    assert needs_rehash(stronger_hash) is True


def test_needs_rehash_invalid_hash_returns_true() -> None:
    """
    Невалидный/повреждённый формат хеша не должен приводить к падению —
    needs_rehash трактует это как "нужен пересчёт при первой возможности".
    """
    assert needs_rehash("not-a-valid-argon2-hash") is True
    assert needs_rehash("") is True


def test_verify_password_with_outdated_hash_still_works() -> None:
    """
    Верификация пароля должна работать независимо от того, устарели ли
    параметры хеша — needs_rehash это отдельная, не блокирующая проверка.
    """
    outdated_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=8 * 1024,
        parallelism=1,
        hash_len=32,
    )
    password = "super-secure-password-123"
    outdated_hash = outdated_hasher.hash(password)

    assert verify_password(password, outdated_hash)
    assert needs_rehash(outdated_hash) is True


def test_hash_password_empty_raises_value_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        hash_password("")


def test_verify_password_empty_hash_returns_false() -> None:
    assert verify_password("any-password", "") is False


def test_verify_password_malformed_hash_returns_false() -> None:
    assert verify_password("any-password", "not-a-valid-hash") is False
