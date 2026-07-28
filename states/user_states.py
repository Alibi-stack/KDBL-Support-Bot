from aiogram.fsm.state import State, StatesGroup


class UserDialog(StatesGroup):
    waiting_question = State()
    waiting_support_question = State()
