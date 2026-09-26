from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    choosing_role = State()
    waiting_name = State()
    waiting_phone = State()
