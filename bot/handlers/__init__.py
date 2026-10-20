from aiogram import Router

from bot.handlers import fallback, menu, start


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(start.router, menu.router)
    # Must stay last: catches whatever no other router handled
    router.include_router(fallback.router)
    return router
