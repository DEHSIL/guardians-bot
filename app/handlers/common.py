from html import escape
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from app.keyboards.main_menu import main_menu
from app.services.api_client import APIClient, BackendAPIError

router = Router(name=__name__)

@router.message(CommandStart())
async def start(message: Message, api_client: APIClient) -> None:
    if message.from_user is None:
        return
    try:
        profile = await api_client.get_profile(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    if profile is None:
        await message.answer("Добро пожаловать! Зарегистрируйтесь командой /register и выберите вашу роль.")
        return
    await message.answer("Выберите действие.", reply_markup=main_menu(profile["role"]))

@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer("/register — регистрация; /profile — профиль; /call — текущий вызов; "
                         "/patrol — начать патруль; /stop_patrol — закончить. "
                         "Для патруля включите трансляцию геопозиции через скрепку → Геопозиция. "
                         "Заявитель вызывает помощь кнопкой SOS и закрывает принятый вызов кнопкой «Завершён».")

@router.message(Command("profile"))
@router.message(F.text == "👤 Мой профиль")
async def profile(message: Message, api_client: APIClient) -> None:
    if message.from_user is None: return
    try: data = await api_client.get_profile(message.from_user.id)
    except BackendAPIError as exc: await message.answer(f"⚠️ {exc.user_message}"); return
    if data is None: await message.answer("Профиль не найден. Создайте его командой /register."); return
    await message.answer(f"<b>Ваш профиль</b>\nИмя: {escape(data.get('full_name') or 'не указано')}\nТелефон: {escape(data.get('phone') or 'не указан')}\nРоль: {'Волонтёр' if data.get('role') == 'volunteer' else 'Нужна помощь'}", reply_markup=main_menu(data.get("role", "requester")))
