from aiogram import Router

from bot.handlers import cars, fallback, menu, mileage, profile_form, settings, start


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(
        start.router, menu.router, cars.router, mileage.router, settings.router,
        profile_form.router,
    )
    # Must stay last: catches whatever no other router handled
    router.include_router(fallback.router)
    return router
