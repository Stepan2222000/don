# CLAUDE.md - Telegram Automation System

> **ВАЖНО:** Этот файл должен динамически обновляться при любых изменениях в структуре проекта, добавлении новых модулей, функций или изменении логики работы. После внесения изменений в код обязательно обновите соответствующие секции этого файла.

## Обзор проекта

Telegram Automation System - это система автоматической рассылки сообщений в Telegram-чаты через web.telegram.org/k с использованием профилей Donut Browser и Playwright автоматизации.

### Ключевые особенности

- **Worker Pool архитектура** - параллельная обработка несколькими профилями
- **Интеграция с Donut Browser** - использование fingerprints и прокси из профилей
- **SQLite с WAL режимом** - надежное хранение с конкурентным доступом
- **Campaign Groups** - группировка задач, профилей и сообщений в кампании
- **Session-based cycles** - отслеживание циклов отправки на уровне сессии (run_id)
- **Auto-restart workers** - автоматический перезапуск упавших воркеров с exponential backoff
- **Обработка 4 типов ошибок** - chat_not_found, account_frozen, send_restrictions, unexpected_errors

## Структура проекта

```
tg-automatizamtion/
├── src/                          # Основные Python модули
│   ├── __init__.py              # Инициализация пакета
│   ├── main.py                  # CLI интерфейс и WorkerManager
│   ├── config.py                # Конфигурация и Campaign Groups
│   ├── database.py              # SQLite операции
│   ├── task_queue.py            # Очередь задач с атомарными операциями
│   ├── worker.py                # Worker процесс
│   ├── browser_automation.py    # Запуск браузеров через Playwright
│   ├── telegram_sender.py       # Автоматизация Telegram Web
│   ├── profile_manager.py       # Управление профилями Donut Browser
│   ├── error_handler.py         # Обработка ошибок
│   └── logger.py                # Мультифайловое логирование
├── scripts/                      # Утилиты и скрипты (основной способ запуска)
│   ├── start_automation.py      # Запуск автоматизации
│   ├── manage_groups.py         # Управление campaign groups
│   ├── manage_tasks.py          # Управление задачами
│   ├── profile_stats.py         # Статистика профилей
│   ├── sync_group_messages.py   # Синхронизация сообщений групп
│   ├── reset_groups.py          # Сброс групп
│   ├── reset_database.py        # Сброс БД
│   ├── clear_database.py        # Очистка БД
│   ├── clear_db_force.py        # Принудительная очистка БД
│   ├── migrate_db.py            # Миграции БД
│   └── interactive_utils.py     # Интерактивные утилиты
├── db/
│   ├── schema.sql               # SQL схема (7 таблиц, 3 views)
│   ├── migrate_add_run_id.sql   # Миграция для run_id
│   └── telegram_automation.db   # SQLite база (создается автоматически)
├── data/
│   ├── groups.json              # Конфигурация campaign groups
│   ├── messages.json            # Шаблоны сообщений (legacy)
│   └── automation.db            # Альтернативная БД
├── docs/
│   ├── REQUIREMENTS.md          # Полная спецификация системы
│   ├── SELECTORS.md             # CSS селекторы Telegram Web
│   ├── GROUPS.md                # Документация по группам
│   └── SESSION_BASED_CYCLES.md  # Документация по session-based cycles
├── logs/                         # Логи (создается автоматически)
│   ├── main.log                 # Основной лог
│   ├── success.log              # Успешные отправки
│   ├── failed_chats.log         # Чаты не найдены
│   ├── failed_send.log          # Ошибки отправки
│   ├── screenshots/             # Скриншоты ошибок
│   └── debug_trash/             # Debug-снапшоты (HTML + PNG)
├── config.yaml                   # Основная конфигурация
├── requirements.txt              # Python зависимости
└── README.md                     # Документация пользователя
```

## CLI Команды

### Основной способ запуска (через scripts/)

