from __future__ import annotations

from datetime import datetime

from domain.purchase_metadata import (
    build_new_subscription_params_from_metadata,
    build_purchase_metadata,
    build_subscription_dates,
    build_yookassa_flat_metadata,
)
from states.purchase import DATA_EXTEND_SUBSCRIPTION_ID, DATA_IS_EXTEND
from tests.factories import make_server, make_tariff, make_user

# ---------------------------------------------------------------------------
# build_subscription_dates
# ---------------------------------------------------------------------------


def test_build_subscription_dates_adds_duration() -> None:
    starts_at, expires_at = build_subscription_dates(duration_days=30)

    assert starts_at.tzinfo is not None
    assert expires_at.tzinfo is not None
    delta = expires_at - starts_at
    assert delta.days == 30


def test_build_subscription_dates_zero_days() -> None:
    starts_at, expires_at = build_subscription_dates(duration_days=0)

    assert (expires_at - starts_at).total_seconds() == 0


# ---------------------------------------------------------------------------
# build_purchase_metadata — обычная покупка (is_extend=False)
# ---------------------------------------------------------------------------


def test_build_purchase_metadata_regular_purchase() -> None:
    user = make_user(telegram_id=555, username="alice")
    server = make_server(name="Amsterdam", emoji="🇳🇱", inbound_tag="vless-in")
    tariff = make_tariff(
        server_id=server.id,
        name="1 month",
        duration_days=30,
        data_limit_bytes=50_000_000_000,
        price_amount=29900,
        price_currency="RUB",
    )
    fsm_data = {DATA_IS_EXTEND: False, DATA_EXTEND_SUBSCRIPTION_ID: None}

    metadata = build_purchase_metadata(
        user=user,
        server=server,
        tariff=tariff,
        fsm_data=fsm_data,
    )

    assert metadata["user"] == {
        "id": user.id,
        "telegram_id": 555,
        "username": "alice",
    }
    assert metadata["server"] == {
        "id": server.id,
        "name": "Amsterdam",
        "emoji": "🇳🇱",
        "marzban_node_id": server.marzban_node_id,
        "inbound_tag": "vless-in",
    }
    assert metadata["tariff"] == {
        "id": tariff.id,
        "name": "1 month",
        "duration_days": 30,
        "data_limit_bytes": 50_000_000_000,
        "price_amount": 29900,
        "price_currency": "RUB",
    }
    assert metadata["flags"] == {
        "is_extend": False,
        "extend_subscription_id": None,
    }
    sub = metadata["subscription"]
    assert (
        sub["marzban_username"]
        == f"fastlink_{user.id}_{int(datetime.fromisoformat(sub['expires_at']).timestamp())}"
    )
    starts_at = datetime.fromisoformat(sub["starts_at"])
    expires_at = datetime.fromisoformat(sub["expires_at"])
    assert (expires_at - starts_at).days == 30


def test_build_purchase_metadata_missing_fsm_flags_defaults_false() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)

    metadata = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data={}
    )

    assert metadata["flags"]["is_extend"] is False
    assert metadata["flags"]["extend_subscription_id"] is None


# ---------------------------------------------------------------------------
# build_purchase_metadata — продление (is_extend=True)
# ---------------------------------------------------------------------------


def test_build_purchase_metadata_extend_flow() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    fsm_data = {DATA_IS_EXTEND: True, DATA_EXTEND_SUBSCRIPTION_ID: 777}

    metadata = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data=fsm_data
    )

    assert metadata["flags"]["is_extend"] is True
    assert metadata["flags"]["extend_subscription_id"] == 777


# ---------------------------------------------------------------------------
# build_yookassa_flat_metadata
# ---------------------------------------------------------------------------


def test_build_yookassa_flat_metadata_regular_purchase() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    fsm_data = {DATA_IS_EXTEND: False, DATA_EXTEND_SUBSCRIPTION_ID: None}
    nested = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data=fsm_data
    )

    flat = build_yookassa_flat_metadata(nested)

    assert flat["tariff_id"] == str(tariff.id)
    assert flat["server_id"] == str(server.id)
    assert flat["marzban_username"] == nested["subscription"]["marzban_username"]
    assert flat["expires_at"] == nested["subscription"]["expires_at"]
    assert flat["starts_at"] == nested["subscription"]["starts_at"]
    assert "subscription_id" not in flat
    assert all(isinstance(v, str) for v in flat.values())
    assert len(flat) <= 16


def test_build_yookassa_flat_metadata_extend_includes_subscription_id() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    fsm_data = {DATA_IS_EXTEND: True, DATA_EXTEND_SUBSCRIPTION_ID: 42}
    nested = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data=fsm_data
    )

    flat = build_yookassa_flat_metadata(nested)

    assert flat["subscription_id"] == "42"


def test_build_yookassa_flat_metadata_extend_flag_true_but_no_id_omits_key() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    fsm_data = {DATA_IS_EXTEND: True, DATA_EXTEND_SUBSCRIPTION_ID: None}
    nested = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data=fsm_data
    )

    flat = build_yookassa_flat_metadata(nested)

    assert "subscription_id" not in flat


def test_build_yookassa_flat_metadata_missing_starts_at_omitted() -> None:
    nested = {
        "server": {"id": 1},
        "tariff": {"id": 2},
        "subscription": {
            "marzban_username": "user1",
            "expires_at": "2026-08-01T00:00:00+00:00",
            "starts_at": None,
        },
        "flags": {"is_extend": False, "extend_subscription_id": None},
    }

    flat = build_yookassa_flat_metadata(nested)

    assert "starts_at" not in flat
    assert flat["tariff_id"] == "2"
    assert flat["server_id"] == "1"


# ---------------------------------------------------------------------------
# build_new_subscription_params_from_metadata (roundtrip)
# ---------------------------------------------------------------------------


def test_build_new_subscription_params_from_metadata_roundtrip() -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id, duration_days=14)
    fsm_data = {DATA_IS_EXTEND: False, DATA_EXTEND_SUBSCRIPTION_ID: None}
    nested = build_purchase_metadata(
        user=user, server=server, tariff=tariff, fsm_data=fsm_data
    )

    params = build_new_subscription_params_from_metadata(nested)

    assert params.tariff_id == tariff.id
    assert params.server_id == server.id
    assert params.marzban_username == nested["subscription"]["marzban_username"]
    assert params.expires_at == datetime.fromisoformat(
        nested["subscription"]["expires_at"]
    )
    assert params.starts_at == datetime.fromisoformat(
        nested["subscription"]["starts_at"]
    )


def test_build_new_subscription_params_from_metadata_missing_starts_at() -> None:
    nested = {
        "server": {"id": 10},
        "tariff": {"id": 20},
        "subscription": {
            "marzban_username": "user10",
            "expires_at": "2026-09-01T12:00:00+00:00",
            "starts_at": None,
        },
        "flags": {"is_extend": False, "extend_subscription_id": None},
    }

    params = build_new_subscription_params_from_metadata(nested)

    assert params.starts_at is None
    assert params.expires_at == datetime.fromisoformat("2026-09-01T12:00:00+00:00")
