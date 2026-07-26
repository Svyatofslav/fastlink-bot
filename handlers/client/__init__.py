from __future__ import annotations

from aiogram import Router

from .donation import router as donation_router
from .fallback import router as fallback_router
from .menu import router as menu_router
from .payment import router as payment_router
from .purchase import router as purchase_router
from .start import router as start_router
from .subscriptions import router as subscriptions_router
from .support import router as support_router

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
