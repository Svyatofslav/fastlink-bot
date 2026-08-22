from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.enums import SubscriptionStatus
from utils.format import format_price
from utils.i18n import t
from utils.telegram import get_support_bot_username

if TYPE_CHECKING:
    from database.models import Server, Subscription, Tariff, User

# ---------------------------------------------------------------------------
# Callback data prefixes (single source of truth for this module)
# ---------------------------------------------------------------------------
CB_MENU_BUY = "menu:buy"
CB_MENU_MY_SUBS = "menu:my_subs"
CB_MENU_HELP = "menu:help"
CB_MENU_MAIN = "menu:main"
CB_MENU_CANCEL = "menu:cancel"
CB_MENU_BACK_TO_TARIFFS = "menu:back_to_tariffs"
CB_MENU_LANGUAGE = "menu:language"  # NEW
CB_MENU_DONATE = "menu:donate"
CB_DONATION_CANCEL = "donation:cancel"

CB_SERVER_PREFIX = "srv"  # srv:{server_id}
CB_TARIFF_PREFIX = "tariff"  # tariff:{tariff_id}
CB_CONFIRM_PAY = "confirm:pay"

CB_PAYMENT_CHECK = "payment:check"  # payment:check:{payment_id}
CB_PAYMENT_CANCEL = "payment:cancel"  # payment:cancel:{payment_id}

CB_SUB_PREFIX = "sub"  # sub:{subscription_id}
CB_SUB_LINK = "sub:link"  # sub:link:{id}
CB_SUB_QR = "sub:qr"  # sub:qr:{id}
CB_SUB_EXTEND = "sub:extend"  # sub:extend:{id}
CB_SUB_HELP = "sub:help"  # sub:help:{id}
CB_SUB_CONFIG_LINK = "sub:config_link"  # sub:config_link:{id}
CB_SUB_CONFIG_QR = "sub:config_qr"  # sub:config_qr:{id}


def main_menu_kb(user: User) -> InlineKeyboardMarkup:
    """Главное меню: точка входа во все клиентские сценарии."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("menu.buy_subscription", lang),
            callback_data=CB_MENU_BUY,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("menu.my_subscriptions", lang),
            callback_data=CB_MENU_MY_SUBS,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("menu.donate", lang),
            callback_data=CB_MENU_DONATE,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("menu.help", lang),
            callback_data=CB_MENU_HELP,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("menu.language", lang),
            callback_data=CB_MENU_LANGUAGE,
        )
    )
    return builder.as_markup()


def servers_kb(
    servers: list[Server],
    min_prices: dict[int, int],
    user: User,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора сервера.

    min_prices: {server_id: min price_amount in minor units} для пометки "от N ₽".
    """
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    for server in servers:
        min_price = min_prices.get(server.id)
        if min_price is not None:
            price_suffix = t(
                "servers.price_suffix", lang, price=format_price(min_price)
            )
        else:
            price_suffix = ""
        label = t(
            "servers.item_label",
            lang,
            name=server.name,
            price_suffix=price_suffix,
        )
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"{CB_SERVER_PREFIX}:{server.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t("common.back_to_main", lang),
            callback_data=CB_MENU_MAIN,
        )
    )
    return builder.as_markup()


def tariffs_kb(
    tariffs: list[Tariff],
    user: User,
    back_callback: str = CB_MENU_BUY,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа для уже выбранного сервера."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        price = format_price(tariff.price_amount)
        if tariff.name:
            label = t(
                "tariffs.item_with_name",
                lang,
                name=tariff.name,
                price=price,
            )
        else:
            label = t(
                "tariffs.item_without_name",
                lang,
                days=tariff.duration_days,
                price=price,
            )
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"{CB_TARIFF_PREFIX}:{tariff.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t("tariffs.back_to_servers", lang),
            callback_data=back_callback,
        )
    )
    return builder.as_markup()


