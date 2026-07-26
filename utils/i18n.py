from __future__ import annotations

from typing import Dict

# Базовый словарь переводов по ключам и языкам.
# Можно расширять по мере необходимости.
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Главное меню
    "main.menu.title": {
        "ru": "Главное меню FastLink. Выберите действие:",
        "en": "FastLink main menu. Choose an option:",
    },
    # /start приветствия
    "start.welcome.new": {
        "ru": (
            "👋 Добро пожаловать в FastLink!\n\n"
            "Сервис для повышения приватности и защиты ваших данных в сети.\n"
            "Оплата в рублях, подключение занимает не больше пары минут.\n\n"
            "Выберите действие:"
        ),
        "en": (
            "👋 Welcome to FastLink!\n\n"
            "A service to improve privacy and protect your data online.\n"
            "Payments in RUB, setup takes just a couple of minutes.\n\n"
            "Choose an option:"
        ),
    },
    "start.welcome.returning": {
        "ru": "👋 С возвращением в FastLink!\n\nВыберите действие:",
        "en": "👋 Welcome back to FastLink!\n\nChoose an option:",
    },
    # Ошибки и сообщения оплаты (payment.py)
    "payment.not_found": {
        "ru": "Платёж не найден",
        "en": "Payment not found",
    },
    "payment.pending": {
        "ru": (
            "Оплата ещё не поступила. Если вы уже оплатили — "
            "подождите немного и проверьте снова."
        ),
        "en": (
            "Payment has not been received yet. If you already paid, "
            "wait a bit and check again."
        ),
    },
    "payment.succeeded.message": {
        "ru": (
            "✅ Оплата на сумму {price} подтверждена, подписка активирована!\n\n"
            "Вы можете найти её в разделе «Мои подписки»."
        ),
        "en": (
            "✅ Payment of {price} is confirmed, your subscription is now active!\n\n"
            'You can find it in the "My subscriptions" section.'
        ),
    },
    "donation.succeeded.message": {
        "ru": "Донат на {price} получен! Спасибо за поддержку 🙏",
        "en": "Donation of {price} received! Thank you for your support 🙏",
    },
    "donation.ask_amount": {
        "ru": ("Введите сумму доната в рублях (от {min_price} до {max_price}):"),
        "en": ("Enter the donation amount in RUB (from {min_price} to {max_price}):"),
    },
    "donation.invalid_amount": {
        "ru": "Не удалось распознать сумму. Введите число, например 100 или 99.50",
        "en": "Could not parse the amount. Enter a number, e.g. 100 or 99.50",
    },
    "donation.amount_too_small": {
        "ru": "Минимальная сумма доната — {min_price}. Попробуйте снова.",
        "en": "Minimum donation amount is {min_price}. Please try again.",
    },
    "donation.amount_too_large": {
        "ru": "Максимальная сумма доната — {max_price}. Попробуйте снова.",
        "en": "Maximum donation amount is {max_price}. Please try again.",
    },
    "donation.payment_created": {
        "ru": (
            "Сумма к оплате: {price}\n\n"
            "Перейдите по кнопке ниже для оплаты. Ссылка действует 15 минут.\n"
            "После оплаты нажмите «Проверить оплату»."
        ),
        "en": (
            "Amount to pay: {price}\n\n"
            "Use the button below to pay. The link is valid for 15 minutes.\n"
            'After payment, press "Check payment".'
        ),
    },
    "payment.canceled.message": {
        "ru": "❌ Платёж отменён.",
        "en": "❌ Payment has been canceled.",
    },
    "payment.cancel_impossible": {
        "ru": "Платёж уже обрабатывается, отменить его больше нельзя.",
        "en": "Payment is already being processed and can no longer be canceled.",
    },
    # Покупка (purchase.py)
    "purchase.no_servers": {
        "ru": "Нет доступных серверов, попробуйте позже.",
        "en": "No available servers, please try again later.",
    },
    "purchase.choose_server": {
        "ru": "Выберите сервер:",
        "en": "Choose a server:",
    },
    "purchase.server_unavailable": {
        "ru": "Сервер недоступен.",
        "en": "Server is unavailable.",
    },
    "purchase.no_tariffs_for_server": {
        "ru": "Для этого сервера пока нет тарифов.",
        "en": "There are no tariffs for this server yet.",
    },
    "purchase.choose_tariff": {
        "ru": "Выберите тариф:",
        "en": "Choose a tariff:",
    },
    "purchase.tariff_unavailable": {
        "ru": "Тариф недоступен.",
        "en": "Tariff is unavailable.",
    },
    "purchase.cannot_go_back": {
        "ru": "Не удалось вернуться назад, начните заново.",
        "en": "Could not go back, please start again.",
    },
    "purchase.cancelled": {
        "ru": "Покупка отменена.",
        "en": "Purchase has been canceled.",
    },
    "purchase.payment_in_progress": {
        "ru": "Платёж уже создаётся, подождите пару секунд.",
        "en": "Payment is already being created, please wait a few seconds.",
    },
    "purchase.data_expired": {
        "ru": "Данные покупки устарели, начните заново.",
        "en": "Purchase data is outdated, please start again.",
    },
    "purchase.create_failed": {
        "ru": "Не удалось создать платёж. Попробуйте ещё раз чуть позже.",
        "en": "Failed to create payment. Please try again later.",
    },
    "purchase.confirm_text": {
        "ru": (
            "{server_label}\n"
            "{tariff_name}\n"
            "Цена: {price}\n\n"
            "После оплаты вы получите доступ и QR-код для подключения."
        ),
        "en": (
            "{server_label}\n"
            "{tariff_name}\n"
            "Price: {price}\n\n"
            "After payment you will receive access and a QR code to connect."
        ),
    },
    "purchase.payment_created": {
        "ru": (
            "Сумма к оплате: {price}\n\n"
            "Перейдите по кнопке ниже для оплаты. "
            "Ссылка действует 15 минут.\n"
            "После оплаты нажмите «Проверить оплату»."
        ),
        "en": (
            "Amount to pay: {price}\n\n"
            "Use the button below to pay. "
            "The link is valid for 15 minutes.\n"
            'After payment, press "Check payment".'
        ),
    },
    # Кнопки главного меню (keyboards/client.py)
    "menu.buy_subscription": {
        "ru": "🛒 Купить подписку",
        "en": "🛒 Buy subscription",
    },
    "menu.my_subscriptions": {
        "ru": "📱 Мои подписки",
        "en": "📱 My subscriptions",
    },
    "menu.donate": {
        "ru": "💝 Поддержать проект",
        "en": "💝 Support the project",
    },
    "menu.help": {
        "ru": "❓ Помощь",
        "en": "❓ Help",
    },
    "menu.language": {
        "ru": "🌐 Язык",
        "en": "🌐 Language",
    },
    # Поддержка (support.py, keyboards/client.py)
    "support.intro_text": {
        "ru": (
            "По любым вопросам вы можете обратиться в поддержку.\n\n"
            "Нажмите кнопку ниже, чтобы перейти в бот поддержки."
        ),
        "en": (
            "For any questions, you can contact support.\n\n"
            "Press the button below to go to the support bot."
        ),
    },
    "support.contact_button": {
        "ru": "💬 Написать в поддержку",
        "en": "💬 Contact support",
    },
    "support.unavailable": {
        "ru": "⚠️ Поддержка временно недоступна. Попробуйте позже.",
        "en": "⚠️ Support is temporarily unavailable. Please try again later.",
    },
    # Общие
    "common.back_to_main": {
        "ru": "🏠 В главное меню",
        "en": "🏠 Back to main menu",
    },
    # servers_kb
    "servers.price_suffix": {
        "ru": " — от {price}",
        "en": " — from {price}",
    },
    "servers.item_label": {
        "ru": "{name}{price_suffix}",
        "en": "{name}{price_suffix}",
    },
    # tariffs_kb
    "tariffs.item_with_name": {
        "ru": "{name} · {price}",
        "en": "{name} · {price}",
    },
    "tariffs.item_without_name": {
        "ru": "{days} дн. · {price}",
        "en": "{days} days · {price}",
    },
    "tariffs.back_to_servers": {
        "ru": "⬅️ Назад к серверам",
        "en": "⬅️ Back to servers",
    },
    # confirm_purchase_kb
    "purchase.confirm_and_pay": {
        "ru": "✅ Подтвердить и оплатить",
        "en": "✅ Confirm and pay",
    },
    "purchase.change_tariff": {
        "ru": "⬅️ Изменить тариф",
        "en": "⬅️ Change tariff",
    },
    "purchase.cancel": {
        "ru": "❌ Отменить",
        "en": "❌ Cancel",
    },
    # payment_kb
    "payment.go_to_payment": {
        "ru": "💳 Перейти к оплате",
        "en": "💳 Go to payment",
    },
    "payment.check_status": {
        "ru": "🔄 Проверить статус",
        "en": "🔄 Check status",
    },
    "payment.cancel_order": {
        "ru": "❌ Отменить заказ",
        "en": "❌ Cancel order",
    },
    # subscription_card_kb / my_subs_list_kb
    "subs.subscription_link": {
        "ru": "🔗 Ссылка-подписка",
        "en": "🔗 Subscription link",
    },
    "subs.subscription_qr": {
        "ru": "📱 QR подписки",
        "en": "📱 Subscription QR",
    },
    "subs.config_link": {
        "ru": "⚙️ Конфиг-ссылка",
        "en": "⚙️ Config link",
    },
    "subs.config_qr": {
        "ru": "📱 QR конфига",
        "en": "📱 Config QR",
    },
    "subs.extend": {
        "ru": "🔄 Продлить",
        "en": "🔄 Extend",
    },
    "subs.instructions": {
        "ru": "📖 Инструкция",
        "en": "📖 Instructions",
    },
    "subs.back_to_list": {
        "ru": "⬅️ К списку подписок",
        "en": "⬅️ Back to subscriptions list",
    },
    "subs.server_fallback": {
        "ru": "Сервер",
        "en": "Server",
    },
    "subs.status_active": {
        "ru": "Активна",
        "en": "Active",
    },
    "subs.status_disabled": {
        "ru": "Отключена",
        "en": "Disabled",
    },
    "subs.list_item": {
        "ru": "{server_label} · {status_label}",
        "en": "{server_label} · {status_label}",
    },
    "subs.link_message": {
        "ru": "Ваша ссылка-подписка:\n{url}",
        "en": "Your subscription link:\n{url}",
    },
    "subs.qr_caption": {
        "ru": "QR-код вашей ссылки-подписки.",
        "en": "QR code for your subscription link.",
    },
    "subs.config_link_message": {
        "ru": "Ваша актуальная конфиг-ссылка:\n{url}",
        "en": "Your current config link:\n{url}",
    },
    "subs.config_qr_caption": {
        "ru": "QR-код актуальной конфиг-ссылки.",
        "en": "QR code for the current config link.",
    },
    "subs.config_link_failed": {
        "ru": "Не удалось получить конфиг-ссылку. Попробуйте чуть позже.",
        "en": "Failed to get config link. Please try again later.",
    },
    "subs.config_link_unavailable": {
        "ru": "Для этой подписки сейчас нет доступной конфиг-ссылки.",
        "en": "There is no available config link for this subscription right now.",
    },
    # Тексты раздела "Мои подписки"
    "subs.none_yet": {
        "ru": "У вас пока нет подписок.",
        "en": "You do not have any subscriptions yet.",
    },
    "subs.list_title": {
        "ru": "Ваши подписки:",
        "en": "Your subscriptions:",
    },
    "subs.invalid_id": {
        "ru": "Не удалось определить подписку.",
        "en": "Could not determine subscription.",
    },
    "subs.not_found": {
        "ru": "Подписка не найдена.",
        "en": "Subscription not found.",
    },
    # Детализированная карточка подписки
    "subs.tariff_fallback": {
        "ru": "Тариф",
        "en": "Tariff",
    },
    "subs.period_line": {
        "ru": "Период: {starts_at} → {expires_at}",
        "en": "Period: {starts_at} → {expires_at}",
    },
    "subs.price_line": {
        "ru": "Стоимость: {price}",
        "en": "Price: {price}",
    },
    "subs.traffic_line": {
        "ru": "Трафик: {traffic}",
        "en": "Traffic: {traffic}",
    },
    "subs.card_details": {
        "ru": (
            "Сервер: {server_name}\n"
            "Тариф: {tariff_name}\n"
            "Статус: {status_label}\n"
            "{period_line}\n"
            "{price_line}\n"
            "{traffic_line}\n\n"
            "Выберите действие:"
        ),
        "en": (
            "Server: {server_name}\n"
            "Tariff: {tariff_name}\n"
            "Status: {status_label}\n"
            "{period_line}\n"
            "{price_line}\n"
            "{traffic_line}\n\n"
            "Choose an action:"
        ),
    },
    "subs.card_title": {
        "ru": "Выберите способ подключения или продления:",
        "en": "Choose how to connect or extend:",
    },
    "subs.extend_todo": {
        "ru": "Продление пока не реализовано, попробуйте позже.",
        "en": "Extension is not implemented yet, please try later.",
    },
    "subs.help_text": {
        "ru": (
            "Инструкция по подключению будет доступна позже.\n"
            "Пока вы можете использовать ссылку или QR из карточки подписки."
        ),
        "en": (
            "Connection instructions will be available later.\n"
            "For now, you can use the link or QR from the subscription card."
        ),
    },
    "common.unrecognized_message": {
        "ru": "Сообщение не распознано. Пожалуйста, используйте кнопки в сообщениях бота.",
        "en": "Message not recognized. Please use the buttons in the bot's messages.",
    },
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Простая функция перевода: t("key", lang, placeholder=value).

    - Если для lang нет перевода, возвращает русский вариант.
    - Если ключ неизвестен, возвращает сам key (для отладки).
    - Поддерживает format-плейсхолдеры: {price}, {server_label}, ...
    """
    variants = TRANSLATIONS.get(key)
    if not variants:
        base = key
    else:
        base = variants.get(lang) or variants.get("ru") or key
    if kwargs:
        try:
            return base.format(**kwargs)
        except Exception:
            return base
    return base
