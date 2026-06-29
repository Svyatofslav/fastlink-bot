from aiogram import Router

from handlers.client import router as client_router

router = Router(name="root")
router.include_router(client_router)

__all__ = ["router"]
