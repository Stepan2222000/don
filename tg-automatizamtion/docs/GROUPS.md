# Campaign Groups - Руководство пользователя

## Обзор

Система Campaign Groups позволяет создавать множественные изолированные рассылки с разными настройками, профилями и целевыми чатами.

### Основные возможности

- **Изоляция**: Каждая группа имеет свои задачи (чаты), сообщения и настройки
- **Гибкие настройки**: Настройки группы переопределяют глобальные настройки из `config.yaml`
- **Общие профили**: Один профиль может работать с несколькими группами
- **Статистика**: Отслеживание отправленных сообщений по профилям за день/период
- **Скрипты управления**: Удобные скрипты для управления группами и задачами

## Архитектура

### Структура группы (JSON)

Группы хранятся в файле `data/groups.json`:

```json
{
  "groups": [
    {
      "id": "my_campaign_1",
      "profiles": [],
      "messages": [],
      "settings": {}
    }
  ]
}
```

#### Поля группы:

- **id**: Уникальный идентификатор группы (строка)
- **profiles**: Массив UUID профилей Donut Browser для этой группы
- **messages**: Массив текстов сообщений (опционально, можно загружать через БД)
- **settings**: Персональные настройки группы (переопределяют `config.yaml`)

### Настройки группы

Все настройки опциональны. Если не указаны - используются значения из `config.yaml`.

Пример полного набора настроек:

```json
{
  "id": "aggressive_campaign",
  "profiles": ["uuid-1", "uuid-2"],
  "messages": ["Привет!", "Добрый день!"],
  "settings": {
    "limits": {
      "max_messages_per_hour": 50,
      "max_cycles": 2,
      "delay_randomness": 0.3
    },
    "timeouts": {
      "search_timeout": 15,
      "send_timeout": 10
    },
    "telegram": {
      "headless": true
    }
  }
}
```

## Использование

### 1. Создание группы

```bash
python scripts/manage_groups.py create my_campaign_1
```

### 2. Настройка группы

#### Добавление профилей

```bash
python scripts/manage_groups.py add-profiles my_campaign_1 "Profile 1" "Profile 2"
```

#### Изменение настроек

```bash
# Установить лимит сообщений в час
python scripts/manage_groups.py set-setting my_campaign_1 limits.max_messages_per_hour 50

# Включить headless режим
python scripts/manage_groups.py set-setting my_campaign_1 telegram.headless true
```

#### Добавление сообщений (опционально)

```bash
python scripts/manage_groups.py add-messages my_campaign_1 "Текст 1" "Текст 2"
```

### 3. Загрузка чатов

Создайте файл `chats.txt` с целевыми чатами (по одному на строку):

```
@username1
@username2
@username3
```

Загрузите чаты в группу:

```bash
python scripts/manage_tasks.py load my_campaign_1 chats.txt
```

### 4. Просмотр информации

#### Список всех групп

```bash
python scripts/manage_groups.py list
```

#### Детали группы

```bash
python scripts/manage_groups.py show my_campaign_1
```

#### Статистика группы

```bash
python scripts/manage_tasks.py stats my_campaign_1
```

### 5. Запуск рассылки

**ВАЖНО:** Функционал запуска рассылки еще не реализован в `main.py`.

Планируемое использование:

```bash
# Запуск с указанием группы
python -m src.main start --group my_campaign_1

# Запуск с использованием всех доступных профилей (не только из группы)
python -m src.main start --group my_campaign_1 --all-profiles
```

### 6. Управление задачами

#### Очистка задач группы

```bash
python scripts/manage_tasks.py clear my_campaign_1
```

#### Замена задач

```bash
# Сначала очистить
python scripts/manage_tasks.py clear my_campaign_1

# Загрузить новые
python scripts/manage_tasks.py load my_campaign_1 new_chats.txt
```

### 7. Статистика профилей

#### Все профили за сегодня

```bash
python scripts/profile_stats.py all
```

#### Все профили за последние 7 дней

```bash
python scripts/profile_stats.py all --days 7
```

#### Конкретный профиль

```bash
python scripts/profile_stats.py show "Profile 1" --days 30
```

## Примеры использования

### Пример 1: Простая рассылка

```bash
# 1. Создать группу
python scripts/manage_groups.py create simple_campaign

# 2. Добавить профили
python scripts/manage_groups.py add-profiles simple_campaign "Profile 1"

# 3. Загрузить чаты
echo "@chat1\n@chat2\n@chat3" > chats.txt
python scripts/manage_tasks.py load simple_campaign chats.txt

# 4. Запустить
python -m src.main start --group simple_campaign
```

### Пример 2: Агрессивная рассылка с кастомными настройками

```bash
# 1. Создать группу
python scripts/manage_groups.py create aggressive_campaign

# 2. Настроить лимиты
python scripts/manage_groups.py set-setting aggressive_campaign limits.max_messages_per_hour 100
python scripts/manage_groups.py set-setting aggressive_campaign limits.max_cycles 3
python scripts/manage_groups.py set-setting aggressive_campaign telegram.headless true

# 3. Добавить несколько профилей
python scripts/manage_groups.py add-profiles aggressive_campaign "Profile 1" "Profile 2" "Profile 3"

# 4. Загрузить большой список чатов
python scripts/manage_tasks.py load aggressive_campaign huge_list.txt

# 5. Запустить
python -m src.main start --group aggressive_campaign
```

### Пример 3: Тестовая рассылка с параметром --all-profiles

```bash
# Использовать ВСЕ доступные профили, а не только те что в группе
python -m src.main start --group test_campaign --all-profiles
```

## База данных

### Новые таблицы

- **profile_daily_stats**: Статистика отправленных сообщений по профилям за день

### Модифицированные таблицы

- **tasks**: Добавлено поле `group_id`
- **messages**: Добавлено поле `group_id`
- **send_log**: Добавлено поле `group_id`

### Новые views

- **group_stats**: Статистика по группам

## Ограничения и известные проблемы

1. **worker.py и main.py не обновлены** - Запуск рассылки с группами еще не реализован
2. **Миграция старых данных** - Если в БД есть старые задачи без `group_id`, они не будут работать
3. **Профили в JSON** - Храним UUID профилей, а не имена (UUID можно узнать через `manage_groups.py add-profiles`)

## Следующие шаги для завершения реализации

1. Модифицировать [worker.py](../src/worker.py) для приема `group_id`
2. Модифицировать [main.py](../src/main.py) для поддержки `--group` параметра
3. Обновить документацию по запуску рассылок

## Техническая информация

### Приоритет настроек

1. **Настройки группы** (в `data/groups.json`)
2. **Глобальные настройки** (в `config.yaml`)

При запуске рассылки система объединяет настройки группы с глобальными, при этом настройки группы имеют приоритет.

### Изоляция данных

- Каждая группа имеет свои задачи (чаты) в БД
- Каждая группа имеет свои сообщения (если загружены через JSON или БД)
- Профили могут работать с несколькими группами одновременно
- Лимиты (например, 30 сообщений в час) применяются к профилю глобально, а не отдельно для каждой группы

### Статистика

Система отслеживает:
- Сообщения отправленные каждым профилем за день (таблица `profile_daily_stats`)
- Успешные и неудачные отправки
- Общую статистику по группам (view `group_stats`)