```bash
# Запуск автоматизации
python scripts/start_automation.py                      # Интерактивный режим
python scripts/start_automation.py <group_id>           # Запуск группы
python scripts/start_automation.py <group_id> --workers 2

# Управление группами
python scripts/manage_groups.py                         # Интерактивный режим
python scripts/manage_groups.py create <group_id>
python scripts/manage_groups.py list
python scripts/manage_groups.py show <group_id>
python scripts/manage_groups.py delete <group_id>
python scripts/manage_groups.py add-profiles <group_id> <profile1> [<profile2> ...]
python scripts/manage_groups.py add-messages <group_id> <message1> [<message2> ...]
python scripts/manage_groups.py set-setting <group_id> <key> <value>

# Управление задачами
python scripts/manage_tasks.py

# Статистика профилей
python scripts/profile_stats.py

# Сброс/очистка
python scripts/reset_database.py
python scripts/clear_database.py
python scripts/reset_groups.py
```

### Альтернативный способ (через src.main)

```bash
python -m src.main init
python -m src.main import-chats data/chats.txt --group group_1
python -m src.main import-messages data/messages.json --group group_1
python -m src.main add-profile "ProfileName"
python -m src.main list-profiles [--db-only]
python -m src.main start --group group_1 [--workers N] [--all-profiles]
python -m src.main status
```

## Описание модулей

### src/main.py
**CLI интерфейс и управление воркерами**

Классы:
- `WorkerManager` - управление пулом worker-процессов с auto-restart логикой

Функции:
- `cmd_init()` - инициализация БД и конфига
- `cmd_import_chats()` - импорт чатов из файла
- `cmd_import_messages()` - импорт сообщений из JSON
- `cmd_add_profile()` - добавление профилей в автоматизацию
- `cmd_list_profiles()` - список профилей
- `cmd_start()` - запуск автоматизации с указанием группы
- `cmd_status()` - статус очереди
- `cmd_stop()` - остановка

### src/config.py
**Конфигурация и Campaign Groups**

Dataclasses:
- `LimitsConfig` - лимиты (max_messages_per_hour, max_cycles, delay_randomness, cycle_delay_minutes)
- `TimeoutsConfig` - таймауты (search_timeout, send_timeout, page_load_timeout)
- `TelegramConfig` - настройки Telegram (url, headless)
- `RetryConfig` - политика retry (max_attempts, max_attempts_before_block)
- `ScreenshotsConfig` - настройки скриншотов
- `LoggingConfig` - настройки логирования
- `DatabaseConfig` - путь к БД
- `Config` - главный класс конфигурации
- `CampaignGroup` - группа кампании (id, profiles, messages, settings)
- `GroupsData` - контейнер для всех групп

Функции:
- `load_config()` - загрузка config.yaml
- `load_groups()` - загрузка data/groups.json
- `get_group_config()` - получение merged конфига для группы

### src/database.py
**SQLite операции с WAL режимом**

Класс `Database`:
- Thread-local connections для конкурентного доступа
- Транзакции с режимами DEFERRED/IMMEDIATE/EXCLUSIVE
- Операции: profiles, tasks, task_attempts, messages, send_log, screenshots, profile_daily_stats

Ключевые методы:
- `add_profile()`, `get_active_profiles()`, `block_profile()`
- `import_chats()`, `get_task_by_id()`, `block_task()`
- `import_messages()`, `get_active_messages()`
- `log_send()`, `add_screenshot()`
- `get_task_attempts_count_by_run()` - подсчет попыток по run_id
- `update_profile_daily_stats()` - дневная статистика

### src/task_queue.py
**Очередь задач с атомарными операциями**

Класс `TaskQueue`:
- Атомарное получение задач (UPDATE + RETURNING)
- Session-based cycle tracking через run_id
- Fair distribution между профилями

Ключевые методы:
- `get_next_incomplete_task(group_id, profile_id, run_id)` - получение следующей задачи
- `calculate_delay()` - расчет задержки с рандомизацией
- `get_random_message(group_id)` - случайное сообщение из группы
- `mark_task_success()` - отметка успеха
- `mark_task_failed()` - отметка ошибки
- `reset_stale_tasks()` - сброс зависших задач

