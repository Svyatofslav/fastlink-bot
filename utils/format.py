from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


def format_price(amount_minor: int | None, currency: str = "RUB") -> str:
    """Конвертирует сумму в минорных единицах (копейках) в читаемый вид.

    format_price(19900) -> "199 ₽"
    format_price(19950) -> "199.50 ₽"
    """
    if amount_minor is None:
        return "—"

    symbol = {"RUB": "₽"}.get(currency, currency)
    major, minor = divmod(amount_minor, 100)

    if minor == 0:
        return f"{major} {symbol}"
    return f"{major}.{minor:02d} {symbol}"


def parse_price(raw: str) -> int | None:
    """Парсит сумму в рублях, введённую пользователем, в минорные единицы (копейки).

    parse_price("50") -> 5000
    parse_price("49.99") -> 4999
    parse_price("не число") -> None
    """
    normalized = raw.strip().replace(",", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    minor = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def format_traffic(used_bytes: int, limit_bytes: int | None) -> str:
    """Форматирует расход трафика в читаемый вид.

    format_traffic(1_500_000_000, 50_000_000_000) -> "1.4 GB из 46.6 GB"
    Если limit_bytes is None или 0 -> считается безлимитным.
    """
    used_gb = used_bytes / (1024**3)

    if not limit_bytes:
        return f"{used_gb:.1f} GB (безлимит)"

    limit_gb = limit_bytes / (1024**3)
    return f"{used_gb:.1f} GB из {limit_gb:.1f} GB"


def format_date(dt: datetime | None) -> str:
    """Форматирует дату в формате ДД.ММ.ГГГГ.

    Если dt is None -> "—".
    """
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y")


def _pluralize_ru(n: int, one: str, few: str, many: str) -> str:
    """
    Склонение существительного после числительного в русском языке.

    one  — форма для 1, 21, 31, ... (кроме 11)
    few  — форма для 2-4, 22-24, ... (кроме 12-14)
    many — форма для 5-20, 25-30, 0, ...
    """
    n_abs = abs(n)
    if n_abs % 100 in (11, 12, 13, 14):
        return many
    last_digit = n_abs % 10
    if last_digit == 1:
        return one
    if 2 <= last_digit <= 4:
        return few
    return many


def format_duration_days(days: int) -> str:
    """Человекочитаемое название длительности тарифа.

    format_duration_days(30) -> "1 месяц"
    format_duration_days(90) -> "3 месяца"
    format_duration_days(365) -> "365 дней"
    format_duration_days(7) -> "7 дней"
    format_duration_days(1) -> "1 день"
    format_duration_days(21) -> "21 день"
    """
    if days % 30 == 0:
        months = days // 30
        if months == 1:
            return "1 месяц"
        if 2 <= months <= 4:
            return f"{months} месяца"
        return f"{months} месяцев"

    day_word = _pluralize_ru(days, "день", "дня", "дней")
    return f"{days} {day_word}"
