from aiogram import Router

from handlers import mini_app, start, support, user_dialog


def setup_routers() -> Router:
    router = Router()
    router.include_router(start.router)
    router.include_router(mini_app.router)
    router.include_router(user_dialog.router)
    router.include_router(support.router)
    return router
