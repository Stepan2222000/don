# Требования к системе автоматической рассылки в Telegram

**Дата:** 2024-11-15
**Проект:** Telegram Automation System
**Папка:** `/Users/stepanorlov/Desktop/donat/tg-automatizamtion/`

---

## 🎯 Глобальная цель

Создать систему автоматической рассылки сообщений в Telegram-чаты через веб-интерфейс `web.telegram.org/k`, используя браузерную автоматизацию (Playwright + Camoufox) и существующие профили Donut Browser.

---

## 📋 Основные требования

### 1. Архитектура и расположение

- **Папка проекта:** `/Users/stepanorlov/Desktop/donat/tg-automatizamtion/`
- **База данных:** SQLite (один файл БД в папке проекта)
- **Интеграция:** Использовать существующие профили из `~/Library/Application Support/DonutBrowserDev/profiles/`
- **Интерфейс:** CLI (command line interface)
- **Язык программирования:** Python
- **Браузер:** Camoufox через Playwright
- **Telegram версия:** web.telegram.org/k

### 2. Режим работы

- **Headless:** `false` (видимые окна браузера)
- **Параллельная обработка:** Да (несколько профилей работают одновременно)
- **Автоматизация:** Полная (без участия пользователя после запуска)

---

## 🏗️ Система параллельной работы профилей

### Концепция

Система работает по модели **Worker Pool**:

```
Main Process (CLI)
    ├── Worker Process 1 (Profile A) → Browser Instance A → Telegram
    ├── Worker Process 2 (Profile B) → Browser Instance B → Telegram
    ├── Worker Process 3 (Profile C) → Browser Instance C → Telegram
    └── ...
                ↓
        Shared SQLite Database (WAL mode)
                ↓
          Common Task Queue
```

### Принципы работы

1. **Пул профилей:**
   - Пользователь выбирает профили Donut Browser для участия в рассылке
   - Каждый профиль работает как независимый воркер (worker process)
   - Все профили имеют одинаковые настройки (лимиты, задержки)

2. **Общая очередь задач:**
   - Все задачи хранятся в SQLite БД
   - Воркеры берут задачи из общей очереди (атомарные операции)
   - Кто первый взял задачу - тот и обрабатывает

3. **Балансировка нагрузки:**
   - Задачи распределяются автоматически
   - Каждый воркер работает в своем темпе (на основе лимитов)

### Пример работы

```
Время | Профиль A              | Профиль B              | Профиль C
------|------------------------|------------------------|------------------------
12:00 | Берет @chat1           | Берет @chat2           | Берет @chat3
12:01 | Отправляет сообщение   | Отправляет сообщение   | Отправляет сообщение
12:03 | Ожидание (delay)       | Ожидание (delay)       | Ожидание (delay)
12:05 | Берет @chat4           | Берет @chat5           | Берет @chat6
...
```

---

## 🗄️ База данных SQLite

### Общая информация

- **Файл:** `db/telegram_automation.db`
- **Режим:** WAL (Write-Ahead Logging) для улучшенной конкуренции
- **Кодировка:** UTF-8

### Схема БД (финальная версия)

#### Таблица: `profiles`

Профили Donut Browser, участвующие в рассылке.

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT UNIQUE NOT NULL,           -- UUID профиля Donut Browser
    profile_name TEXT NOT NULL,                -- Название профиля
    is_active BOOLEAN DEFAULT 1,               -- Участвует ли в рассылке
    is_blocked BOOLEAN DEFAULT 0,              -- Заблокирован ли Telegram в профиле
    messages_sent_current_hour INTEGER DEFAULT 0,
    hour_reset_time TIMESTAMP,                 -- Время сброса счетчика
    last_message_time TIMESTAMP,               -- Время последней отправки
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Таблица: `tasks`

