from aiogram.fsm.state import State, StatesGroup

class SOSStates(StatesGroup):
    awaiting_confirmation = State()
    awaiting_location = State()

class ContactStates(StatesGroup):
    awaiting_name = State()
    awaiting_phone = State()
    awaiting_relationship = State()