def confirm_purchase_kb(user: User) -> InlineKeyboardMarkup:
    """Подтверждение заказа перед созданием Subscription/Payment."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("purchase.confirm_and_pay", lang),
            callback_data=CB_CONFIRM_PAY,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("purchase.change_tariff", lang),
            callback_data=CB_MENU_BACK_TO_TARIFFS,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("purchase.cancel", lang),
            callback_data=CB_MENU_CANCEL,
        )
    )
    return builder.as_markup()


def payment_kb(
    payment_id: int,
    confirmation_url: str,
    user: User,
) -> InlineKeyboardMarkup:
    """Клавиатура с ссылкой на оплату YooKassa и служебными действиями."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("payment.go_to_payment", lang),
            url=confirmation_url,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("payment.check_status", lang),
            callback_data=f"{CB_PAYMENT_CHECK}:{payment_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("payment.cancel_order", lang),
            callback_data=f"{CB_PAYMENT_CANCEL}:{payment_id}",
        )
    )
    return builder.as_markup()


def subscription_card_kb(
    subscription: Subscription,
    user: User,
) -> InlineKeyboardMarkup:
    """Карточка подписки: 4 способа подключения + продление."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    status_value = getattr(subscription.status, "value", subscription.status)
    is_active = status_value == SubscriptionStatus.ACTIVE.value

    if is_active:
        builder.row(
            InlineKeyboardButton(
                text=t("subs.subscription_link", lang),
                callback_data=f"{CB_SUB_LINK}:{subscription.id}",
            ),
            InlineKeyboardButton(
                text=t("subs.subscription_qr", lang),
                callback_data=f"{CB_SUB_QR}:{subscription.id}",
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text=t("subs.config_link", lang),
                callback_data=f"{CB_SUB_CONFIG_LINK}:{subscription.id}",
            ),
            InlineKeyboardButton(
                text=t("subs.config_qr", lang),
                callback_data=f"{CB_SUB_CONFIG_QR}:{subscription.id}",
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text=t("subs.extend", lang),
            callback_data=f"{CB_SUB_EXTEND}:{subscription.id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("subs.instructions", lang),
            callback_data=f"{CB_SUB_HELP}:{subscription.id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("subs.back_to_list", lang),
            callback_data=CB_MENU_MY_SUBS,
        )
    )
    return builder.as_markup()


def my_subs_list_kb(
    subscriptions: list[Subscription],
    servers_by_id: dict[int, Server],
    user: User,
) -> InlineKeyboardMarkup:
    """Список подписок пользователя с кратким статусом в подписи кнопки."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    for sub in subscriptions:
        server = servers_by_id.get(sub.server_id)
        server_label = server.name if server else t("subs.server_fallback", lang)
        status_value = getattr(sub.status, "value", sub.status)
        if status_value == SubscriptionStatus.ACTIVE.value:
            status_label = t("subs.status_active", lang)
        else:
            status_label = t("subs.status_disabled", lang)
        label = t(
            "subs.list_item",
            lang,
            server_label=server_label,
            status_label=status_label,
        )
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"{CB_SUB_PREFIX}:{sub.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t("common.back_to_main", lang),
            callback_data=CB_MENU_MAIN,
        )
    )
    return builder.as_markup()


def back_to_main_kb(user: User) -> InlineKeyboardMarkup:
    """Универсальная кнопка возврата в главное меню."""
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("common.back_to_main", lang),
            callback_data=CB_MENU_MAIN,
        )
    )
    return builder.as_markup()


def support_kb(user: User) -> InlineKeyboardMarkup:
    """
    Кнопка перехода в бот поддержки + возврат в главное меню.

    Вызывается только после проверки get_support_bot_username() на None
    в handlers/client/support.py — сюда доходят только когда поддержка
    реально доступна.
    """
    lang = user.language_code or "ru"
    username = get_support_bot_username()
    if username is None:
        raise RuntimeError(
            "support_kb() called without support bot being available — "
            "caller must check get_support_bot_username() first"
        )
    deep_link = f"https://t.me/{username}"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("support.contact_button", lang),
            url=deep_link,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("common.back_to_main", lang),
            callback_data=CB_MENU_MAIN,
        )
    )
    return builder.as_markup()


def donation_amount_kb(user: User) -> InlineKeyboardMarkup:
    lang = user.language_code or "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=t("purchase.cancel", lang), callback_data=CB_DONATION_CANCEL)
    builder.adjust(1)
    return builder.as_markup()
