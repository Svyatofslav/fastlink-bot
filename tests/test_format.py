from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.format import (
    format_date,
    format_duration_days,
    format_price,
    format_traffic,
    parse_price,
)


@pytest.mark.parametrize(
    "amount_minor,currency,expected",
    [
        (19900, "RUB", "199 ₽"),
        (19950, "RUB", "199.50 ₽"),
        (100, "RUB", "1 ₽"),
        (1, "RUB", "0.01 ₽"),
        (0, "RUB", "0 ₽"),
        (5000, "USD", "50 $" if False else "50 USD"),
        (None, "RUB", "—"),
    ],
)
def test_format_price(amount_minor: int | None, currency: str, expected: str) -> None:
    assert format_price(amount_minor, currency) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("50", 5000),
        ("49.99", 4999),
        ("49,99", 4999),
        (" 50 ", 5000),
        ("50.005", 5001),
        ("50.004", 5000),
        ("0.01", 1),
    ],
)
def test_parse_price_valid(raw: str, expected: int) -> None:
    assert parse_price(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["не число", "abc", "-10", "-50.00", "0", "0.00", "", "   ", "50.00.00", "5,0,0"],
)
def test_parse_price_invalid_or_non_positive(raw: str) -> None:
    assert parse_price(raw) is None


def test_parse_price_scientific_notation_is_accepted_as_valid_decimal() -> None:
    """
    Decimal("1e10") валиден для decimal.Decimal и не бросает InvalidOperation,
    поэтому parse_price не отбрасывает научную нотацию как невалидный ввод.
    Если это нежелательно на уровне UX (обход donation_max_amount через
    непривычный формат), ограничение должно быть на уровне вызывающего
    хендлера, а не внутри parse_price.
    """
    assert parse_price("1e10") == 1_000_000_000_000


def test_parse_price_very_large_number() -> None:
    assert parse_price("999999999999") == 99999999999900


def test_parse_price_leading_trailing_whitespace() -> None:
    assert parse_price("  100  ") == 10000


@pytest.mark.parametrize(
    "used_bytes,limit_bytes,expected",
    [
        (1_500_000_000, 50_000_000_000, "1.4 GB из 46.6 GB"),
        (0, 50_000_000_000, "0.0 GB из 46.6 GB"),
        (50_000_000_000, 50_000_000_000, "46.6 GB из 46.6 GB"),
        (1_500_000_000, None, "1.4 GB (безлимит)"),
        (1_500_000_000, 0, "1.4 GB (безлимит)"),
        (0, None, "0.0 GB (безлимит)"),
    ],
)
def test_format_traffic(
    used_bytes: int, limit_bytes: int | None, expected: str
) -> None:
    assert format_traffic(used_bytes, limit_bytes) == expected


def test_format_date_with_value() -> None:
    dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert format_date(dt) == "25.07.2026"


def test_format_date_none() -> None:
    assert format_date(None) == "—"


@pytest.mark.parametrize(
    "days,expected",
    [
        (30, "1 месяц"),
        (60, "2 месяца"),
        (90, "3 месяца"),
        (120, "4 месяца"),
        (150, "5 месяцев"),
        (360, "12 месяцев"),
        (365, "365 дней"),
        (7, "7 дней"),
        (1, "1 день"),
        (14, "14 дней"),
        (21, "21 день"),
        (22, "22 дня"),
        (25, "25 дней"),
        (11, "11 дней"),
    ],
)
def test_format_duration_days(days: int, expected: str) -> None:
    assert format_duration_days(days) == expected
