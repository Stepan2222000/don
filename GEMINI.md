
> **ВАЖНО:** Этот файл должен динамически обновляться при любых изменениях в структуре проекта.

## Обзор проекта

Telegram Automation System - система автоматической рассылки сообщений в Telegram-чаты через web.telegram.org/k с использованием профилей Donut Browser и Playwright.

### Ключевые особенности

- **Async архитектура** - полностью асинхронный код на asyncio
- **PostgreSQL + asyncpg** - асинхронная работа с БД через connection pool
- **Worker Pool** - параллельная обработка несколькими профилями
- **Donut Browser** - использование fingerprints и прокси из профилей
- **Campaign Groups** - группировка задач, профилей и сообщений
- **Session-based cycles** - отслеживание циклов через run_id
- **Proxy Management** - автоматическая ротация прокси при проблемах
- **Auto-restart workers** - exponential backoff при падениях

## Структура проекта

```
tg-automatizamtion/
├── src/                          # Основные модули
│   ├── __init__.py
│   ├── main.py                  # CLI + WorkerManager
│   ├── config.py                # Конфигурация и Campaign Groups
│   ├── database.py              # AsyncDatabase (asyncpg)
│   ├── task_queue.py            # Async очередь задач
│   ├── worker.py                # Async Worker процесс
│   ├── browser_automation.py    # Playwright + Camoufox
│   ├── telegram_sender.py       # Автоматизация Telegram Web
│   ├── profile_manager.py       # Управление профилями Donut
│   ├── proxy_manager.py         # Управление прокси
│   ├── proxy_health.py          # Мониторинг здоровья прокси
│   ├── error_handler.py         # Async обработка ошибок
│   └── logger.py                # Мультифайловое логирование
├── scripts/                      # Утилиты запуска
│   ├── start_automation.py      # Запуск автоматизации
│   ├── manage_groups.py         # Управление группами
│   ├── manage_tasks.py          # Управление задачами
│   ├── profile_stats.py         # Статистика профилей
│   ├── sync_group_messages.py   # Синхронизация сообщений
│   ├── migrate_proxies.py       # Миграция прокси в БД
│   ├── reset_database.py        # Сброс БД
│   ├── clear_database.py        # Очистка БД
│   ├── clear_db_force.py        # Принудительная очистка
│   ├── migrate_db.py            # Миграции БД
│   ├── reset_groups.py          # Сброс групп
│   └── interactive_utils.py     # Утилиты интерактива
├── db/
│   ├── schema_postgresql.sql    # PostgreSQL схема (основная)
│   ├── schema.sql               # SQLite схема (legacy)
│   ├── migrate_add_run_id.sql   # Миграция run_id
│   ├── migrate_add_logged_out.sql
│   └── migrate_proxy_system.sql # Миграция прокси
├── data/
│   ├── groups.json              # Campaign groups конфиг
│   ├── chats.txt                # Список чатов
│   ├── proxies.txt              # Пул прокси
│   └── messages.json            # Шаблоны (legacy)
├── docs/
│   ├── REQUIREMENTS.md
│   ├── SELECTORS.md
│   ├── GROUPS.md
│   └── SESSION_BASED_CYCLES.md
├── logs/                         # Создается автоматически
│   ├── main.log
│   ├── success.log
│   ├── failed_chats.log
│   ├── failed_send.log
│   ├── screenshots/
│   └── debug_trash/
├── config.yaml                   # Основная конфигурация
├── requirements.txt
└── README.md
```

## Модули (src/)

### database.py
**Async PostgreSQL через asyncpg**

```python
class AsyncDatabase:
    _pool: asyncpg.Pool  # Connection pool (min=2, max=10)

    async def connect()           # Создание pool
    async def close()             # Закрытие pool
    async def transaction()       # Context manager для транзакций
```

Ключевые методы:
- `add_profile()`, `get_active_profiles()`, `block_profile()`, `mark_profile_logged_out()`
- `import_chats()`, `get_next_task()`, `block_task()`, `set_task_next_available()`
- `import_messages()`, `get_active_messages()`
- `log_send()`, `add_screenshot()`, `cleanup_old_screenshots()`
- `get_proxy_for_profile()`, `assign_proxy()`, `mark_proxy_unhealthy()`
- `update_profile_daily_stats()`, `get_profile_daily_stats()`

### task_queue.py
**Async очередь с атомарными операциями**

```python
class TaskQueue:
    db: AsyncDatabase
    config: Config
```

Методы:
- `get_next_incomplete_task(group_id, profile_id, run_id)` - FOR UPDATE SKIP LOCKED
- `calculate_delay()` - с рандомизацией
- `get_random_message(group_id)`
- `mark_task_success()`, `mark_task_failed()`
- `reset_stale_tasks()`

### worker.py
**Async Worker процесс**

```python
class Worker:
    async def run()              # Главный async цикл
    async def _process_task()    # search → open → check → send
```

Exit codes: 0 (OK), 1 (error), 3 (banned - не перезапускать)

### proxy_manager.py
**Управление прокси**

```python
class ProxyManager:
    async def get_proxy_for_profile(profile_id)
    async def rotate_proxy(profile_id)
    async def mark_proxy_unhealthy(proxy_url)
    async def sync_proxies_from_file()
```

### proxy_health.py
**Мониторинг здоровья прокси**

```python
class ProxyHealthMonitor:
    async def check_proxy_health(profile_id)
    async def should_rotate_proxy(profile_id)  # По % chat_not_found
```

