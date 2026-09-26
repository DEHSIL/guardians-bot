from datetime import datetime, timedelta, timezone
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from app.keyboards.main_menu import main_menu
from app.services.api_client import APIClient, BackendAPIError

router = Router(name=__name__)
router.message.filter(F.chat.type == "private")
router.edited_message.filter(F.chat.type == "private")


async def location_instructions(message: Message) -> None:
    await message.answer(
        "Для автоматических обновлений: скрепка → Геопозиция → Транслировать геопозицию. "
        "Разрешите Telegram доступ к геопозиции. Бот получает изменения от Telegram, "
        "сам включить GPS или задать частоту обновления он не может. "
        "Кнопка ниже отправляет только разовую точку — её нужно обновлять вручную. "
        "Если обновлений долго нет, вы временно исключаетесь из поиска. /patrol_status — проверить.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📍 Отправить текущую точку", request_location=True)],
            [KeyboardButton(text="⚪ Завершить патруль")],
        ], resize_keyboard=True))


@router.message(Command("patrol"))
@router.message(F.text == "🟢 Начать патруль")
async def start(message: Message, api_client: APIClient) -> None:
    if not message.from_user:
        return
    try:
        await api_client.start_patrol(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    await message.answer("Патруль включён. Для получения вызовов нужны актуальные координаты.")
    await location_instructions(message)


@router.message(Command("stop_patrol"))
@router.message(F.text == "⚪ Завершить патруль")
async def stop(message: Message, api_client: APIClient) -> None:
    if not message.from_user:
        return
    try:
        await api_client.stop_patrol(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    await message.answer("Патруль выключен. Также остановите трансляцию геопозиции в Telegram. "
                         "Уже принятый вызов остаётся за вами до завершения заявителем.", reply_markup=main_menu("volunteer"))


@router.message(Command("patrol_status"))
@router.message(F.text == "🧭 Статус патруля")
async def status(message: Message, api_client: APIClient) -> None:
    if not message.from_user:
        return
    try:
        data = await api_client.patrol_status(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    text = "Патруль выключен."
    if data["active"]:
        text = "Патруль включён. " + ("Координаты актуальны." if data["location_fresh"] else "Координаты устарели или ещё не получены. Отправьте новую геопозицию.")
    await message.answer(text, reply_markup=main_menu("volunteer"))


@router.message(F.text == "📍 Обновить геопозицию")
async def request_location(message: Message) -> None:
    await location_instructions(message)


async def forward_location(
    message: Message, api_client: APIClient, *, edited: bool
) -> None:
    if message.from_user is None or message.location is None:
        return

    location = message.location

    # Расчет окончания трансляции геопозиции (Live Location)
    live_until = (
        message.date + timedelta(seconds=location.live_period)
        if location.live_period
        else None
    )

    # Преобразуем message.edit_date (int/Timestamp) в datetime с UTC, если оно есть
    if message.edit_date:
        observed_at_dt = datetime.fromtimestamp(
            message.edit_date, tz=timezone.utc
        )
    else:
        observed_at_dt = message.date

    payload = {
        "telegram_id": message.from_user.id,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "message_id": message.message_id,
        "sent_at": message.date.isoformat(),
        "observed_at": observed_at_dt.isoformat(),
        "live_until": live_until.isoformat() if live_until else None,
        "is_edit": edited,
    }

    try:
        data = await api_client.update_patrol_location(payload)
    except BackendAPIError as exc:
        if not edited:
            await message.answer(exc.user_message, parse_mode=None)
        return

    if not edited:
        text = (
            "Координаты патруля обновлены."
            if data.get("location_fresh")
            else "Точка устарела. Отправьте новую геопозицию."
        )
        await message.answer(text, reply_markup=main_menu("volunteer"))

@router.message(StateFilter(None), F.location)
async def location(message: Message, api_client: APIClient) -> None:
    await forward_location(message, api_client, edited=False)


@router.edited_message(F.location)
async def edited_location(message: Message, api_client: APIClient) -> None:
    await forward_location(message, api_client, edited=True)
