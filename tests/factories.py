from __future__ import annotations

import itertools

from database.models import Server, Tariff, User

_seq = itertools.count(1)


def make_user(**overrides) -> User:
    n = next(_seq)
    defaults = {
        "id": n,
        "telegram_id": 1_000_000 + n,
        "username": f"user{n}",
        "first_name": "Test",
        "last_name": None,
        "language_code": "ru",
        "is_banned": False,
        "is_active": True,
        "last_active_at": None,
    }
    defaults.update(overrides)
    return User(**defaults)


def make_server(**overrides) -> Server:
    n = next(_seq)
    defaults = {
        "id": n,
        "name": f"Server {n}",
        "country_code": None,
        "country_name": None,
        "emoji": None,
        "marzban_node_id": n,
        "metrics_url": None,
        "metrics_token": None,
        "inbound_tag": f"inbound-{n}",
        "is_active": True,
        "sort_order": 100,
    }
    defaults.update(overrides)
    return Server(**defaults)


def make_tariff(*, server_id: int | None = None, **overrides) -> Tariff:
    n = next(_seq)
    defaults = {
        "id": n,
        "server_id": server_id,
        "name": f"Tariff {n}",
        "duration_days": 30,
        "data_limit_bytes": 10_000_000_000,
        "price_amount": 10000,
        "price_currency": "RUB",
        "is_active": True,
        "sort_order": 100,
        "description": None,
    }
    defaults.update(overrides)
    return Tariff(**defaults)


def make_subscription(
    *, user_id: int, server_id: int | None, tariff_id: int | None = None, **overrides
):
    from database.enums import SubscriptionStatus
    from database.models import Subscription

    n = next(_seq)
    defaults = {
        "id": n,
        "user_id": user_id,
        "server_id": server_id,
        "tariff_id": tariff_id,
        "marzban_username": f"user{n}",
        "subscription_url": f"https://sub.example.com/{n}",
        "status": SubscriptionStatus.ACTIVE,
        "starts_at": None,
        "expires_at": None,
        "data_limit_bytes": 10_000_000_000,
        "data_used_bytes": 0,
        "auto_renew": False,
    }
    defaults.update(overrides)
    return Subscription(**defaults)


def make_payment(*, user_id: int, subscription_id: int | None = None, **overrides):
    import uuid

    from database.enums import PaymentProvider, PaymentStatus
    from database.models import Payment

    n = next(_seq)
    defaults = {
        "id": n,
        "user_id": user_id,
        "subscription_id": subscription_id,
        "provider": PaymentProvider.YOOKASSA,
        "provider_payment_id": None,
        "confirmation_url": f"https://yookassa.example.com/{n}",
        "amount": 10000,
        "currency": "RUB",
        "status": PaymentStatus.PENDING,
        "idempotence_key": str(uuid.uuid4()),
        "metadata_snapshot": None,
        "paid_at": None,
        "refundable": False,
        "refunded_amount": 0,
    }
    defaults.update(overrides)
    return Payment(**defaults)