### src/worker.py
**Worker процесс**

Класс `Worker`:
- Главный цикл обработки задач
- Интеграция с browser_automation и telegram_sender
- Обработка прерываний и cleanup

Методы:
- `run()` - главный цикл: launch → process → delay → repeat
- `_process_task()` - обработка одной задачи: search → open → check_restrictions → send

Exit codes:
- 0 - успешное завершение / graceful shutdown
- 1 - ошибка
- 3 - аккаунт забанен (не перезапускать)

### src/browser_automation.py
**Запуск браузеров через Playwright**

Классы:
- `BrowserAutomation` - полная автоматизация с nodecar
- `BrowserAutomationSimplified` - прямой запуск через Playwright (используется по умолчанию)

Функции:
- `_verify_telegram_loaded()` - проверка загрузки UI
- `_load_telegram_with_retry()` - загрузка с retry при white page

Особенности:
- Fingerprint передается через CAMOU_CONFIG_* env vars
- Автоматический retry при white/blank page
- Persistent context для сохранения сессии

### src/telegram_sender.py
**Автоматизация Telegram Web**

Класс `TelegramSelectors`:
- CSS селекторы для Telegram Web K version
- SEARCH_INPUT, CHAT_ELEMENT, MESSAGE_INPUT, SEND_BUTTON
- Индикаторы ошибок: FROZEN_TEXT, JOIN_BUTTON, PREMIUM_BUTTON, STARS_BUTTON

Класс `TelegramSender`:
- `search_chat()` - поиск чата с retry
- `open_chat()` - открытие чата
- `check_chat_restrictions()` - проверка ограничений (join, premium, stars, blocked)
- `send_message()` - отправка с deep debugging
- `close_popups()` - закрытие popup'ов
- `_check_slow_mode_text()` - проверка Slow Mode
- `_save_debug_snapshot()` - сохранение HTML + PNG для отладки

### src/profile_manager.py
**Управление профилями Donut Browser**

Dataclass `DonutProfile`:
- profile_id, profile_name, browser, version
- Пути: profile_path, metadata_path, browser_data_path
- Camoufox: executable_path, fingerprint, proxy

Класс `ProfileManager`:
- Сканирование `~/Library/Application Support/DonutBrowserDev/profiles/`
- Загрузка metadata.json
- Валидация профилей

Методы:
- `get_all_profiles()` - все профили
- `get_profile_by_id()`, `get_profile_by_name()`
- `validate_profile()` - проверка готовности к автоматизации

### src/error_handler.py
**Обработка 4 типов ошибок**

Класс `ErrorHandler`:
1. `handle_chat_not_found()` - чат не найден → блокировка задачи
2. `handle_account_frozen()` - аккаунт заморожен → блокировка профиля, остановка worker
3. `handle_send_restriction()` - ограничения → failed без блокировки
4. `handle_unexpected_error()` - exception → retry или блокировка при превышении лимита

### src/logger.py
**Мультифайловое логирование**

Класс `TelegramAutomationLogger`:
- main.log - общий лог (console + file)
- success.log - успешные отправки
- failed_chats.log - чаты не найдены
- failed_send.log - ошибки отправки

Методы:
- `info()`, `debug()`, `warning()`, `error()`, `critical()`
- `log_success()`, `log_chat_not_found()`, `log_send_error()`
- `log_worker_start()`, `log_worker_stop()`
- `get_screenshot_path()` - генерация пути для скриншота

## Скрипты (scripts/)

### start_automation.py
Запуск автоматизации для campaign group. Поддерживает интерактивный режим и CLI.

### manage_groups.py
Управление campaign groups: создание, удаление, добавление профилей/сообщений, настройка.

### manage_tasks.py
Управление задачами: просмотр, сброс статусов, очистка.

### profile_stats.py
Просмотр статистики профилей: отправлено сообщений, успешные/неудачные.

### sync_group_messages.py
Синхронизация сообщений между groups.json и базой данных.