**ВАЖНО:** Задача = работа с одним чатом (одна запись на чат).
Задача накапливает статистику по всем попыткам отправки.

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_username TEXT UNIQUE NOT NULL,        -- @username чата
    status TEXT DEFAULT 'pending',             -- pending/in_progress/completed/blocked
    assigned_profile_id TEXT,                  -- Текущий обработчик (NULL если свободна)

    -- Прогресс
    total_cycles INTEGER DEFAULT 1,            -- Сколько циклов нужно (из конфига)
    completed_cycles INTEGER DEFAULT 0,        -- Сколько циклов выполнено

    -- Статистика
    success_count INTEGER DEFAULT 0,           -- Успешных отправок
    failed_count INTEGER DEFAULT 0,            -- Неудачных попыток

    -- Флаги
    is_blocked BOOLEAN DEFAULT 0,              -- Навсегда заблокирована
    block_reason TEXT,                         -- Причина блокировки

    -- Времена
    last_attempt_at TIMESTAMP,                 -- Последняя попытка
    next_available_at TIMESTAMP,               -- Когда можно снова (для задержек)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_next_available ON tasks(next_available_at);
CREATE INDEX idx_tasks_is_blocked ON tasks(is_blocked);
```

**Пример данных:**
```
| chat_username | status      | total_cycles | completed_cycles | success | failed |
|---------------|-------------|--------------|------------------|---------|--------|
| @chat1        | completed   | 3            | 3                | 3       | 0      |
| @chat2        | in_progress | 3            | 2                | 2       | 0      |
| @chat3        | pending     | 3            | 1                | 0       | 1      |
| @chat4        | blocked     | 3            | 0                | 0       | 1      |
```

#### Таблица: `task_attempts`

История всех попыток отправки (детали каждой отправки).

```sql
CREATE TABLE task_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,                  -- FK -> tasks.id
    profile_id TEXT NOT NULL,                  -- Кто отправлял
    cycle_number INTEGER NOT NULL,             -- Номер цикла (1, 2, 3...)
    status TEXT NOT NULL,                      -- success/failed
    message_text TEXT,                         -- Отправленное сообщение
    error_type TEXT,                           -- chat_not_found/send_error/blocked/etc
    error_message TEXT,                        -- Детали ошибки
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX idx_attempts_task_id ON task_attempts(task_id);
CREATE INDEX idx_attempts_status ON task_attempts(status);
CREATE INDEX idx_attempts_timestamp ON task_attempts(timestamp);
```

#### Таблица: `messages`

Шаблоны сообщений для рассылки.

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,                        -- Текст сообщения
    is_active BOOLEAN DEFAULT 1,               -- Используется ли в рассылке
    usage_count INTEGER DEFAULT 0,             -- Сколько раз использовано
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Таблица: `send_log`

Общий лог всех отправок (для быстрого поиска и аналитики).

```sql
CREATE TABLE send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,                           -- FK -> tasks.id (NULL если задача удалена)
    profile_id TEXT NOT NULL,
    chat_username TEXT NOT NULL,
    message_text TEXT,
    status TEXT NOT NULL,                      -- success/failed
    error_type TEXT,                           -- chat_not_found/send_error/blocked/etc
    error_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE INDEX idx_send_log_status ON send_log(status);
CREATE INDEX idx_send_log_timestamp ON send_log(timestamp);
CREATE INDEX idx_send_log_chat ON send_log(chat_username);
```

#### Таблица: `screenshots`

Скриншоты при ошибках и для отладки.

```sql
CREATE TABLE screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER,                            -- FK -> send_log.id (NULL для отладочных)
    screenshot_type TEXT NOT NULL,             -- error/warning/debug
    file_name TEXT NOT NULL,                   -- Имя файла
    description TEXT,                          -- Описание
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (log_id) REFERENCES send_log(id) ON DELETE CASCADE
);

