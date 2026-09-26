import asyncio
from html import escape
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from app.keyboards.main_menu import main_menu
from app.keyboards.sos_kb import accept_call, call_controls, location_request, sos_confirmation
from app.services.api_client import APIClient, BackendAPIError
from app.states.sos_states import SOSStates

router = Router(name=__name__)

async def _cancel(message: Message, state: FSMContext, api_client: APIClient, telegram_id: int | None = None) -> None:
    telegram_id = telegram_id or (message.from_user.id if message.from_user else None)
    if telegram_id is None: return
    data = await state.get_data(); alert_id = data.get("active_call_id")
    if alert_id:
        try: await api_client.cancel_sos(telegram_id=telegram_id, alert_id=str(alert_id))
        except BackendAPIError as exc:
            await message.answer(f"⚠️ Не удалось отменить вызов: {exc.user_message}"); return
    await state.clear()
    await message.answer("❌ Вызов SOS отменён.", reply_markup=main_menu())

@router.message(F.text == "🚨 СОС / Помощь")
async def initiate(message: Message, state: FSMContext, api_client: APIClient) -> None:
    if message.from_user is None: return
    try: sos = await api_client.initiate_sos(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(f"⚠️ {exc.user_message}"); return
    await state.clear(); await state.update_data(alert_id=sos.initiate_token)
    await state.set_state(SOSStates.awaiting_confirmation)
    contacts = f"Будут оповещены доверенные контакты ({sos.contacts_count})." if sos.contacts_count else "Будет создан экстренный вызов."
    await message.answer(f"🚨 <b>Экстренный вызов SOS</b>\n{contacts}\nПодтвердите, что вам нужна помощь.", reply_markup=sos_confirmation())

@router.callback_query(SOSStates.awaiting_confirmation, F.data == "sos:confirm")
async def confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SOSStates.awaiting_location)
    await callback.answer()
    await callback.message.answer("📍 Отправьте геопозицию. Это позволит службам и доверенным лицам быстрее найти вас.", reply_markup=location_request())

