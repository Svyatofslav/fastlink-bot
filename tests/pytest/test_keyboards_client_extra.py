from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from keyboards.client import support_kb, tariffs_kb
from tests.pytest.factories import make_user


def test_support_kb_raises_when_support_bot_unavailable() -> None:
    user = make_user()

    with (
        patch("keyboards.client.get_support_bot_username", return_value=None),
        pytest.raises(RuntimeError, match="support bot being available"),
    ):
        support_kb(user)


def test_support_kb_builds_deep_link_when_available() -> None:
    user = make_user()

    with patch(
        "keyboards.client.get_support_bot_username",
        return_value="fastlinksupportbot",
    ):
        markup = support_kb(user)

    urls = [
        btn.url for row in markup.inline_keyboard for btn in row if btn.url is not None
    ]
    assert any("fastlinksupportbot" in url for url in urls)


def test_tariffs_kb_without_name_uses_duration_label() -> None:
    user = make_user()
    tariff_without_name = SimpleNamespace(
        id=1, name=None, duration_days=30, price_amount=10000
    )

    markup = tariffs_kb([tariff_without_name], user)

    all_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any(text for text in all_texts)  # рендерится без исключения


def test_tariffs_kb_with_name_uses_name_label() -> None:
    user = make_user()
    tariff_with_name = SimpleNamespace(
        id=2, name="Trial", duration_days=7, price_amount=1000
    )

    markup = tariffs_kb([tariff_with_name], user)

    all_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Trial" in text for text in all_texts)
