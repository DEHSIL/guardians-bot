import logging
import sys
import os
import asyncio
from typing import Dict
from dotenv import load_dotenv
import httpx
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)

# ------------------------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_KEY") 
BACKEND_URL = " http://127.0.0.1:8000"  # URL вашего FastAPI бэкенда
ADMIN_CHAT_ID = 12345678                   # Telegram ID администратора (модератора)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("sos_bot")

# ------------------------------------------------------------------------------
# Состояния FSM (Finite State Machine)
# ------------------------------------------------------------------------------
class RegistrationSG(StatesGroup):
    choosing_role = State()
    waiting_full_name = State()
    waiting_phone = State()
    waiting_document = State()

class SOSCreateSG(StatesGroup):
    waiting_location = State()
    waiting_message = State()
    waiting_radius = State()

# ------------------------------------------------------------------------------
# Клавиатуры (Keyboards)
# ------------------------------------------------------------------------------
def get_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🙋‍♂️ Я Волонтер", callback_data="role:volunteer")],
        [InlineKeyboardButton(text="♿ Нужна помощь (Инвалидность)", callback_data="role:disabled_person")]
    ])

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_volunteer_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Включить трансляцию геопозиции (Live Location)", request_location=True)],
            [KeyboardButton(text="👤 Мой профиль")]
        ],
        resize_keyboard=True
    )

def get_disabled_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚨 СОЗДАТЬ СИГНАЛ SOS")],
            [KeyboardButton(text="👤 Мой профиль")]
        ],
        resize_keyboard=True
    )

def get_send_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить текущую геопозицию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------------------------------------------------------
# Хэндлеры: Старт и Регистрация
# ------------------------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Проверяем, зарегистрирован ли пользователь
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BACKEND_URL}/users/{message.from_user.id}")
            if resp.status_code == 200:
                user_data = resp.json()
                role = user_data.get("role")
                status = user_data.get("verification_status")

                if role == "volunteer":
                    await message.answer(
                        "👋 С возвращением! Вы волонтер. Не забудьте включить трансляцию геопозиции.",
                        reply_markup=get_volunteer_main_keyboard()
                    )
                else:
                    msg = "👋 С возвращением!"
                    if status == "pending":
                        msg += "\n⏳ Ваш документ об инвалидности находится на проверке."
                    elif status == "approved":
                        msg += "\n✅ Ваш профиль верифицирован. Вы можете запрашивать помощь."
                    elif status == "rejected":
                        msg += "\n❌ Ваш документ отклонен модератором."
                    
                    await message.answer(msg, reply_markup=get_disabled_main_keyboard())
                return
        except Exception as e:
            logger.error(f"Ошибка проверки юзера: {e}")

    await message.answer(
        "Привет! Это сервис экстренной взаимопомощи.\nВыберите вашу роль для регистрации:",
        reply_markup=get_role_keyboard()
    )
    await state.set_state(RegistrationSG.choosing_role)

@dp.callback_query(RegistrationSG.choosing_role, F.data.startswith("role:"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    await state.update_data(role=role)
    
    await callback.message.edit_text("Введите ваше ФИО (например, Иванов Иван Иванович):")
    await state.set_state(RegistrationSG.waiting_full_name)
    await callback.answer()

@dp.message(RegistrationSG.waiting_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Поделитесь вашим контактом:", reply_markup=get_phone_keyboard())
    await state.set_state(RegistrationSG.waiting_phone)

@dp.message(RegistrationSG.waiting_phone, F.contact | F.text)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone_number=phone)
    
    user_data = await state.get_data()
    role = user_data["role"]

    if role == "disabled_person":
        await message.answer(
            "📎 Пожалуйста, прикрепите фото или PDF-файл документа, подтверждающего инвалидность (справка / удостоверение):",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationSG.waiting_document)
    else:
        # Регистрация волонтера без документов
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BACKEND_URL}/users/register",
                data={
                    "user_id": message.from_user.id,
                    "full_name": user_data["full_name"],
                    "phone_number": phone,
                    "role": "volunteer"
                }
            )
            if resp.status_code in (200, 201):
                await message.answer(
                    "🎉 Регистрация волонтера успешно завершена!",
                    reply_markup=get_volunteer_main_keyboard()
                )
            else:
                await message.answer("❌ Ошибка при регистрации. Попробуйте позже.")
        await state.clear()