@router.callback_query(F.data == "sos:cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext, api_client: APIClient) -> None:
    await callback.answer()
    if callback.message: await _cancel(callback.message, state, api_client, callback.from_user.id)

@router.message(SOSStates.awaiting_location, F.location)
async def signal(message: Message, state: FSMContext, api_client: APIClient) -> None:
    if message.from_user is None or message.location is None: return
    alert_id = (await state.get_data()).get("alert_id")
    if not isinstance(alert_id, str):
        await state.clear(); await message.answer("Сессия SOS устарела. Нажмите «🚨 СОС / Помощь» ещё раз.", reply_markup=main_menu()); return
    try:
        result = await api_client.signal_sos(telegram_id=message.from_user.id, alert_id=alert_id, latitude=message.location.latitude, longitude=message.location.longitude)
    except BackendAPIError as exc:
        await message.answer(f"⚠️ SOS ещё не отправлен: {exc.user_message}\nПопробуйте отправить геопозицию снова.", reply_markup=location_request()); return
    await state.clear()
    await state.update_data(active_call_id=result.call_id)
    if result.status != "ACTIVE":
        await message.answer(f"Вызов №{result.call_id} уже изменил статус: {result.status}. Нажмите «Мой вызов».", reply_markup=main_menu())
        return
    contacts = {c.telegram_id for c in result.contacts if c.telegram_id is not None}
    volunteers = set(result.volunteer_telegram_ids)
    recipients = contacts | volunteers
    limiter = asyncio.Semaphore(5)

    async def notify(recipient: int) -> tuple[int, bool]:
        async with limiter:
            try:
                await message.bot.send_message(recipient, result.notification_text, parse_mode=None,
                    reply_markup=accept_call(result.call_id) if recipient in volunteers else None)
                return recipient, True
            except TelegramAPIError:
                return recipient, False

    outcomes = await asyncio.gather(*(notify(recipient) for recipient in recipients))
    delivered = {recipient for recipient, success in outcomes if success}
    suffix = (f"Вызов №{result.call_id} зарегистрирован. Радиус поиска: {result.radius_km:g} км. "
              f"Оповещено волонтёров: {len(delivered & volunteers)} из {len(volunteers)}; "
              f"доверенных контактов: {len(delivered & contacts)} из {len(contacts)}.")
    if not delivered:
        suffix += " Уведомления не доставлены. Свяжитесь с близкими по телефону."
    await message.answer(f"🚨 <b>Сигнал SOS отправлен</b>\n{suffix}\nЕсли состояние ухудшается, звоните 112.",
                         reply_markup=main_menu())
    await message.answer(f"Управление вызовом №{result.call_id}:", reply_markup=call_controls(result.call_id, result.status))


@router.message(StateFilter(SOSStates.awaiting_confirmation, SOSStates.awaiting_location), F.text == "❌ Отмена SOS")
async def cancel_message(message: Message, state: FSMContext, api_client: APIClient) -> None:
    await _cancel(message, state, api_client)

@router.message(Command("cancel_sos"))
async def cancel_active(message: Message, state: FSMContext, api_client: APIClient) -> None:
    if message.from_user is None:
        return
    try:
        await api_client.cancel_sos(telegram_id=message.from_user.id, alert_id="")
    except BackendAPIError as exc:
        await message.answer(escape(exc.user_message))
        return
    await state.clear()
    await message.answer("Вызов SOS отменён.", reply_markup=main_menu())


@router.message(Command("call"))
@router.message(F.text == "📋 Мой вызов")
async def current_call(message: Message, api_client: APIClient) -> None:
    if not message.from_user:
        return
    try:
        call = await api_client.active_call(message.from_user.id)
    except BackendAPIError as exc:
        await message.answer(exc.user_message, parse_mode=None)
        return
    if call is None:
        await message.answer("Открытого вызова нет.")
        return
    owner = call["telegram_id"] == message.from_user.id
    status_text = "Ожидает волонтёра" if call["status"] == "ACTIVE" else "Волонтёр принял вызов"
    await message.answer(f"Вызов №{call['call_id']}: {status_text}.\n"
        f"https://www.google.com/maps?q={call['latitude']},{call['longitude']}",
        reply_markup=call_controls(call["call_id"], call["status"]) if owner else None)


@router.callback_query(F.data.regexp(r"^call:(accept|resolve|cancel):[0-9]+$"))
async def call_action(callback: CallbackQuery, state: FSMContext, api_client: APIClient) -> None:
    await callback.answer()
    _, action, raw_id = callback.data.split(":")
    call_id = int(raw_id)
    actor = callback.from_user.id
    try:
        if action == "accept":
            call = await api_client.accept_call(call_id, actor)
        elif action == "resolve":
            call = await api_client.resolve_call(call_id, actor)
        else:
            await api_client.cancel_sos(telegram_id=actor, alert_id=str(call_id))
            await state.clear()
            await callback.bot.send_message(actor, f"Вызов №{call_id} отменён.", reply_markup=main_menu())
            return
    except BackendAPIError as exc:
        await callback.bot.send_message(actor, exc.user_message, parse_mode=None)
        return
    if action == "accept":
        await callback.bot.send_message(actor, f"Вы приняли вызов №{call_id}. Другие волонтёры уже не могут его принять.\n"
            f"https://www.google.com/maps?q={call['latitude']},{call['longitude']}", reply_markup=main_menu("volunteer"))
        try:
            name = escape(call.get("volunteer_name") or "Волонтёр")
            await callback.bot.send_message(call["requester_telegram_id"],
                f"Вызов №{call_id} принят: {name}. После оказания помощи нажмите «Завершён».",
                reply_markup=call_controls(call_id, "ACCEPTED"))
        except TelegramAPIError:
            await callback.bot.send_message(actor, "Не удалось уведомить заявителя. Вызов сохранён, он виден через /call.")
    else:
        await state.clear()
        await callback.bot.send_message(actor, f"Вызов №{call_id} завершён. Спасибо за подтверждение!", reply_markup=main_menu())
        if call.get("volunteer_telegram_id"):
            try:
                await callback.bot.send_message(call["volunteer_telegram_id"],
                    f"Заявитель завершил вызов №{call_id}. Спасибо за помощь!", reply_markup=main_menu("volunteer"))
            except TelegramAPIError:
                pass
