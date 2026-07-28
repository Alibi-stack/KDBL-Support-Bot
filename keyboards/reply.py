from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Напишите вопрос или нажмите Отмена",
    )