CREATE INDEX idx_screenshots_log_id ON screenshots(log_id);
CREATE INDEX idx_screenshots_type ON screenshots(screenshot_type);
CREATE INDEX idx_screenshots_created ON screenshots(created_at);
```

**Путь к файлу формируется:** `logs/screenshots/{screenshot_type}/{file_name}`

---

## 📁 Структура проекта

```
tg-automatizamtion/
├── README.md                          # Общее описание проекта
├── requirements.txt                   # Python зависимости
├── config.yaml                        # Конфигурация
├── .env.example                       # Пример переменных окружения
├── .gitignore
│
├── db/
│   ├── schema.sql                     # SQL схема БД
│   ├── migrations/                    # Миграции (на будущее)
│   └── telegram_automation.db         # SQLite база (создается автоматически)
│
├── src/
│   ├── __init__.py
│   ├── main.py                        # CLI entry point
│   ├── config.py                      # Загрузка конфигурации
│   ├── database.py                    # Работа с SQLite
│   ├── profile_manager.py             # Управление профилями Donut Browser
│   ├── browser_automation.py          # Playwright автоматизация
│   ├── telegram_sender.py             # Логика отправки сообщений
│   ├── task_queue.py                  # Очередь задач
│   ├── worker.py                      # Воркер для параллельной обработки
│   ├── error_handler.py               # Обработка ошибок
│   └── logger.py                      # Система логирования
│
├── data/
│   ├── chats.txt                      # Список чатов (@username по строке)
│   └── messages.json                  # Массив сообщений
│
├── logs/                              # Логи (создается автоматически)
│   ├── main.log
│   ├── success.log
│   ├── failed_chats.log
│   ├── failed_send.log
│   └── screenshots/                   # Скриншоты ошибок
│       ├── errors/                    # Критические ошибки
│       ├── warnings/                  # Предупреждения
│       └── debug/                     # Отладочные
│
├── htmls/                             # HTML примеры (уже существует)
│   ├── main.html
│   ├── search.html
│   └── chat.html
│
└── docs/                              # Документация
    ├── REQUIREMENTS.md                # Этот файл
    ├── SELECTORS.md                   # Селекторы Telegram Web
    └── ARCHITECTURE.md                # Детальная архитектура (TODO)
```

---

## ⚙️ Конфигурация

### Файл: `config.yaml`

```yaml
# Лимиты и ограничения
limits:
  max_messages_per_hour: 30            # Сообщений в час на профиль
  max_cycles: 1                        # Количество циклов (проходов по всем чатам)
  delay_randomness: 0.2                # ±20% к рассчитанной задержке
  cycle_delay_minutes: 20              # Задержка между циклами (минуты)

# Таймауты
timeouts:
  search_timeout: 10                   # Таймаут поиска чата (секунды)
  send_timeout: 5                      # Таймаут отправки сообщения
  page_load_timeout: 30                # Таймаут загрузки страницы

# Telegram
telegram:
  url: "https://web.telegram.org/k"
  headless: false                      # Видимые окна браузера

# Повторные попытки
retry:
  enabled: false                       # Повторять ли неудачные попытки
  max_attempts: 3                      # Максимум попыток
  delay_between_retries: 60            # Задержка между попытками (секунды)

# Скриншоты
screenshots:
  enabled: true                        # Включить/выключить скриншоты
  on_error: true                       # Скриншоты при ошибках
  on_warning: false                    # Скриншоты при предупреждениях (чат не найден)
  on_debug: false                      # Отладочные скриншоты
  full_page: true                      # Скриншот всей страницы
  quality: 80                          # Качество (0-100)
  format: "png"                        # png/jpeg
  max_age_days: 30                     # Удалять скриншоты старше N дней

# Логирование
logging:
  level: "INFO"                        # DEBUG/INFO/WARNING/ERROR
  format: "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

# База данных
database:
  path: "db/telegram_automation.db"
  wal_mode: true                       # Использовать WAL режим
