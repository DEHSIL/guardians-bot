"""Typed HTTP boundary. No domain data is stored by the bot service."""
from __future__ import annotations
import logging
from collections.abc import Mapping
from typing import Any
import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

class BackendAPIError(RuntimeError):
    def __init__(self, user_message: str, *, status_code: int | None = None) -> None:
        super().__init__(user_message); self.user_message = user_message; self.status_code = status_code

class SOSInitiateResponse(BaseModel):
    initiate_token: str
    expires_in_seconds: int
    active: bool = False
    requires_location: bool = True
    contacts_count: int = Field(default=0, ge=0)

class SOSSignalResponse(BaseModel):
    call_id: int
    status: str
    notification_text: str
    contacts: list[EmergencyContact]
    maps: dict[str, str]
    volunteer_telegram_ids: list[int] = Field(default_factory=list)
    radius_km: float = 3.0

class EmergencyContact(BaseModel):
    id: int
    name: str
    phone: str
    telegram_id: int | None = None

SOSSignalResponse.model_rebuild()

class APIClient:
    def __init__(self, client: httpx.AsyncClient) -> None: self._client = client

    async def get_profile(self, telegram_id: int) -> dict[str, Any] | None:
        response = await self._request("GET", f"/api/v1/users/{telegram_id}", allow_not_found=True)
        return None if response is None else self._json_object(response)

    async def register_user(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._json_object(await self._request("PUT", f"/api/v1/users/{payload['telegram_id']}", json=dict(payload)))

    async def initiate_sos(self, telegram_id: int) -> SOSInitiateResponse:
        return self._model(await self._request("POST", "/api/v1/sos/initiate", json={"telegram_id": telegram_id}), SOSInitiateResponse)

    async def signal_sos(self, *, telegram_id: int, alert_id: str, latitude: float, longitude: float) -> SOSSignalResponse:
        return self._model(await self._request("POST", "/api/v1/sos/signal", json={"telegram_id": telegram_id, "initiate_token": alert_id, "latitude": latitude, "longitude": longitude}), SOSSignalResponse)

    async def cancel_sos(self, *, telegram_id: int, alert_id: str) -> None:
        payload = {"telegram_id": telegram_id}
        if alert_id.isdigit():
            payload["call_id"] = int(alert_id)
        await self._request("POST", "/api/v1/sos/cancel", json=payload)

    async def list_contacts(self, telegram_id: int) -> list[EmergencyContact]:
        response = await self._request("GET", f"/api/v1/contacts/{telegram_id}")
        try:
            payload = response.json(); records = payload.get("items", payload) if isinstance(payload, dict) else payload
            return [EmergencyContact.model_validate(item) for item in records]
        except (ValueError, ValidationError, TypeError) as exc:
            raise BackendAPIError("Сервис вернул некорректные данные контактов.") from exc

    async def add_contact(self, telegram_id: int, *, full_name: str, phone: str, contact_telegram_id: int | None) -> EmergencyContact:
        return self._model(await self._request("POST", f"/api/v1/contacts/{telegram_id}", json={"name": full_name, "phone": phone, "telegram_id": contact_telegram_id}), EmergencyContact)

    async def start_patrol(self, telegram_id: int) -> dict[str, Any]:
        return self._json_object(await self._request("POST", "/api/v1/patrol/start", json={"telegram_id": telegram_id}))

    async def stop_patrol(self, telegram_id: int) -> dict[str, Any]:
        return self._json_object(await self._request("POST", "/api/v1/patrol/stop", json={"telegram_id": telegram_id}))

    async def patrol_status(self, telegram_id: int) -> dict[str, Any]:
        return self._json_object(await self._request("GET", f"/api/v1/patrol/{telegram_id}"))

    async def update_patrol_location(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._json_object(await self._request("PUT", "/api/v1/patrol/location", json=dict(payload)))

    async def active_call(self, telegram_id: int) -> dict[str, Any] | None:
        response = await self._request("GET", f"/api/v1/sos/active/{telegram_id}", allow_not_found=True)
        return self._json_object(response) if response is not None else None

    async def accept_call(self, call_id: int, telegram_id: int) -> dict[str, Any]:
        return self._json_object(await self._request("POST", f"/api/v1/sos/{call_id}/accept", json={"volunteer_telegram_id": telegram_id}))

    async def resolve_call(self, call_id: int, telegram_id: int) -> dict[str, Any]:
        return self._json_object(await self._request("POST", f"/api/v1/sos/{call_id}/resolve", json={"resolver_telegram_id": telegram_id}))

    async def _request(self, method: str, url: str, *, allow_not_found: bool = False, **kwargs: Any) -> httpx.Response | None:
        try: response = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc: raise BackendAPIError("Сервер долго не отвечает. Попробуйте ещё раз.") from exc
        except httpx.HTTPError as exc: raise BackendAPIError("Не удалось связаться с сервером помощи.") from exc
        if allow_not_found and response.status_code == httpx.codes.NOT_FOUND: return None
        if response.is_error:
            detail = self._detail(response); logger.warning("Backend %s %s failed: %s", method, url, response.status_code)
            if response.status_code == 409: raise BackendAPIError(detail or "Для вас уже есть активный вызов SOS.", status_code=409)
            if response.status_code in (401, 403): raise BackendAPIError("Доступ к сервису помощи временно ограничен.", status_code=response.status_code)
            if 400 <= response.status_code < 500: raise BackendAPIError(detail or "Не удалось обработать запрос. Проверьте данные.", status_code=response.status_code)
            raise BackendAPIError("Сервис помощи временно недоступен.", status_code=response.status_code)
        return response

    @staticmethod
    def _detail(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            return detail if isinstance(detail, str) else None
        except ValueError: return None

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try: value = response.json()
        except ValueError as exc: raise BackendAPIError("Сервис вернул некорректный ответ.") from exc
        if not isinstance(value, dict): raise BackendAPIError("Сервис вернул некорректный ответ.")
        return value

    def _model(self, response: httpx.Response, model: type[BaseModel]) -> Any:
        try: return model.model_validate(self._json_object(response))
        except ValidationError as exc:
            logger.warning("Unexpected backend schema: %s", exc)
            raise BackendAPIError("Сервис вернул неполные данные. Попробуйте позже.") from exc
