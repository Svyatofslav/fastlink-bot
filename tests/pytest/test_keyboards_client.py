from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from database.enums import SubscriptionStatus
from keyboards.client import (
    CB_PAYMENT_CANCEL,
    CB_PAYMENT_CHECK,
    CB_SERVER_PREFIX,
    CB_SUB_CONFIG_LINK,
    CB_SUB_CONFIG_QR,
    CB_SUB_EXTEND,
    CB_SUB_HELP,
    CB_SUB_LINK,
    CB_SUB_PREFIX,
    CB_SUB_QR,
    CB_TARIFF_PREFIX,
    payment_kb,
    subscription_card_kb,
)

ALL_ID_PREFIXES = [
    CB_SERVER_PREFIX,
    CB_TARIFF_PREFIX,
    CB_PAYMENT_CHECK,
    CB_PAYMENT_CANCEL,
    CB_SUB_PREFIX,
    CB_SUB_LINK,
    CB_SUB_QR,
    CB_SUB_EXTEND,
    CB_SUB_HELP,
    CB_SUB_CONFIG_LINK,
    CB_SUB_CONFIG_QR,
]


@pytest.mark.parametrize("prefix", ALL_ID_PREFIXES)
def test_prefix_id_extraction_via_split_last(prefix):
    fake_id = 42
    callback_data = f"{prefix}:{fake_id}"
    assert int(callback_data.split(":")[-1]) == fake_id


def _fake_user():
    return MagicMock(language_code="ru")


def test_payment_kb_buttons_use_correct_prefixes():
    user = _fake_user()
    kb = payment_kb(payment_id=7, confirmation_url="https://example.com", user=user)
    buttons = [b for row in kb.inline_keyboard for b in row]
    check_btn = next(
        b
        for b in buttons
        if b.callback_data and b.callback_data.startswith(CB_PAYMENT_CHECK)
    )
    cancel_btn = next(
        b
        for b in buttons
        if b.callback_data and b.callback_data.startswith(CB_PAYMENT_CANCEL)
    )
    assert check_btn.callback_data == f"{CB_PAYMENT_CHECK}:7"
    assert cancel_btn.callback_data == f"{CB_PAYMENT_CANCEL}:7"


def test_subscription_card_kb_active_shows_link_and_qr_buttons():
    user = _fake_user()
    sub = MagicMock(id=1, status=SubscriptionStatus.ACTIVE)
    kb = subscription_card_kb(sub, user=user)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"{CB_SUB_LINK}:{sub.id}" in data
    assert f"{CB_SUB_QR}:{sub.id}" in data


def test_subscription_card_kb_disabled_hides_link_buttons():
    user = _fake_user()
    other_status = next(s for s in SubscriptionStatus if s != SubscriptionStatus.ACTIVE)
    sub = MagicMock(id=1, status=other_status)
    kb = subscription_card_kb(sub, user=user)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert not any(d and d.startswith(CB_SUB_LINK) for d in data)