```

---

## 🔄 Алгоритм работы

### Инициализация

1. Загрузка конфигурации из `config.yaml`
2. Подключение к SQLite БД (создание если не существует)
3. Загрузка списка чатов из `data/chats.txt`
4. Загрузка сообщений из `data/messages.json`
5. Импорт данных в БД (если нужно)
6. Выбор профилей для рассылки

### Основной цикл работы воркера

```python
# Инициализация
browser = open_browser_with_profile(profile_id)
navigate_to_telegram(browser)

while True:
    # 1. Взять задачу из БД (атомарная операция)
    # Берем задачу где completed_cycles < total_cycles
    task = get_next_incomplete_task(profile_id)

    if task is None:
        # Нет доступных задач
        logger.info("No more tasks available")
        break

    # 2. Задача взята, статус = 'in_progress', assigned_profile_id = profile_id

    try:
        # 3. Найти чат
        chat_found = search_chat(browser, task.chat_username)

        if not chat_found:
            # Чат не найден
            handle_chat_not_found(task, profile_id)
            # Помечаем задачу как заблокированную
            block_task(task.id, reason="chat_not_found")
            continue

        # 4. Открыть чат
        open_chat(browser, task.chat_username)

        # 5. Проверить доступность отправки
        restrictions = check_chat_restrictions(browser)

        if restrictions['account_frozen']:
            # Аккаунт заморожен - блокируем профиль
            block_profile(profile_id)
            logger.error(f"Profile {profile_id} is frozen by Telegram")
            save_screenshot(browser, 'error', 'account_frozen')
            break  # Выходим из цикла, воркер останавливается

        if not restrictions['can_send']:
            # Нет прав на отправку (нужно вступить, нужен Premium, и т.д.)
            handle_send_restriction(task, profile_id, restrictions['reason'])
            # Записываем попытку как failed
            add_task_attempt(
                task_id=task.id,
                profile_id=profile_id,
                cycle_number=task.completed_cycles + 1,
                status='failed',
                error_type=restrictions['reason']
            )
            # Увеличиваем счетчик неудач
            increment_task_failed_count(task.id)
            increment_completed_cycles(task.id)
            continue

        # 6. Выбрать случайное сообщение
        message = get_random_message()

        # 7. Отправить сообщение
        send_message(browser, message)

        # 8. Записать успешную попытку
        add_task_attempt(
            task_id=task.id,
            profile_id=profile_id,
            cycle_number=task.completed_cycles + 1,
            status='success',
            message_text=message
        )

        # 9. Обновить статистику задачи
        increment_task_success_count(task.id)
        increment_completed_cycles(task.id)

        # 10. Логировать успех
        log_success(profile_id, task.chat_username, message)

        # 11. Проверить завершена ли задача
        if task.completed_cycles + 1 >= task.total_cycles:
            mark_task_completed(task.id)
            logger.info(f"Task {task.chat_username} completed")
        else:
            # Установить next_available_at для задержки
            set_task_next_available(task.id, delay_seconds)

        # 12. Рассчитать задержку
        delay = calculate_delay(
            max_messages_per_hour=config.max_messages_per_hour,
            randomness=config.delay_randomness
        )

        # 13. Обновить счетчики профиля
        update_profile_stats(profile_id)

        # 14. Подождать
        logger.info(f"Waiting {delay} seconds...")
        sleep(delay)

    except Exception as e:
        # Неожиданная ошибка
        logger.error(f"Unexpected error: {e}")

        # Сохранить скриншот
        save_screenshot(browser, 'error', f'unexpected_error_{task.chat_username}')

        # Записать неудачную попытку
        add_task_attempt(
            task_id=task.id,
            profile_id=profile_id,
            cycle_number=task.completed_cycles + 1,
            status='failed',
            error_type='exception',
            error_message=str(e)
        )

        # Увеличить счетчик неудач
        increment_task_failed_count(task.id)
        increment_completed_cycles(task.id)