### reset_database.py / clear_database.py
Сброс и очистка базы данных.

### interactive_utils.py
Общие утилиты для интерактивного режима скриптов.

## База данных

### Таблицы

1. **profiles** - профили Donut Browser
   - profile_id (UUID), profile_name, is_active, is_blocked
   - messages_sent_current_hour, hour_reset_time, last_message_time

2. **tasks** - задачи (одна на чат)
   - group_id, chat_username, status (pending/in_progress/completed/blocked)
   - total_cycles, completed_cycles, success_count, failed_count
   - is_blocked, block_reason, next_available_at

3. **task_attempts** - история попыток
   - task_id (FK), profile_id, run_id, cycle_number
   - status, message_text, error_type, error_message

4. **messages** - шаблоны сообщений
   - group_id, text, is_active, usage_count

5. **send_log** - общий лог отправок
   - group_id, task_id (FK), profile_id, chat_username
   - message_text, status, error_type, error_details

6. **profile_daily_stats** - дневная статистика профилей
   - profile_id, date, messages_sent, successful_sends, failed_sends

7. **screenshots** - метаданные скриншотов
   - log_id (FK), screenshot_type, file_name, description

### Views

- `profile_stats` - агрегированная статистика по профилям
- `task_progress` - прогресс выполнения задач
- `group_stats` - статистика по группам

## Campaign Groups

Группы определяются в `data/groups.json`:

```json
{
  "groups": [
    {
      "id": "group_1",
      "profiles": ["ProfileName1", "ProfileName2"],
      "messages": ["Сообщение 1", "Сообщение 2"],
      "settings": {
        "limits": {
          "max_messages_per_hour": 20
        }
      }
    }
  ]
}
```

Группа объединяет:
- Профили для рассылки
- Сообщения для отправки
- Переопределенные настройки (merge с config.yaml)

## Session-Based Cycles

Система использует `run_id` для отслеживания циклов в рамках одной сессии:

- Каждый запуск `start_automation.py` генерирует уникальный run_id
- max_cycles считается на уровне сессии, а не глобально
- Позволяет перезапускать рассылку без "памяти" о предыдущих запусках
- Attempts записываются с run_id для точного tracking

## Конфигурация (config.yaml)

```yaml
limits:
  max_messages_per_hour: 30      # Лимит на профиль в час
  max_cycles: 1                  # Циклов на чат за сессию
  delay_randomness: 0.2          # ±20% рандомизация задержки
  cycle_delay_minutes: 20        # Задержка между циклами

timeouts:
  search_timeout: 10             # Поиск чата
  send_timeout: 5                # Отправка
  page_load_timeout: 30          # Загрузка страницы

telegram:
  url: "https://web.telegram.org/k"
  headless: false                # true для headless режима

retry:
  max_attempts_before_block: 3   # Попыток до блокировки задачи

screenshots:
  enabled: true
  on_error: true
  on_warning: false
  on_debug: false
```

## Рабочий процесс

1. **Создание группы**: `python scripts/manage_groups.py create my_group`
2. **Добавление профилей**: `python scripts/manage_groups.py add-profiles my_group Profile1 Profile2`
3. **Добавление сообщений**: через интерактивный режим или groups.json
4. **Импорт чатов**: `python -m src.main import-chats data/chats.txt --group my_group`
5. **Запуск**: `python scripts/start_automation.py my_group`
6. **Мониторинг**: `tail -f logs/main.log`
7. **Остановка**: Ctrl+C

## Важные заметки для разработки

1. **Thread safety**: Используются thread-local connections для SQLite
2. **Atomicity**: UPDATE + RETURNING для атомарного захвата задач
3. **White page detection**: Автоматический retry при пустой странице
4. **Debug snapshots**: HTML + PNG сохраняются в logs/debug_trash/
5. **Slow Mode handling**: Распознавание и reschedule задачи
6. **Auto-restart**: Exponential backoff при падении worker'ов

---

**Последнее обновление:** При внесении изменений обновите соответствующие секции выше.
