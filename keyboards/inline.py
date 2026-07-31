from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


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


def mini_app_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть KDBL Mini App",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")],
        ]
    )


def after_ai_keyboard(
    show_duty: bool = False,
    show_operator: bool = True,
) -> InlineKeyboardMarkup:
    if show_duty:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="Дежурный оператор",
                    callback_data="duty_contact",
                )
            ],
        ]
    elif show_operator:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="Создать обращение оператору",
                    callback_data="human_support",
                )
            ],
        ]
    else:
        keyboard = []
    keyboard.append([InlineKeyboardButton(text="Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
                    text="Передать",
                    callback_data=f"ticket_transfer:{ticket_id}",
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
                    callback_data=f"ticket_phonebook_menu:{ticket_id}",
                ),
            ],
        ]
    )


def ticket_phonebook_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Simbase",
                    callback_data=f"ticket_phonebook:{ticket_id}:simbase",
                ),
                InlineKeyboardButton(
                    text="1С",
                    callback_data=f"ticket_phonebook:{ticket_id}:onec",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Metadoc",
                    callback_data=f"ticket_phonebook:{ticket_id}:metadoc",
                ),
                InlineKeyboardButton(
                    text="Личный кабинет",
                    callback_data=f"ticket_phonebook:{ticket_id}:personal_account",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Lotus / тех. вопросы",
                    callback_data=f"ticket_phonebook:{ticket_id}:lotus_tech",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Все номера",
                    callback_data=f"ticket_phonebook:{ticket_id}:all",
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
            ],
            [
                InlineKeyboardButton(
                    text="РњР°СЂС€СЂСѓС‚",
                    callback_data=f"ticket_route_menu:{ticket_id}",
                ),
            ]
        ]
    )


def ticket_transfer_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Передать",
                    callback_data=f"ticket_transfer:{ticket_id}",
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=f"ticket_close:{ticket_id}",
                ),
            ]
        ]
    )


def ticket_route_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="operator", callback_data=f"ticket_route:{ticket_id}:operator"),
                InlineKeyboardButton(text="developer", callback_data=f"ticket_route:{ticket_id}:developer"),
            ],
            [
                InlineKeyboardButton(text="documents", callback_data=f"ticket_route:{ticket_id}:documents"),
                InlineKeyboardButton(text="bot_admin", callback_data=f"ticket_route:{ticket_id}:bot_admin"),
            ],
            [
                InlineKeyboardButton(text="unknown / triage", callback_data=f"ticket_route:{ticket_id}:unknown"),
            ],
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

