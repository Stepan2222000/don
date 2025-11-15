# Telegram Automation System

Автоматическая рассылка сообщений в Telegram-чаты через web.telegram.org/k с использованием профилей Donut Browser и Playwright автоматизации.

## Особенности

- ✅ **Worker Pool архитектура** - параллельная обработка с несколькими профилями
- ✅ **Интеграция с Donut Browser** - использует fingerprints и прокси из существующих профилей
- ✅ **SQLite с WAL режимом** - надежное хранение данных с поддержкой конкурентного доступа
- ✅ **Автоматическая балансировка** - равномерное распределение задач между профилями
- ✅ **Обработка ошибок** - умная обработка 4 типов ошибок с логированием и скриншотами
- ✅ **CLI интерфейс** - удобное управление через командную строку

## Требования

- Python 3.11+
- Donut Browser с созданными профилями
- Профили должны быть авторизованы в Telegram (web.telegram.org/k)

## Установка

### 1. Установка Python зависимостей

```bash
cd /Users/stepanorlov/Desktop/donat/tg-automatizamtion
pip install -r requirements.txt
```

### 2. Установка Playwright браузеров

```bash
playwright install firefox
```

### 3. Инициализация проекта

```bash
python -m src.main init
```

Эта команда:
- Создает базу данных SQLite
- Создает config.yaml (если не существует)
- Подготавливает структуру папок

## Подготовка профилей Donut Browser

### Важно: Авторизация в Telegram

**Перед запуском автоматизации** вы должны авторизовать каждый профиль в Telegram вручную:

1. Откройте Donut Browser UI
2. Запустите профиль (кнопка "Launch")
3. Перейдите на https://web.telegram.org/k
4. Авторизуйтесь (введите номер телефона, код из SMS)
5. Закройте браузер

После этого профиль готов к автоматизации. Сессия Telegram сохранится в профиле.

### Список доступных профилей

```bash
python -m src.main list-profiles
```

Вывод:
```
Name                 ID                                   Browser      Proxy
-------------------------------------------------------------------------------------
AutoProxy1           a1b2c3d4-...                        camoufox     http://...
Test                 e5f6g7h8-...                        camoufox     Not Set
...

Total profiles: 4
```

## Настройка

### 1. Редактирование config.yaml

Откройте `config.yaml` и настройте параметры:

```yaml
limits:
  max_messages_per_hour: 30      # Сообщений в час на профиль
  max_cycles: 1                  # Сколько раз отправить в каждый чат
  delay_randomness: 0.2          # Случайность задержки (±20%)
  cycle_delay_minutes: 20        # Задержка между циклами

timeouts:
  search_timeout: 10             # Таймаут поиска чата
  send_timeout: 5                # Таймаут отправки
  page_load_timeout: 30          # Таймаут загрузки страницы

telegram:
  url: "https://web.telegram.org/k"
  headless: false                # false = видимые окна браузера

screenshots:
  enabled: true                  # Включить скриншоты при ошибках
  on_error: true                 # Скриншоты критических ошибок
  on_warning: false              # Скриншоты предупреждений
```

### 2. Подготовка списка чатов

Создайте или отредактируйте `data/chats.txt`:

```
@vibedevs
@pythonru
@WebDevelopersChat
# Комментарии начинаются с #
@javascriptru
```

### 3. Подготовка сообщений

Создайте или отредактируйте `data/messages.json`:

```json
[
  "Привет! Интересный проект обсуждаете?",
  "Добрый день! Можно присоединиться?",
  "Здравствуйте! Давно следите за темой?"
]
```

## Использование

### Полный цикл работы

#### 1. Импорт чатов

```bash
python -m src.main import-chats data/chats.txt
```

Вывод: `✓ Imported 10 chats successfully`

#### 2. Импорт сообщений

```bash
python -m src.main import-messages data/messages.json
```

Вывод: `✓ Imported 5 messages successfully`

#### 3. Добавление профилей

```bash
python -m src.main add-profile "AutoProxy1" "Test"
```

Вывод:
```
✓ Added profile: AutoProxy1 (a1b2c3d4-...)
✓ Added profile: Test (e5f6g7h8-...)
```

#### 4. Проверка статуса

```bash
python -m src.main status
```

Вывод:
```
============================================================
AUTOMATION STATUS
============================================================

Tasks Overview:
  Total tasks:     10
  Pending:         10 (100.0%)
  In Progress:     0
  Completed:       0 (0.0%)
  Blocked:         0 (0.0%)

Results:
  Total Success:   0
  Total Failed:    0

Active Profiles (2):
  - AutoProxy1: Active
  - Test: Active

============================================================
```

#### 5. Запуск автоматизации

```bash
python -m src.main start
```

Вывод:
```
Starting automation with 2 worker(s)...
Profiles: AutoProxy1, Test

2024-11-15 14:30:00 | INFO | Worker started: AutoProxy1 (a1b2c3d4-...)
2024-11-15 14:30:00 | INFO | Worker started: Test (e5f6g7h8-...)
2024-11-15 14:30:05 | INFO | Launching browser for profile: AutoProxy1
...
2024-11-15 14:30:45 | INFO | Profile: AutoProxy1 | Chat: @vibedevs | Message: "Привет! ..."
...
```

**Остановка:** Нажмите `Ctrl+C` для graceful shutdown всех worker'ов.

#### 6. Ограничение количества worker'ов

```bash
python -m src.main start --workers 1
```

Запустит только 1 worker (первый активный профиль).

