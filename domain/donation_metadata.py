from __future__ import annotations
from database.models import User


def build_donation_metadata(*, user: User, amount: int, currency: str = "RUB") -> dict:
    return {
        "type": "donation",
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
        },
        "amount": amount,
        "currency": currency,
    }


def build_yookassa_donation_flat_metadata(metadata: dict) -> dict[str, str]:
    return {"type": "donation", "user_id": str(metadata["user"]["id"])}
