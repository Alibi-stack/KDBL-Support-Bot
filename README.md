# KDBL Support

Telegram-бот IT-поддержки на aiogram 3.x: AI-ответы, тикеты,
операторская группа, PostgreSQL, ChromaDB, Prometheus/Grafana и Superset.

## Быстрый старт

Рекомендуемый запуск — через Docker Desktop. Бот работает, пока запущены
Docker Desktop и контейнеры проекта.

1. Установите и запустите Docker Desktop.
2. Скопируйте `.env.example` в `.env` и заполните секреты.
3. Запустите сервисы:

```powershell
cd "C:\Users\Alibi\Desktop\AI KDBL\my_ai_bot"
docker compose up -d --build
```

Первый запуск может занять долго: Docker скачивает образы и собирает контейнеры.
Если скачивание падает с `EOF`, повторите команду или заранее скачайте образы:

```powershell
docker pull postgres:16
docker pull python:3.13-slim
docker pull prom/alertmanager:latest
docker pull prom/prometheus:latest
docker pull grafana/grafana:latest
docker pull chromadb/chroma:latest
```

Проверить статус:

```powershell
docker compose ps
```

Проверить логи бота:

```powershell
docker compose logs -f bot
```

В логах должна появиться строка `Telegram connection OK`.

Полезные адреса:

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Superset: http://localhost:8088
- ChromaDB: http://localhost:8000

### Alerts в отдельную тему Telegram

Алерты отправляет Alertmanager через Telegram-бота. По умолчанию чат берётся из
`ALERT_CHAT_ID`, а если он пустой — из `ADMIN_CHAT_ID`.

Чтобы алерты приходили не в `General`, а в отдельную тему:

1. В группе операторов включите Topics.
2. Дайте боту право управлять темами.
3. В группе выполните команду:

```text
/alerts_topic
```

Команда покажет или создаст тему `Alerts` и даст значение:

```env
ALERT_THREAD_ID=...
```

Добавьте его в `.env`, затем перезапустите Alertmanager:

```powershell
docker compose up -d --build alertmanager-init alertmanager
```

Остановить все сервисы:

```powershell
docker compose down
```

После перезагрузки компьютера снова откройте Docker Desktop и выполните:

```powershell
cd "C:\Users\Alibi\Desktop\AI KDBL\my_ai_bot"
docker compose up -d
```

## Локальный запуск без Docker

Локальный запуск сложнее: отдельно нужны PostgreSQL и ChromaDB. Для Docker
используйте `DATABASE_URL` с хостом `postgres`, для локального запуска — с
хостом `localhost`.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `BOT_TOKEN` в `.env`, затем запустите:

```powershell
python main.py
```

Если PowerShell блокирует `.\venv\Scripts\Activate.ps1`, активация не нужна.
Запускайте так:

```powershell
.\venv\Scripts\python.exe main.py
```

## Как выключить бота

При Docker-запуске:

```powershell
docker compose down
```

При локальном запуске в PowerShell нажмите `Ctrl+C`, затем подтвердите `Y`.

## Интеграция с AI

CS-разработчику нужно заменить реализацию в `services/ai_client.py`.
Контракт уже готов:

```python
async def get_ai_response(user_text: str) -> str:
    ...
```

После ответа AI пользователь может сам создать тикет оператору кнопкой под
сообщением.

Сейчас поддержаны два режима:

```env
AI_PROVIDER=stub
```

или

```env
AI_PROVIDER=groq
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile
USE_VECTOR_RAG=false
```

Groq подключен через официальный пакет `groq`.
По умолчанию используется быстрый поиск по ключевым словам в `knowledge_base.json`.
Векторный RAG через HuggingFace можно включить позже через `USE_VECTOR_RAG=true`,
но первый запуск будет заметно дольше.

## Новые функции

- При первом `/start` бот предлагает выбрать язык: русский или казахский.
- В меню есть заглушка `Справочник номеров`; номера можно добавить позже.
- В меню есть `Дежурный оператор`. Контакт задаётся через `DUTY_CONTACT` в `.env`.
- После `REPORT_HOUR` бот один раз в день отправляет Excel-отчёт по тикетам в
  `ADMIN_CHAT_ID`. Для ручной проверки в админ-группе есть команда
  `/daily_report`.
- Мат-фильтр: 2 предупреждения, затем мут на 30 минут.
- Антиспам: по умолчанию 3 сообщения за 10 секунд, затем пауза на 30 секунд.

Настройки:

```env
TIMEZONE=Asia/Qyzylorda
WORKDAY_START_HOUR=9
WORKDAY_START_MINUTE=30
WORKDAY_END_HOUR=18
REPORT_HOUR=18
DUTY_CONTACT=
RATE_LIMIT_MESSAGES=3
RATE_LIMIT_WINDOW=10
RATE_LIMIT_COOLDOWN=30
```

## Операторская группа

1. Создайте Telegram-группу операторов.
2. Добавьте туда бота и сделайте его администратором.
3. Запустите бота.
4. Напишите `/chat_id` в группе.
5. Скопируйте значение `ADMIN_CHAT_ID=...` в `.env`.

После этого бот сможет создавать тикеты в группе. Оператор нажимает
`Взять в работу`, отвечает reply-сообщением на тикет, а бот пересылает ответ
пользователю. Кнопка `Закрыть` завершает тикет.

Для удобного режима helpdesk включите в группе операторов **Темы / Topics**.
Тогда бот будет создавать отдельную тему на каждый тикет, и операторы смогут
писать ответы прямо внутри темы без reply. Если темы не включены или у бота нет
права управлять темами, бот продолжит работать в общем чате.

Нужные права бота в группе операторов:

- отправка сообщений;
- управление темами;
- желательно статус администратора.

## Telegram Mini App

В проект добавлен статичный Mini App в папке `webapp/`. Его можно открыть локально как обычную страницу для проверки интерфейса, а для Telegram нужно разместить эту папку на HTTPS-хостинге и указать ссылку в `.env`:

```env
MINI_APP_URL=https://your-domain.example/
```

После перезапуска бота пользователь может отправить `/app` в личном чате и открыть Mini App кнопкой. Приложение отправляет данные обратно в бота через Telegram WebApp API: вопрос AI, создание обращения, справочник номеров, дежурный контакт и выбор языка.