### Мониторинг

#### Просмотр логов

Логи создаются автоматически в папке `logs/`:

```bash
# Общий лог
tail -f logs/main.log

# Успешные отправки
tail -f logs/success.log

# Чаты не найдены
tail -f logs/failed_chats.log

# Ошибки отправки
tail -f logs/failed_send.log
```

#### Скриншоты ошибок

Скриншоты сохраняются в:
- `logs/screenshots/errors/` - критические ошибки
- `logs/screenshots/warnings/` - предупреждения
- `logs/screenshots/debug/` - отладочные

## CLI Команды

### init
Инициализация БД и конфигурации.
```bash
python -m src.main init
```

### import-chats
Импорт списка чатов из файла.
```bash
python -m src.main import-chats data/chats.txt
```

### import-messages
Импорт сообщений из JSON файла.
```bash
python -m src.main import-messages data/messages.json
```

### add-profile
Добавить профиль(и) для рассылки.
```bash
python -m src.main add-profile "ProfileName1" "ProfileName2"
```

### list-profiles
Список всех профилей Donut Browser.
```bash
python -m src.main list-profiles

# Показать только профили в базе данных
python -m src.main list-profiles --db-only
```

### start
Запуск автоматизации.
```bash
# Запустить всех активных
python -m src.main start

# Ограничить до N worker'ов
python -m src.main start --workers 3
```

### status
Показать статус выполнения.
```bash
python -m src.main status
```

### stop
Остановка worker'ов (используйте Ctrl+C).
```bash
python -m src.main stop
```

## Архитектура

### Worker Pool модель

```
Main Process (CLI)
    ├── Worker 1 (Profile A) → Browser A → Telegram
    ├── Worker 2 (Profile B) → Browser B → Telegram
    └── Worker 3 (Profile C) → Browser C → Telegram
                ↓
        SQLite Database (WAL mode)
                ↓
          Shared Task Queue
```

Каждый worker:
1. Берет задачу из общей очереди (атомарная операция)
2. Запускает браузер с профилем Donut Browser
3. Выполняет: Поиск → Открытие → Проверка → Отправка
4. Логирует результат
5. Ждет задержку
6. Берет следующую задачу

### Обработка ошибок

Система обрабатывает 4 типа ошибок:

1. **Чат не найден**
   - Действие: Блокирует задачу навсегда
   - Лог: `failed_chats.log`
   - Скриншот: `warnings/`

2. **Аккаунт заморожен**
   - Действие: Блокирует профиль, останавливает worker
   - Лог: `main.log` (ERROR)
   - Скриншот: `errors/`

3. **Нет прав писать**
   - Причины: Нужно вступить / Premium / Заблокирован
   - Действие: Пропускает, пробует в следующем цикле
   - Лог: `failed_send.log`
   - Скриншот: `warnings/`

4. **Сетевые ошибки**
   - Действие: Логирует, продолжает
   - Лог: `main.log` (ERROR)
   - Скриншот: `errors/`

## Troubleshooting

### Ошибка: "Profile not found"

**Решение:** Проверьте имя профиля командой `list-profiles`.

### Ошибка: "Nodecar binary not found"

**Решение:** Убедитесь, что Donut Browser установлен и nodecar binary доступен.
Проверьте путь: `/Users/stepanorlov/Desktop/donat/donutbrowser/src-tauri/binaries/`

### Ошибка: "Fingerprint not configured"

**Решение:** Профиль должен быть создан через Donut Browser UI с настроенным fingerprint.

### Telegram не загружается

**Решение:**
1. Проверьте proxy в профиле
2. Увеличьте `page_load_timeout` в config.yaml
3. Проверьте интернет-соединение

### Чаты не находятся

**Решение:**
1. Проверьте правильность @username в chats.txt
2. Убедитесь, что чат публичный или вы в нем состоите
3. Увеличьте `search_timeout` в config.yaml

## Структура проекта

```
tg-automatizamtion/
├── src/                      # Python модули
│   ├── main.py              # CLI интерфейс
│   ├── config.py            # Конфигурация
│   ├── database.py          # SQLite операции
│   ├── profile_manager.py   # Управление профилями
│   ├── browser_automation.py # Запуск браузеров
│   ├── telegram_sender.py   # Автоматизация Telegram
│   ├── task_queue.py        # Очередь задач
│   ├── worker.py            # Worker процессы
│   ├── error_handler.py     # Обработка ошибок
│   └── logger.py            # Логирование
├── db/
│   ├── schema.sql           # SQL схема (6 таблиц)
│   └── telegram_automation.db # SQLite база (создается автоматически)
├── data/
│   ├── chats.txt            # Список чатов
│   └── messages.json        # Сообщения
├── logs/                    # Логи (создается автоматически)
├── docs/                    # Документация
│   ├── REQUIREMENTS.md      # Полная спецификация
│   └── SELECTORS.md         # Селекторы Telegram Web
├── htmls/                   # HTML примеры Telegram Web
├── config.yaml              # Конфигурация
└── README.md                # Этот файл
```

## Лицензия

Данная система предназначена только для легального использования в соответствии с Terms of Service Telegram. Автор не несет ответственности за неправомерное использование.

## Поддержка

Для вопросов и issues обращайтесь к документации:
- [REQUIREMENTS.md](docs/REQUIREMENTS.md) - Полная спецификация
- [SELECTORS.md](docs/SELECTORS.md) - Селекторы и примеры автоматизации
