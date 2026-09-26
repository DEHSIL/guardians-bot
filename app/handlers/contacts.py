from html import escape
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from app.services.api_client import APIClient, BackendAPIError
from app.states.sos_states import ContactStates

router = Router(name=__name__)

@router.message(F.text == "☎️ Контакты")
async def contacts(message: Message, api_client: APIClient) -> None:
    if message.from_user is None: return
    try: items = await api_client.list_contacts(message.from_user.id)
    except BackendAPIError as exc: await message.answer(f"⚠️ {exc.user_message}"); return
    listing = "\n".join(f"• {escape(x.name)}: {escape(x.phone)}" for x in items) or "Пока нет доверенных контактов."
    await message.answer(f"<b>Доверенные контакты</b>\n{listing}\n\nЧтобы добавить контакт, используйте /add_contact.")

@router.message(Command("add_contact"))
async def add_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ContactStates.awaiting_name); await message.answer("Введите имя доверенного контакта.")

@router.message(ContactStates.awaiting_name, F.text)
async def add_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not 2 <= len(name) <= 120: await message.answer("Имя должно содержать от 2 до 120 символов."); return
    await state.update_data(contact_name=name); await state.set_state(ContactStates.awaiting_phone); await message.answer("Введите номер телефона в международном формате, например +77001234567.")

@router.message(ContactStates.awaiting_phone, F.text)
async def add_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").replace(" ", "").replace("-", "")
    if not (phone.startswith("+") and phone[1:].isdigit() and 8 <= len(phone) <= 16): await message.answer("Введите корректный номер, например +77001234567."); return
    await state.update_data(contact_phone=phone); await state.set_state(ContactStates.awaiting_relationship); await message.answer("Введите Telegram ID контакта для SOS-уведомлений. Контакт должен сначала запустить этого бота. Отправьте «-», чтобы сохранить только телефон (без уведомлений).")

@router.message(ContactStates.awaiting_relationship, F.text)
async def add_finish(message: Message, state: FSMContext, api_client: APIClient) -> None:
    if message.from_user is None: return
    data = await state.get_data(); relation = (message.text or "").strip(); relation = None if relation == "-" else relation
    if relation is not None and (not relation.isdigit() or not 0 < int(relation) <= 9223372036854775807):
        await message.answer("Введите положительный числовой Telegram ID или «-»."); return
    try: await api_client.add_contact(message.from_user.id, full_name=data["contact_name"], phone=data["contact_phone"], contact_telegram_id=int(relation) if relation else None)
    except BackendAPIError as exc: await message.answer(f"⚠️ {exc.user_message}"); return
    await state.clear(); await message.answer("✅ Доверенный контакт добавлен.")
