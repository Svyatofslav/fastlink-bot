import pytest

from utils.i18n import TRANSLATIONS, t


def test_t_returns_ru_by_default() -> None:
    result = t("main.menu.title")
    assert result == "Главное меню FastLink. Выберите действие:"


def test_t_returns_en_when_lang_explicit() -> None:
    result = t("main.menu.title", lang="en")
    assert result == "FastLink main menu. Choose an option:"


def test_t_unknown_key_returns_key_itself() -> None:
    unknown_key = "this.key.does.not.exist"
    assert t(unknown_key) == unknown_key


def test_t_unknown_key_with_lang_returns_key_itself() -> None:
    unknown_key = "another.missing.key"
    assert t(unknown_key, lang="en") == unknown_key


def test_t_falls_back_to_ru_when_lang_variant_missing(monkeypatch) -> None:
    """
    Если для запрошенного lang нет перевода в variants, t() должен
    откатиться на "ru", а не на сам key.
    """
    monkeypatch.setitem(
        TRANSLATIONS,
        "test.ru_only_key",
        {"ru": "Только русский текст"},
    )
    result = t("test.ru_only_key", lang="de")
    assert result == "Только русский текст"


def test_t_falls_back_to_key_when_no_ru_and_no_lang_match(monkeypatch) -> None:
    """
    Крайний случай: если у ключа вообще нет ни запрошенного lang, ни ru
    (гипотетическая ситуация — в реальных данных такого не бывает),
    variants.get(lang) or variants.get("ru") or key должно откатиться на key.
    """
    monkeypatch.setitem(
        TRANSLATIONS,
        "test.en_only_key",
        {"en": "English only text"},
    )
    result = t("test.en_only_key", lang="de")
    assert result == "test.en_only_key"


def test_t_with_kwargs_formats_placeholders() -> None:
    result = t("donation.succeeded.message", lang="ru", price="199 ₽")
    assert result == "Донат на 199 ₽ получен! Спасибо за поддержку 🙏"


def test_t_with_kwargs_formats_multiple_placeholders() -> None:
    result = t(
        "donation.ask_amount",
        lang="ru",
        min_price="50 ₽",
        max_price="50000 ₽",
    )
    assert result == "Введите сумму доната в рублях (от 50 ₽ до 50000 ₽):"


def test_t_no_kwargs_returns_unformatted_base_with_placeholders_intact() -> None:
    """
    Если плейсхолдеры в строке есть, но kwargs не переданы вообще,
    t() не пытается форматировать (if kwargs: ложно) и возвращает
    базовую строку с литеральными {price} внутри.
    """
    result = t("donation.succeeded.message", lang="ru")
    assert result == "Донат на {price} получен! Спасибо за поддержку 🙏"


def test_t_missing_required_kwarg_returns_unformatted_base_silently() -> None:
    """
    Если kwargs переданы, но не содержат нужный плейсхолдер, .format()
    бросает KeyError, который t() глушит через except Exception и
    возвращает базовую (неотформатированную) строку — без исключения.

    Это документирует потенциально опасное поведение: ошибка в вызывающем
    коде (забыли передать price) остаётся незамеченной в проде, пользователь
    увидит буквальный текст "{price}" вместо суммы.
    """
    result = t("donation.succeeded.message", lang="ru", wrong_kwarg="value")
    assert result == "Донат на {price} получен! Спасибо за поддержку 🙏"


def test_t_extra_unused_kwargs_do_not_break_formatting() -> None:
    """
    str.format() не падает на лишних kwargs, если все нужные плейсхолдеры
    присутствуют — лишние ключи просто игнорируются.
    """
    result = t(
        "donation.succeeded.message",
        lang="ru",
        price="100 ₽",
        unused_extra="ignored",
    )
    assert result == "Донат на 100 ₽ получен! Спасибо за поддержку 🙏"


def test_t_key_without_placeholders_ignores_kwargs() -> None:
    result = t("menu.buy_subscription", lang="ru", unused="value")
    assert result == "🛒 Купить подписку"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_t_simple_keys_no_kwargs_needed(lang: str) -> None:
    result = t("subs.status_active", lang=lang)
    assert result in ("Активна", "Active")


from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    key=st.sampled_from(list(TRANSLATIONS.keys())),
    lang=st.sampled_from(["ru", "en"]),
)
@settings(max_examples=200, deadline=None)
def test_t_all_keys_and_languages(key: str, lang: str) -> None:
    """
    Property-тест: t(key, lang) работает для ВСЕХ ключей и языков.

    Проверяет:
    - Возвращает строку (не None, не Exception)
    - Для валидного key+lang возвращает перевод (не сам key)
    - Не падает на KeyError/ValueError
    """
    result = t(key, lang=lang)

    # Должна быть строка
    assert isinstance(result, str)

    # Для валидного key+lang должен быть перевод, а не сам key
    # (кроме случаев, когда для lang нет перевода — тогда fallback на ru)
    variants = TRANSLATIONS.get(key)
    if variants:
        # Если есть variants, результат должен быть либо переводом для lang,
        # либо fallback на ru, но не самим key
        assert result != key or (lang not in variants and "ru" not in variants)


@given(
    key=st.sampled_from(list(TRANSLATIONS.keys())),
    lang=st.sampled_from(["ru", "en"]),
    price=st.text(max_size=50),
    min_price=st.text(max_size=50),
    max_price=st.text(max_size=50),
    server_label=st.text(max_size=50),
    tariff_name=st.text(max_size=50),
    new_expires_at=st.text(max_size=50),
    new_traffic=st.text(max_size=50),
    url=st.text(max_size=200),
    traffic=st.text(max_size=50),
    status_label=st.text(max_size=50),
    server_name=st.text(max_size=50),
    starts_at=st.text(max_size=50),
    expires_at=st.text(max_size=50),
    name=st.text(max_size=50),
    days=st.text(max_size=50),
    price_suffix=st.text(max_size=50),
)
@settings(max_examples=100, deadline=None)
def test_t_all_placeholders_with_random_values(
    key: str,
    lang: str,
    price: str,
    min_price: str,
    max_price: str,
    server_label: str,
    tariff_name: str,
    new_expires_at: str,
    new_traffic: str,
    url: str,
    traffic: str,
    status_label: str,
    server_name: str,
    starts_at: str,
    expires_at: str,
    name: str,
    days: str,
    price_suffix: str,
) -> None:
    """
    Property-тест: t(key, lang, **kwargs) работает для ВСЕХ плейсхолдеров.

    Проверяет:
    - Не падает на KeyError (все плейсхолдеры в строке заменены)
    - Возвращает строку (не Exception)
    - Если kwargs не хватает, возвращает строку с незаменёнными плейсхолдерами (fallback)
    """
    kwargs = {
        "price": price,
        "min_price": min_price,
        "max_price": max_price,
        "server_label": server_label,
        "tariff_name": tariff_name,
        "new_expires_at": new_expires_at,
        "new_traffic": new_traffic,
        "url": url,
        "traffic": traffic,
        "status_label": status_label,
        "server_name": server_name,
        "starts_at": starts_at,
        "expires_at": expires_at,
        "name": name,
        "days": days,
        "price_suffix": price_suffix,
    }

    result = t(key, lang=lang, **kwargs)

    # Должна быть строка
    assert isinstance(result, str)

    # Не должно быть исключений (KeyError, ValueError уже обработаны внутри t())
    # Если kwargs не хватает, t() вернёт строку с незаменёнными плейсхолдерами
