from __future__ import annotations

from aiogram import Router

from handlers.client.donation import router as donation_router
from handlers.client.fallback import router as fallback_router
from handlers.client.menu import router as menu_router
from handlers.client.payment import router as payment_router
from handlers.client.purchase import router as purchase_router
from handlers.client.start import router as start_router
from handlers.client.subscriptions import router as subscriptions_router
from handlers.client.support import router as support_router

router = Router(name="client")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(purchase_router)
router.include_router(payment_router)
router.include_router(subscriptions_router)
router.include_router(support_router)
router.include_router(donation_router)
router.include_router(fallback_router)  # ВСЕГДА последним!

__all__ = ["router"]
