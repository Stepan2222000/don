# Миграция на Camoufox headless="virtual"

> Документ создан: 2024-12-24
> Статус: Планирование

## Оглавление

1. [Текущая ситуация](#текущая-ситуация)
2. [Проблема](#проблема)
3. [Решение](#решение)
4. [Исследование и анализ](#исследование-и-анализ)
5. [Вопросы и ответы](#вопросы-и-ответы)
6. [План реализации](#план-реализации)
7. [Файлы для изменения](#файлы-для-изменения)
8. [Источники](#источники)

---

## Текущая ситуация

### Как работает браузерная автоматизация сейчас

Система использует **Playwright напрямую** для запуска браузера Camoufox. Код находится в файле `src/browser_automation.py`, класс `BrowserAutomationSimplified`.

Текущий механизм запуска:
- Playwright вызывает метод `firefox.launch_persistent_context()`
- Передаётся путь к Camoufox binary из Donut Browser через параметр `executable_path`
- Fingerprint передаётся через переменные окружения `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2` и т.д.
- Параметр `headless` принимает только boolean значения (true или false)
- Код устанавливает `DISPLAY=:99` как fallback, но Xvfb нужно запускать вручную

### Откуда берутся данные

**Camoufox binary:** Используется из Donut Browser. Путь определяется автоматически функцией `find_camoufox_executable()` в файле `src/profile_manager.py`. На macOS это обычно `~/Library/Application Support/DonutBrowserDev/binaries/camoufox/*/Camoufox.app/Contents/MacOS/camoufox`.

**Fingerprint:** Хранится в файле `metadata.json` каждого профиля Donut Browser. Поле `camoufox_config.fingerprint` содержит JSON-строку с более чем 100 параметрами: user agent, размеры экрана, WebGL данные, шрифты, геолокация, timezone и другие.

**Профили браузера:** Данные сессии (cookies, localStorage) хранятся в папке `profile/` внутри каждого профиля Donut. Путь передаётся в `user_data_dir`.

### Что установлено

В файле `requirements.txt` указаны зависимости:
- `playwright>=1.40.0` - основная библиотека для автоматизации
- `asyncpg>=0.29.0` - асинхронная работа с PostgreSQL
- Пакет `camoufox` **не установлен**

---

## Проблема

### Почему нужны изменения

1. **Headless режим детектируется.** Обычный `headless=True` в Playwright может быть обнаружен antibot системами. Telegram пока не блокирует, но в будущем может начать.

2. **Xvfb нужно запускать вручную.** Для работы на сервере без монитора сейчас нужно вручную запускать команду `Xvfb :99 &` перед стартом автоматизации. Это неудобно и требует дополнительной настройки systemd или docker.

3. **Нет встроенной поддержки virtual display.** Playwright сам не умеет запускать виртуальный дисплей. Параметр `headless="virtual"` - это фича Python библиотеки Camoufox.

### Что такое headless="virtual"

Это специальный режим в Camoufox Python библиотеке. Когда указываешь `headless="virtual"`:
- Camoufox автоматически запускает Xvfb (виртуальный X11 дисплей) в фоновом режиме
- Браузер работает как обычный (headful), но на виртуальном экране
- Для сайтов браузер выглядит как обычный, не headless
- Не нужно ничего настраивать вручную - всё происходит автоматически

---

## Решение

### Что будем делать

Мигрируем с прямого использования Playwright на Python библиотеку Camoufox (`pip install camoufox`). При этом:

1. **Продолжаем использовать Camoufox binary из Donut Browser** - не скачиваем новый, а указываем путь через `executable_path`

2. **Продолжаем использовать fingerprint из Donut** - передаём его через параметр `config` вместо переменных окружения

3. **Включаем headless="virtual"** - автоматический виртуальный дисплей на Linux

4. **Включаем geoip=True** - автоматическое определение геолокации по IP прокси

5. **Включаем humanize=True** - человекоподобные движения мыши (опционально)

### Почему это безопасно

- Camoufox Python API полностью совместим с Playwright. Возвращает стандартный `BrowserContext` и `Page`
- Все остальные модули (`telegram_sender.py`, `worker.py` и т.д.) работают с объектом `Page` и не знают, как именно запущен браузер
- Формат fingerprint из Donut идентичен формату, который ожидает Camoufox

---

## Исследование и анализ

### Документация Camoufox

Официальная документация: https://camoufox.com/python/

Ключевые страницы:
- Virtual Display: https://camoufox.com/python/virtual-display/
- Usage (параметры): https://camoufox.com/python/usage/
- GeoIP: https://camoufox.com/python/geoip/

### Поддерживаемые параметры AsyncCamoufox

Из документации Camoufox следует, что поддерживаются все параметры Playwright Firefox, плюс дополнительные:

**Для нашей задачи важны:**
- `persistent_context` (bool) - использовать persistent context. Требует `user_data_dir`
- `user_data_dir` (str) - путь к папке профиля браузера
- `executable_path` (str) - путь к custom Camoufox binary
- `headless` (bool или "virtual") - режим работы. "virtual" запускает Xvfb автоматически
- `config` (dict) - словарь с fingerprint конфигурацией
- `geoip` (bool или str) - автоопределение геолокации по IP. True = определить IP автоматически
- `humanize` (bool или float) - человекоподобные движения мыши. True или число секунд
- `proxy` (dict) - настройки прокси в формате Playwright

### Формат fingerprint

Fingerprint из Donut Browser хранится как JSON-строка и содержит поля:

**Навигатор:**
- `navigator.userAgent` - строка user agent
- `navigator.platform` - платформа (Win32, MacIntel, Linux x86_64)
- `navigator.hardwareConcurrency` - количество ядер CPU
- `navigator.language` - язык браузера

**Экран:**
- `screen.width`, `screen.height` - размеры экрана
- `screen.availWidth`, `screen.availHeight` - доступные размеры
- `screen.colorDepth`, `screen.pixelDepth` - глубина цвета

**Окно:**
- `window.outerWidth`, `window.outerHeight` - размеры окна
- `window.screenX`, `window.screenY` - позиция окна

**WebGL:**
- `webGl:renderer` - название видеокарты
- `webGl:vendor` - производитель
- `webGl:supportedExtensions` - список расширений
- `webGl:parameters` - параметры GPU

**Геолокация и время:**
- `timezone` - часовой пояс
- `geolocation:latitude`, `geolocation:longitude` - координаты
- `locale:language`, `locale:region` - локаль

**Шрифты:**
- `fonts` - массив установленных шрифтов

Этот формат полностью совместим с параметром `config` в Camoufox Python API.

### Как передаётся fingerprint сейчас

В файле `src/browser_automation.py` есть метод `_prepare_fingerprint_env()`. Он:
1. Берёт fingerprint как словарь
2. Конвертирует в JSON-строку
3. Разбивает на куски по 32KB (ограничение переменных окружения)
4. Создаёт переменные `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2` и т.д.
5. Передаёт их в `env` параметр при запуске браузера

После миграции этот метод станет не нужен - fingerprint будет передаваться напрямую через `config=`.

---

## Вопросы и ответы

### Вопрос 1: Можно ли использовать свой Camoufox binary?

**Ответ: Да.** Параметр `executable_path` поддерживается. Мы будем использовать binary из Donut Browser, а не скачивать новый через pip.

### Вопрос 2: Совместим ли формат fingerprint?

**Ответ: Да, полностью.** Формат fingerprint из Donut Browser идентичен тому, что ожидает Camoufox. Поля типа `navigator.userAgent`, `screen.width`, `webGl:renderer` - это стандартный формат Camoufox.

### Вопрос 3: Нужно ли менять telegram_sender.py?

**Ответ: Нет.** Camoufox Python API возвращает стандартный Playwright `BrowserContext` и `Page`. Все методы (`page.goto()`, `page.click()`, `page.locator()`) работают без изменений.

### Вопрос 4: Что нужно установить на Linux сервере?

**Ответ: Только xvfb.** Команда `sudo apt-get install xvfb`. После этого Camoufox с `headless="virtual"` сам запустит виртуальный дисплей.

### Вопрос 5: Использовать fingerprint из Donut или генерировать новые?

**Решение: Использовать из Donut.** Профили уже "прожиты", Telegram знает их fingerprint. Смена fingerprint может выглядеть подозрительно.

### Вопрос 6: Включать ли geoip?

**Решение: Да.** Это автоматически настроит timezone и locale по IP прокси. В Donut это тоже включено (`geoip: true` в конфиге). Важно: geoip перезапишет поля геолокации из fingerprint.

### Вопрос 7: Включать ли humanize?

**Решение: Да, попробуем.** Добавит человекоподобные движения мыши. Может немного замедлить работу (1-2 секунды на действие), но улучшит маскировку.

### Вопрос 8: Будет ли конфликт версий Camoufox?

**Потенциальный риск.** Donut использует определённую версию Camoufox binary. Python библиотека camoufox может ожидать другую версию. Нужно протестировать совместимость. Если будут проблемы - можно указать конкретную версию в requirements.txt.

---

## План реализации

### Этап 1: Подготовка

1. Добавить `camoufox>=0.4.0` в `requirements.txt`
2. Установить xvfb на тестовом Linux сервере: `sudo apt-get install xvfb`

### Этап 2: Изменение конфигурации

1. В `config.yaml` изменить секцию telegram:
   - Поменять `headless: false` на `headless: "virtual"`
   - Добавить `geoip: true`
   - Добавить `humanize: true`

2. В `src/config.py` обновить dataclass `TelegramConfig`:
   - Изменить тип поля `headless` с `bool` на `Union[bool, str]`
   - Добавить поле `geoip: bool = True`
   - Добавить поле `humanize: Union[bool, float] = False`

### Этап 3: Изменение browser_automation.py

1. Добавить импорт: `from camoufox.async_api import AsyncCamoufox`

2. В классе `BrowserAutomationSimplified` изменить метод `launch_browser()`:
   - Заменить вызов `playwright.firefox.launch_persistent_context()` на `AsyncCamoufox()`
   - Передавать fingerprint через параметр `config=` вместо env vars
   - Добавить параметры `geoip=`, `humanize=`

3. Удалить метод `_prepare_fingerprint_env()` - больше не нужен

4. Обновить метод `close_browser()` для корректного закрытия Camoufox контекста

### Этап 4: Тестирование

1. Проверить запуск на локальной машине с `headless: false`
2. Проверить запуск на Linux сервере с `headless: "virtual"`
3. Проверить, что fingerprint применяется корректно
4. Проверить работу geoip с прокси
5. Проверить humanize движения мыши
6. Убедиться, что telegram_sender.py работает без изменений

---

## Файлы для изменения

### Файлы, которые нужно изменить

| Файл | Что меняем |
|------|------------|
| `requirements.txt` | Добавляем зависимость `camoufox>=0.4.0` |
| `config.yaml` | Меняем формат headless, добавляем geoip и humanize |
| `src/config.py` | Обновляем dataclass TelegramConfig |
| `src/browser_automation.py` | Заменяем Playwright на Camoufox API |

### Файлы, которые НЕ меняем

| Файл | Почему не трогаем |
|------|-------------------|
| `src/telegram_sender.py` | Работает с Page, API совместим |
| `src/worker.py` | Использует browser_automation, интерфейс сохраняется |
| `src/task_queue.py` | Не связан с браузером |
| `src/database.py` | Не связан с браузером |
| `src/profile_manager.py` | Только читает профили, не запускает браузер |
| `src/proxy_manager.py` | Управляет прокси, не браузером |

### Полные пути к ключевым файлам

```
tg-automatizamtion/
├── requirements.txt                      # Зависимости
├── config.yaml                           # Главный конфиг
├── src/
│   ├── config.py                         # Dataclasses конфигурации
│   ├── browser_automation.py             # ГЛАВНЫЙ ФАЙЛ ДЛЯ ИЗМЕНЕНИЙ
│   ├── telegram_sender.py                # Не трогаем
│   ├── worker.py                         # Не трогаем
│   └── profile_manager.py                # Не трогаем (читает fingerprint)
└── docs/
    └── HEADLESS_VIRTUAL_MIGRATION.md     # Этот документ
```

---

## Источники

### Официальная документация Camoufox

- Главная: https://camoufox.com/
- Python библиотека: https://camoufox.com/python/
- Virtual Display: https://camoufox.com/python/virtual-display/
- Параметры API: https://camoufox.com/python/usage/
- GeoIP и прокси: https://camoufox.com/python/geoip/
- PyPI пакет: https://pypi.org/project/camoufox/

### GitHub

- Репозиторий Camoufox: https://github.com/daijro/camoufox
- Python библиотека: https://github.com/daijro/camoufox/tree/main/pythonlib
- Issue про headless детекцию: https://github.com/daijro/camoufox/issues/26

### Внутренние файлы проекта

- TypeScript интерфейсы fingerprint: `donutbrowser/src/types.ts` (строки 74-247)
- Пример metadata.json: `donutbrowser/data/profiles/*/metadata.json`
- Текущая реализация browser_automation: `tg-automatizamtion/src/browser_automation.py`
- Загрузка fingerprint: `tg-automatizamtion/src/profile_manager.py` (строки 106-133)

---

## Заметки

### Важные моменты при реализации

1. **Порядок параметров в fingerprint.** При включённом geoip, поля геолокации из fingerprint будут перезаписаны. Это нормально - геолокация должна соответствовать IP прокси.

2. **Совместимость версий.** Если возникнут проблемы с binary из Donut, можно попробовать использовать binary от camoufox pip пакета. Команда `python -m camoufox fetch` скачает последнюю версию.

3. **Fallback на обычный headless.** Если `headless="virtual"` не работает (нет xvfb), можно временно использовать `headless=True`.

4. **Логирование.** Добавить логи при запуске браузера, чтобы видеть, какой режим headless используется.

---

*Документ будет обновляться по мере реализации.*
