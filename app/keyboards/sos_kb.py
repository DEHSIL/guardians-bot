from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

def sos_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 Да, нужна помощь", callback_data="sos:confirm")], [InlineKeyboardButton(text="❌ Отмена SOS", callback_data="sos:cancel")]])

def location_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Отправить геопозицию", request_location=True)], [KeyboardButton(text="❌ Отмена SOS")]], resize_keyboard=True, one_time_keyboard=False)


def accept_call(call_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🙋 Принять вызов", callback_data=f"call:accept:{call_id}")]])


def call_controls(call_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "ACCEPTED":
        rows.append([InlineKeyboardButton(text="✅ Завершён — помощь оказана", callback_data=f"call:resolve:{call_id}")])
    if status in ("ACTIVE", "ACCEPTED"):
        rows.append([InlineKeyboardButton(text="❌ Отменить вызов", callback_data=f"call:cancel:{call_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