### error_handler.py
**Async обработка 4 типов ошибок**

1. `handle_chat_not_found()` → блокировка задачи
2. `handle_account_frozen()` → блокировка профиля, exit(3)
3. `handle_send_restriction()` → failed без блокировки
4. `handle_unexpected_error()` → retry или блокировка

### browser_automation.py
**Playwright + Camoufox**

```python
class BrowserAutomationSimplified:
    async def launch()           # Запуск с fingerprint
    async def close()
```

Особенности:
- Fingerprint через CAMOU_CONFIG_* env vars
- Auto-retry при white page
- Persistent context

### telegram_sender.py
**Автоматизация Telegram Web K**

```python
class TelegramSender:
    async def search_chat(username)
    async def open_chat(element)
    async def check_chat_restrictions()  # join, premium, stars, blocked
    async def send_message(text)
    async def close_popups()
```

### config.py
**Конфигурация**

Dataclasses:
- `LimitsConfig` - max_messages_per_hour, max_cycles, delay_randomness
- `TimeoutsConfig` - search_timeout, send_timeout, page_load_timeout
- `PostgreSQLConfig` - host, port, database, user, password
- `ProxyConfig` - pool_file, thresholds
- `Config` - главный класс

### main.py
**CLI интерфейс**

```python
class WorkerManager:
    def start_workers()
    def stop_workers()
    def _restart_worker()  # Exponential backoff
```

Команды: init, import-chats, import-messages, add-profile, list-profiles, start, status

### profile_manager.py
**Donut Browser профили**

```python
@dataclass
class DonutProfile:
    profile_id, profile_name
    executable_path, fingerprint, proxy
```

### logger.py
**Мультифайловое логирование**

Файлы: main.log, success.log, failed_chats.log, failed_send.log

## База данных (PostgreSQL)

### Подключение
```yaml
host: 81.30.105.134
port: 5432
database: telegram_ras
user: admin
```

### Таблицы

| Таблица | Описание |
|---------|----------|
| `profiles` | Профили Donut (profile_id, is_active, is_blocked, is_logged_out) |
| `tasks` | Задачи/чаты (group_id, chat_username, status, cycles) |
| `task_attempts` | История попыток (task_id, profile_id, run_id, status) |
| `messages` | Шаблоны сообщений (group_id, text, usage_count) |
| `send_log` | Лог отправок (profile_id, chat_username, status) |
| `profile_daily_stats` | Дневная статистика |
| `screenshots` | Метаданные скриншотов |
| `proxy_assignments` | Назначение прокси профилям |

### Views
- `profile_stats` - агрегированная статистика
- `task_progress` - прогресс задач
- `group_stats` - статистика по группам

## Скрипты (scripts/)

| Скрипт | Описание |
|--------|----------|
| `start_automation.py` | Запуск автоматизации (интерактив/CLI) |
| `manage_groups.py` | CRUD для campaign groups |
| `manage_tasks.py` | Управление задачами |
| `profile_stats.py` | Статистика профилей |
| `sync_group_messages.py` | Синхронизация сообщений JSON → БД |
| `migrate_proxies.py` | Импорт прокси из файла в БД |
| `reset_database.py` | Полный сброс БД |
| `clear_database.py` | Очистка данных |

## CLI Команды

```bash
# Запуск
python scripts/start_automation.py <group_id> [--workers N]

# Группы
python scripts/manage_groups.py create|list|show|delete <group_id>
python scripts/manage_groups.py add-profiles <group_id> <profile1> ...
python scripts/manage_groups.py add-messages <group_id> <msg1> ...

# Задачи
python -m src.main import-chats data/chats.txt --group <group_id>
python scripts/manage_tasks.py

# Прокси
python scripts/migrate_proxies.py

# Статистика
python scripts/profile_stats.py
```

## Конфигурация (config.yaml)

```yaml
limits:
  max_messages_per_hour: 25
  max_cycles: 100
  delay_randomness: 0.2
  cycle_delay_minutes: 5

timeouts:
  search_timeout: 20
  send_timeout: 5
  page_load_timeout: 30

database:
  type: "postgresql"
  postgresql:
    host: "81.30.105.134"
    port: 5432
    database: "telegram_ras"

proxy:
  pool_file: "data/proxies.txt"
  chat_not_found_threshold: 40  # % для ротации
```

## Зависимости (requirements.txt)

```
playwright>=1.40.0
pyyaml>=6.0
asyncpg>=0.29.0
psutil>=5.9.0
watchdog>=3.0.0
```

## Рабочий процесс

1. `python scripts/manage_groups.py create my_group`
2. `python scripts/manage_groups.py add-profiles my_group Profile1 Profile2`
3. `python -m src.main import-chats data/chats.txt --group my_group`
4. `python scripts/sync_group_messages.py --all`
5. `python scripts/start_automation.py my_group`
6. Мониторинг: `tail -f logs/main.log`
7. Остановка: Ctrl+C

## Важные заметки

1. **Async везде** - все операции с БД асинхронные
2. **Connection Pool** - asyncpg pool (min=2, max=10)
3. **FOR UPDATE SKIP LOCKED** - атомарный захват задач
4. **make_interval()** - безопасные INTERVAL в SQL (защита от injection)
5. **Proxy rotation** - автоматическая при высоком % chat_not_found
6. **Session-based cycles** - run_id для изоляции сессий

---
**Последнее обновление:** 2024-12-05 (миграция на asyncpg)
