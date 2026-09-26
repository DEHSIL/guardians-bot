from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from app.keyboards.main_menu import main_menu

from app.services.api_client import APIClient, BackendAPIError
from app.states.user_states import RegistrationStates

router = Router(name=__name__)


@router.message(Command("register"))
async def register(message: Message, state: FSMContext, api_client: APIClient) -> None:
    if message.from_user is None:
        return
    try:
        profile = await api_client.get_profile(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    await state.clear()
    if profile:
        await state.update_data(role=profile["role"])
        await state.set_state(RegistrationStates.waiting_name)
        await message.answer("Обновление профиля. Введите ваше полное имя.")
        return
    await state.set_state(RegistrationStates.choosing_role)
    await message.answer("Выберите роль:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Нужна помощь (человек с инвалидностью)", callback_data="register:requester")],
        [InlineKeyboardButton(text="Я волонтёр", callback_data="register:volunteer")],
    ]))


@router.callback_query(RegistrationStates.choosing_role, F.data.in_({"register:requester", "register:volunteer"}))
async def choose_role(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(role=callback.data.split(":")[1])
    await state.set_state(RegistrationStates.waiting_name)
    if callback.message:
        await callback.message.answer("Введите ваше полное имя.")


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Регистрация отменена.")


@router.message(RegistrationStates.waiting_name, F.text)
async def collect_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if len(name) < 2 or len(name) > 120:
        await message.answer("Укажите имя длиной от 2 до 120 символов.")
        return
    await state.update_data(full_name=name)
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer("Введите номер телефона в международном формате, например +77001234567.")


@router.message(RegistrationStates.waiting_phone, F.text)
async def collect_phone(message: Message, state: FSMContext, api_client: APIClient) -> None:
    phone = message.text.strip() if message.text else ""
    normalized_phone = phone.replace(" ", "").replace("-", "")
    if not normalized_phone.startswith("+") or not normalized_phone[1:].isdigit() or not 8 <= len(normalized_phone) <= 16:
        await message.answer("Введите корректный номер, например +77001234567.")
        return
    if message.from_user is None:
        await state.clear()
        return
    data = await state.get_data()
    payload = {
        "telegram_id": message.from_user.id,
        "full_name": data["full_name"],
        "phone": normalized_phone,
        "role": data["role"],
    }
    try:
        await api_client.register_user(payload)
    except BackendAPIError:
        await message.answer("Не удалось сохранить профиль. Повторите попытку позже.")
        return
    await state.clear()
    await message.answer("Профиль сохранён.", reply_markup=main_menu(data["role"]))
