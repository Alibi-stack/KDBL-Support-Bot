from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="Қазақша", callback_data="lang:kz"),
            ]
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Спросить AI / AI-дан сұрау",
                    callback_data="ask_ai",
                )
            ],
            [InlineKeyboardButton(text="FAQ (частые вопросы)", callback_data="faq")],
            [
                InlineKeyboardButton(
                    text="Сменить язык / Тілді ауыстыру",
                    callback_data="change_language",
                )
            ],
        ]
    )


def after_ai_keyboard(show_duty: bool = False) -> InlineKeyboardMarkup:
    if show_duty:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="Дежурный оператор",
                    callback_data="duty_contact",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Справочник номеров",
                    callback_data="phonebook",
                )
            ],
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="Создать обращение оператору",
                    callback_data="human_support",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Справочник номеров",
                    callback_data="phonebook",
                )
            ],
        ]
    keyboard.append([InlineKeyboardButton(text="Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
        ]
    )


def human_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Позвать оператора / Оператор шақыру",
                    callback_data="human_support",
                )
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")],
        ]
    )


def ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Взять в работу",
                    callback_data=f"ticket_take:{ticket_id}",
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=f"ticket_close:{ticket_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Приветствие",
                    callback_data=f"ticket_tpl:{ticket_id}:hello",
                ),
                InlineKeyboardButton(
                    text="Перезагрузка",
                    callback_data=f"ticket_tpl:{ticket_id}:reboot",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Уточнить данные",
                    callback_data=f"ticket_tpl:{ticket_id}:details",
                ),
                InlineKeyboardButton(
                    text="Закрывающий ответ",
                    callback_data=f"ticket_tpl:{ticket_id}:done",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Номера сотрудников",
                    callback_data=f"ticket_tpl:{ticket_id}:phonebook",
                ),
            ],
        ]
    )


def ticket_claim_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Взять в работу",
                    callback_data=f"ticket_take:{ticket_id}",
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=f"ticket_close:{ticket_id}",
                ),
            ]
        ]
    )


def ticket_open_keyboard(ticket_id: int, topic_url: str | None) -> InlineKeyboardMarkup:
    buttons = []
    if topic_url:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Открыть тикет #{ticket_id}",
                    url=topic_url,
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="Закрыть",
                callback_data=f"ticket_close:{ticket_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
