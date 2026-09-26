from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu(role: str = "requester") -> ReplyKeyboardMarkup:
    if role == "volunteer":
        rows = [["🟢 Начать патруль", "⚪ Завершить патруль"],
                ["📍 Обновить геопозицию", "🧭 Статус патруля"], ["📋 Мой вызов"]]
    else:
        rows = [["🚨 СОС / Помощь"], ["📋 Мой вызов", "☎️ Контакты"]]
    rows.append(["👤 Мой профиль"])
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=x) for x in row] for row in rows], resize_keyboard=True)