# Завершение работы воркера
close_browser(browser)
logger.info(f"Worker {profile_id} finished")
```

### Функция взятия задачи (атомарная)

```python
def get_next_incomplete_task(profile_id: str):
    """
    Атомарно взять следующую незавершенную задачу
    """
    with db.transaction():
        # UPDATE + RETURNING для атомарности
        task = db.execute("""
            UPDATE tasks
            SET
                status = 'in_progress',
                assigned_profile_id = :profile_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id FROM tasks
                WHERE
                    is_blocked = 0
                    AND completed_cycles < total_cycles
                    AND (next_available_at IS NULL OR next_available_at <= CURRENT_TIMESTAMP)
                    AND (status = 'pending' OR (status = 'in_progress' AND assigned_profile_id = :profile_id))
                ORDER BY
                    last_attempt_at ASC NULLS FIRST,  -- Приоритет тем, что давно не обрабатывались
                    completed_cycles ASC               -- Затем тем, у кого меньше выполнено
                LIMIT 1
            )
            RETURNING *
        """, profile_id=profile_id).fetchone()

        return task
```

### Завершение работы

- Graceful shutdown при получении сигнала (Ctrl+C)
- Сохранение состояния в БД
- Закрытие браузеров
- Финальный отчет

---

## 🚨 Обработка ошибок

### Случай 1: Чат не найден

**Признаки:**
- При поиске появляется "No results"
- Элемент `.chatlist` пустой или нет элементов `.chatlist-chat`

**Действия:**
1. Сохранить скриншот страницы поиска
2. Логировать в `failed_chats.log`:
   ```
   2024-11-15 12:57:46 | Profile: profile_name | Chat: @nonexistent | Error: Chat not found
   ```
3. Записать попытку в `task_attempts`:
   ```sql
   INSERT INTO task_attempts (task_id, profile_id, cycle_number, status, error_type)
   VALUES (task_id, profile_id, cycle + 1, 'failed', 'chat_not_found')
   ```
4. Обновить задачу:
   - `tasks.is_blocked = true`
   - `tasks.block_reason = 'chat_not_found'`
   - `tasks.status = 'blocked'`
   - `tasks.failed_count += 1`
5. Перейти к следующей задаче (эта больше не будет браться воркерами)

### Случай 2: Профиль заблокирован Telegram

**Признаки:**
- Сообщение "Your Account is Frozen" (`.chat-input-frozen-text`)
- Другие индикаторы блокировки

**Действия:**
1. Сохранить скриншот с сообщением о блокировке
2. Логировать в `main.log`:
   ```
   2024-11-15 12:57:46 | ERROR | Profile profile_name is blocked by Telegram
   ```
3. Обновить в БД:
   - `profiles.is_blocked = true`
   - `profiles.is_active = false`
4. Записать в `send_log` с `error_type = 'account_frozen'`
5. Остановить этот воркер (break из цикла)
6. Другие воркеры продолжают работу

### Случай 3: Нет прав писать в чат

**Признаки:**
- Кнопка "JOIN" видима (`.chat-input-control-button` с текстом "JOIN")
- Сообщение "Only Premium users can message..."
- Кнопка "Unblock"

**Действия:**
1. Сохранить скриншот (warning level)
2. Логировать в `failed_send.log`:
   ```
   2024-11-15 12:57:46 | Profile: profile_name | Chat: @premium_only | Error: Cannot send (need to join/premium required)
   ```
3. Записать попытку в `task_attempts`:
   - `status = 'failed'`
   - `error_type` = 'need_to_join' / 'premium_required' / 'user_blocked'
4. Обновить задачу:
   - `tasks.failed_count += 1`
   - `tasks.completed_cycles += 1`
5. Если это последний цикл → `tasks.status = 'completed'`
6. Перейти к следующей задаче

### Случай 4: Сетевые ошибки

**Признаки:**
- Timeout при загрузке страницы
- Элементы не появляются
- Playwright выбрасывает исключения

**Действия:**
1. Логировать ошибку
2. Retry (если включено в конфиге)
3. Если превышено количество попыток → пометить задачу как failed
4. Продолжить работу

---

## 📊 Система логирования

### Формат логов

**main.log** (общий лог):
```
2024-11-15 12:57:46 | INFO | Application started
2024-11-15 12:57:47 | INFO | Loaded 5 profiles
2024-11-15 12:57:48 | INFO | Worker started: profile_name (profile_id)
2024-11-15 12:58:00 | ERROR | Worker profile_name failed: Connection timeout
```

**success.log** (успешные отправки):
```
2024-11-15 12:57:46 | Profile: profile_name | Chat: @vibedevs | Message: "Текст сообщения"
```

**failed_chats.log** (не найденные чаты):
```
2024-11-15 12:57:46 | Profile: profile_name | Chat: @nonexistent | Error: Chat not found
```

**failed_send.log** (ошибки отправки):
```
2024-11-15 12:57:46 | Profile: profile_name | Chat: @somechat | Error: Cannot send - need to join
```

---

## 🎮 CLI Интерфейс

### Команды (предварительно)

```bash
# Инициализация БД и структуры
python -m src.main init

