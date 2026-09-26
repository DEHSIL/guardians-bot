# Vercel: Telegram-бот

Импортируйте **этот репозиторий** как отдельный проект. Root Directory — корень
репозитория (`.`), Framework Preset — FastAPI. Build Command и Output Directory
оставьте стандартными. Точка входа `app.webhook:app` указана в `pyproject.toml`.
Python — 3.13, зависимости — `requirements.txt`. Docker для Vercel не требуется.

В Settings → Environment Variables задайте для Production:

| Переменная | Значение |
| --- | --- |
| `BOT_TOKEN` | Токен Telegram-бота |
| `REDIS_URL` | Облачный Redis TCP/TLS URL (`redis://...` или `rediss://...`, не REST URL) |
| `BACKEND_BASE_URL` | `https://<api-domain>` без `/api/v1` |
| `BACKEND_API_TOKEN` | Значение `BOT_API_KEY` проекта API |
| `WEBHOOK_SECRET` | Случайная строка из 16–256 латинских букв, цифр, `_` и `-` |

Для генерации секрета: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Можно использовать тот же облачный Redis, что и API: ключи FSM и webhook имеют
префикс `guardians:bot`. Локальные `.env` не включаются в сборку.

Порядок запуска:

1. Разверните API и проверьте его `/ready`.
2. Разверните бота и проверьте `https://<bot-domain>/health`.
3. Production webhook должен быть доступен Telegram без страницы входа Vercel
   Deployment Protection. Сам маршрут проверяет `X-Telegram-Bot-Api-Secret-Token`.
4. Остановите локальный polling этого же бота. В локальном окружении задайте
   `BOT_TOKEN` и `WEBHOOK_SECRET`, совпадающие с Production (прочие настройки
   из `.env` тоже должны быть заполнены). Затем один раз выполните:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.set_webhook https://<bot-domain>
```

Команда регистрирует `https://<bot-domain>/telegram/webhook` в Telegram.
Не запускайте её автоматически при сборке: Preview не должен перехватывать
webhook Production. При прежнем домене и секрете повторная регистрация после
каждого деплоя не нужна. При смене домена или секрета повторите команду.

Обработка update завершается до ответа HTTP 200, без фонового polling.
Успешно обработанные update ID сохраняются в Redis на сутки. Повтор после
частично выполненного запроса всё ещё возможен при падении процесса; абсолютная
однократность отправки Telegram-сообщений не гарантируется.

Проверка: `/register`, `/profile`, `/add_contact` в Telegram, затем SOS и отмена.
Локальный `python main.py` остаётся polling-режимом и удаляет webhook перед
запуском: не запускайте его одновременно с Production для того же токена.

Основа: [FastAPI на Vercel](https://vercel.com/docs/frameworks/backend/fastapi),
[webhook aiogram](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html).

## Включение Live Location после обновления

После миграции и деплоя API, затем бота **повторите регистрацию webhook**:
`python -m app.set_webhook https://<bot-domain>`.
Теперь `allowed_updates` включает `edited_message`; без повторной регистрации
старый webhook не будет передавать обновления Live Location.
Проверьте сценарий на двух отдельных Telegram-аккаунтах: заявитель и волонтёр.
Для испытания конкурирующего принятия используйте второго волонтёра рядом.