@dp.message(RegistrationSG.waiting_document, F.photo | F.document)
async def process_document(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    # Скачивание файла от пользователя
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_info = await bot.get_file(file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    filename = f"doc_{message.from_user.id}.jpg" if message.photo else message.document.file_name

    # Отправка формы на FastAPI бэкенд
    files = {"document_file": (filename, file_bytes.getvalue())}
    data = {
        "user_id": message.from_user.id,
        "full_name": user_data["full_name"],
        "phone_number": user_data["phone_number"],
        "role": "disabled_person"
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{BACKEND_URL}/users/register", data=data, files=files)
            if resp.status_code in (200, 201):
                await message.answer(
                    "✅ Документ отправлен на проверку модератору.\nВы получите уведомление, как только профиль будет подтвержден.",
                    reply_markup=get_disabled_main_keyboard()
                )
            else:
                await message.answer("❌ Ошибка при отправке документа.")
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
            await message.answer("❌ Сервер недоступен.")
            
    await state.clear()

# ------------------------------------------------------------------------------
# Обновление геолокации волонтера (Live Location & Static Location)
# ------------------------------------------------------------------------------
@dp.message(F.location)
@dp.edited_message(F.location)
async def handle_location_update(message: types.Message):
    """Принимает локацию и Live Location обновления волонтера"""
    lat = message.location.latitude
    lon = message.location.longitude

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{BACKEND_URL}/location",
                json={
                    "user_id": message.from_user.id,
                    "location": {"latitude": lat, "longitude": lon}
                }
            )
        except Exception as e:
            logger.error(f"Ошибка обновления локации: {e}")

# ------------------------------------------------------------------------------
# Хэндлеры: Создание SOS-запроса
# ------------------------------------------------------------------------------
@dp.message(F.text == "🚨 СОЗДАТЬ СИГНАЛ SOS")
async def start_sos(message: types.Message, state: FSMContext):
    await message.answer(
        "📍 Отправьте текущую геолокацию, где вам нужна помощь:",
        reply_markup=get_send_location_keyboard()
    )
    await state.set_state(SOSCreateSG.waiting_location)

@dp.message(SOSCreateSG.waiting_location, F.location)
async def process_sos_location(message: types.Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude
    )
    await message.answer(
        "💬 Опишите кратко, какая помощь вам требуется (например: 'Нужно спуститься по пандусу'):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(SOSCreateSG.waiting_message)

@dp.message(SOSCreateSG.waiting_message)
async def process_sos_message(message: types.Message, state: FSMContext):
    await state.update_data(sos_message=message.text)
    
    # Клавиатура выбора радиуса
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 км", callback_data="radius:1.0"),
            InlineKeyboardButton(text="3 км", callback_data="radius:3.0"),
            InlineKeyboardButton(text="5 км", callback_data="radius:5.0")
        ]
    ])
    await message.answer("🎯 Выберите радиус поиска волонтеров вокруг вас:", reply_markup=kb)
    await state.set_state(SOSCreateSG.waiting_radius)

@dp.callback_query(SOSCreateSG.waiting_radius, F.data.startswith("radius:"))
async def process_sos_radius(callback: types.CallbackQuery, state: FSMContext):
    radius = float(callback.data.split(":")[1])
    sos_data = await state.get_data()

    payload = {
        "user_id": callback.from_user.id,
        "location": {
            "latitude": sos_data["latitude"],
            "longitude": sos_data["longitude"]
        },
        "radius_km": radius,
        "message": sos_data["sos_message"]
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{BACKEND_URL}/sos/create", json=payload)
            if resp.status_code in (200, 201):
                res = resp.json()
                count = res.get("notified_volunteers_count", 0)
                await callback.message.edit_text(
                    f"🚨 <b>Сигнал SOS отправлен!</b>\n Найдено волонтеров неподалеку: {count}.\nОжидайте отклика.",
                    parse_mode="HTML"
                )
            else:
                detail = resp.json().get("detail", "Ошибка при создании заявки")
                await callback.message.edit_text(f"❌ {detail}")
        except Exception as e:
            logger.error(f"Ошибка SOS: {e}")
            await callback.message.edit_text("❌ Сервер недоступен.")

    await state.clear()
    await callback.answer()

# ------------------------------------------------------------------------------
# Хэндлеры: Отклик волонтера на заявку SOS
# ------------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("accept_sos:"))
async def accept_sos_callback(callback: types.CallbackQuery):
    request_id = callback.data.split(":")[1]
    volunteer_id = callback.from_user.id

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/sos/{request_id}/accept",
                json={"helper_id": volunteer_id}
            )
            if resp.status_code == 200:
                await callback.message.edit_caption(
                    caption=callback.message.caption + "\n\n✅ <b>ВЫ ПРИНЯЛИ ЭТУ ЗАЯВКУ!</b>",
                    parse_mode="HTML"
                )
                await callback.answer("Заявка принята! Спасибо за помощь.", show_alert=True)
            else:
                detail = resp.json().get("detail", "Не удалось принять заявку.")
                await callback.answer(f"❌ {detail}", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка при принятии SOS: {e}")
            await callback.answer("❌ Ошибка соединения с сервером.", show_alert=True)

# ------------------------------------------------------------------------------
# Модерация для Админа (Подтверждение инвалидности)
# ------------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("verify_approve:") | F.data.startswith("verify_reject:"))
async def process_admin_verification(callback: types.CallbackQuery):
    action, target_id = callback.data.split(":")
    approve = (action == "verify_approve")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_URL}/admin/verify_user",
                params={"target_user_id": int(target_id), "approve": approve}
            )
            if resp.status_code == 200:
                status_str = "ОДОБРЕН" if approve else "ОТКЛОНЕН"
                await callback.message.edit_text(
                    callback.message.text + f"\n\nРЕШЕНИЕ: <b>{status_str}</b>",
                    parse_mode="HTML"
                )
            else:
                await callback.answer("Ошибка при изменении статуса", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка админа: {e}")

    await callback.answer()

# ------------------------------------------------------------------------------
# Запуск бота
# ------------------------------------------------------------------------------
async def main():
    logger.info("Бот запущен...")
    await dp.start_polling(bot)