# Импорт чатов из файла
python -m src.main import-chats data/chats.txt

# Импорт сообщений из файла
python -m src.main import-messages data/messages.json

# Добавить профиль для рассылки
python -m src.main add-profile <profile_id>

# Список профилей
python -m src.main list-profiles

# Запуск рассылки (N воркеров)
python -m src.main start --workers 3

# Статус выполнения
python -m src.main status

# Остановить все воркеры
python -m src.main stop
```

---

## ✅ Финальные решения по архитектуре

### 1. Логика циклов

**Цикл = один проход по всем чатам**

Если `max_cycles = 3` и 100 чатов:
```
Цикл 1: Отправить во все 100 чатов (каждый чат получает 1 сообщение)
  └─ Задержка 20 минут
Цикл 2: Снова отправить во все 100 чатов (каждый чат получает еще 1 сообщение)
  └─ Задержка 20 минут
Цикл 3: Снова отправить во все 100 чатов (каждый чат получает еще 1 сообщение)
  └─ Завершение
```

**Итого:** Каждый чат получает `max_cycles` сообщений.

**Задержка между циклами:** 20 минут (настраивается в конфиге)

### 2. Балансировка отправок

**Двойная балансировка (A + B одновременно):**

1. **По чатам (A):** В каждый чат отправляется одинаковое количество сообщений
   - Приоритет отдается чатам с меньшим `completed_cycles`
   - Результат: все чаты проходят циклы примерно одновременно

2. **По профилям (B):** Между профилями равномерная нагрузка
   - Воркеры берут задачи из общей очереди
   - Нет привязки чатов к конкретным профилям
   - Результат: профили отправляют примерно одинаковое количество сообщений

**Реализация:**
```python
# В SQL запросе get_next_incomplete_task
ORDER BY
    completed_cycles ASC,        # Сначала те, у кого меньше циклов выполнено
    last_attempt_at ASC NULLS FIRST  # Затем давно не обрабатывались
```

### 3. Выбор сообщений

**Полностью случайный выбор:**
```python
import random

def get_random_message():
    messages = db.get_active_messages()
    return random.choice(messages)
```

**Возможные результаты:**
- @chat1 → "Привет!"
- @chat2 → "Привет!" (может повториться)
- @chat3 → "Здравствуйте!"
- @chat4 → "Привет!" (может повториться несколько раз)

Никакой логики чередования - полный рандом каждый раз.

### 4. Запуск профилей

**Используем существующую инфраструктуру (через nodecar):**

```python
# Интеграция с существующим launch_profile.py
from pathlib import Path
import subprocess
import sys

# Путь к скрипту launch_profile
LAUNCH_SCRIPT = Path(__file__).parent.parent / "comander" / "launch_profile.py"

