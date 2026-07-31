from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Напишите вопрос или нажмите Отмена",
    )


def mini_app_launch_keyboard(mini_app_url: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть KDBL Mini App",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Откройте Mini App кнопкой ниже",
    )