def launch_profile(profile_id: str):
    """Запустить профиль через nodecar"""
    process = subprocess.Popen(
        [sys.executable, str(LAUNCH_SCRIPT), "--profile-id", profile_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    return process
```

**Преимущества:**
- ✅ Уже работающее решение
- ✅ Меньше ошибок
- ✅ Использует проверенный механизм nodecar
- ✅ Поддержка всех функций профилей (прокси, fingerprint, и т.д.)

### 5. Авторизация в Telegram

**Профили уже авторизованы вручную.**

Перед запуском рассылки пользователь должен:
1. Открыть профиль через Donut Browser UI
2. Зайти на web.telegram.org/k
3. Авторизоваться (если не авторизован)
4. Закрыть профиль

После этого профиль готов к автоматической рассылке.

### 6. Архитектура процессов

**Используем asyncio + subprocess с автоматическим перезапуском:**

```python
import asyncio
import subprocess

class WorkerManager:
    def __init__(self, profile_ids):
        self.profile_ids = profile_ids
        self.workers = {}  # profile_id -> Process

    async def start_worker(self, profile_id):
        """Запустить воркер для профиля"""
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "src.worker",
            "--profile-id", profile_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self.workers[profile_id] = process

        # Мониторинг воркера
        asyncio.create_task(self.monitor_worker(profile_id, process))

    async def monitor_worker(self, profile_id, process):
        """Мониторить воркер и перезапускать при падении"""
        returncode = await process.wait()

        if returncode != 0:
            logger.error(f"Worker {profile_id} crashed with code {returncode}")

            # Подождать немного перед перезапуском
            await asyncio.sleep(5)

            # Перезапустить воркер
            logger.info(f"Restarting worker {profile_id}...")
            await self.start_worker(profile_id)
        else:
            logger.info(f"Worker {profile_id} finished normally")

    async def start_all(self):
        """Запустить всех воркеров"""
        tasks = [self.start_worker(pid) for pid in self.profile_ids]
        await asyncio.gather(*tasks)
```

**Ключевые особенности:**
- ✅ **Изолированные процессы:** Каждый воркер = отдельный subprocess
- ✅ **Независимость:** Падение одного воркера не влияет на другие
- ✅ **Автоперезапуск:** Если воркер упал - автоматически перезапускается через 5 секунд
- ✅ **Мониторинг:** Main process следит за всеми воркерами
- ✅ **Graceful shutdown:** Ctrl+C останавливает всех воркеров корректно

### 7. Мониторинг и управление

**Реализованные функции:**

1. **Graceful shutdown:** Да, по Ctrl+C
2. **Команда status:** Да, показывает прогресс
3. **Автоостановка:** Нет, воркеры работают пока есть задачи или не получен сигнал остановки

---

## 📝 Следующие шаги

1. **Ответить на уточняющие вопросы**
2. **Финализировать схему БД**
3. **Создать детальную архитектуру** (ARCHITECTURE.md)
4. **Разработать SQL схему** (db/schema.sql)
5. **Начать реализацию модулей**

---

**Статус:** 🎉 Полностью спроектировано и готово к реализации
**Версия документа:** 3.0 (FINAL)
**Последнее обновление:** 2024-11-15

---

## 📌 Ключевые решения (финальные)

1. **Архитектура задач:** Одна задача на чат, накопление статистики по всем циклам
2. **Циклы:** Цикл = проход по всем чатам; задержка между циклами = 20 минут
3. **Балансировка:** Двойная (по чатам + по профилям одновременно)
4. **Выбор сообщений:** Полностью случайный
5. **Запуск профилей:** Через nodecar (существующая инфраструктура)
6. **Авторизация:** Профили уже авторизованы вручную
7. **Процессы:** asyncio + subprocess с автоматическим перезапуском упавших воркеров
8. **Скриншоты:** Отдельная таблица `screenshots` с типами (error/warning/debug)
9. **БД:** SQLite в WAL режиме для параллельной работы
