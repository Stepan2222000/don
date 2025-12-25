# Исправление ошибки properties.json в Camoufox

## Описание проблемы

При использовании профилей Donut Browser с библиотекой Camoufox 0.4.11 возникает ошибка:

```
FileNotFoundError: [Errno 2] No such file or directory:
'/Users/.../DonutBrowserDev/binaries/camoufox/v135.0.1-beta.24/Camoufox.app/Contents/MacOS/properties.json'
```

## Причина

Это известный баг в Camoufox 0.4.11 (см. [Issue #210](https://github.com/daijro/camoufox/issues/210)).

**Суть проблемы:**
- Camoufox требует файл `properties.json` для валидации конфигурации fingerprint
- При использовании кастомного `executable_path` (как в Donut Browser), Camoufox ищет `properties.json` в `{executable_path.parent}/properties.json`
- Для macOS это путь: `Camoufox.app/Contents/MacOS/properties.json`
- Но в стандартной сборке Camoufox файл находится в: `Camoufox.app/Contents/Resources/properties.json`
- Donut Browser при упаковке не копирует файл в папку `MacOS/`, что вызывает ошибку

**Почему это происходит:**

В исходном коде Camoufox (`camoufox/utils.py:77-88`):

```python
def _load_properties(path: Optional[Path] = None) -> Dict[str, str]:
    """
    Loads the properties.json file.
    """
    if path:
        prop_file = str(path.parent / "properties.json")  # ← ищет в родительской директории
    else:
        prop_file = get_path("properties.json")
    with open(prop_file, "rb") as f:
        prop_dict = orjson.loads(f.read())

    return {prop['property']: prop['type'] for prop in prop_dict}
```

Когда `executable_path` = `.../MacOS/camoufox`, `path.parent` = `.../MacOS/`, а файл реально лежит в `.../Resources/`.

## Решение

### Вариант 1: Автоматическое исправление (рекомендуется)

Запустите скрипт автоматического исправления:

```bash
python scripts/fix_properties_json.py
```

Скрипт:
1. Найдёт все установки Camoufox в Donut Browser
2. Проверит наличие `properties.json` в папке `MacOS/`
3. Если файл отсутствует, скопирует его из `Resources/`

**Пример вывода:**

```
Fixing properties.json for Donut Browser Camoufox installations...

Found 1 installation(s):

Processing v135.0.1-beta.24:
  ✓ Copied: properties.json → MacOS/

Summary: 1/1 installation(s) fixed successfully.
```

### Вариант 2: Ручное исправление

Если скрипт не работает, скопируйте файл вручную:

```bash
# Замените v135.0.1-beta.24 на вашу версию Camoufox
cp "$HOME/Library/Application Support/DonutBrowserDev/binaries/camoufox/v135.0.1-beta.24/Camoufox.app/Contents/Resources/properties.json" \
   "$HOME/Library/Application Support/DonutBrowserDev/binaries/camoufox/v135.0.1-beta.24/Camoufox.app/Contents/MacOS/properties.json"
```

### Вариант 3: Переустановка стандартного Camoufox (не рекомендуется)

Этот вариант не исправит проблему с Donut Browser, но покажет как работает стандартная установка:

```bash
camoufox remove
camoufox fetch
```

В стандартной установке (`.../Library/Caches/camoufox/`) файл `properties.json` присутствует в обеих папках - `MacOS/` и `Resources/`.

## Проверка исправления

После применения fix проверьте наличие файла:

```bash
ls -la "$HOME/Library/Application Support/DonutBrowserDev/binaries/camoufox/v135.0.1-beta.24/Camoufox.app/Contents/MacOS/properties.json"
```

Должен вывести:

```
-rw-r--r--@ 1 user  staff  5974 Dec 25 14:54 .../properties.json
```

## Когда нужно повторно применять fix

Fix нужно применять заново в следующих случаях:

1. **При обновлении Camoufox в Donut Browser** - новая версия снова не будет содержать файл в `MacOS/`
2. **При переустановке Donut Browser** - файл будет удалён
3. **При добавлении нового профиля с новой версией Camoufox**

## Автоматизация fix

Чтобы не запускать скрипт вручную каждый раз, можно добавить проверку в код:

```python
# В src/browser_automation.py перед запуском AsyncCamoufox:

def ensure_properties_json(executable_path: str) -> None:
    """Ensure properties.json exists in MacOS directory."""
    from pathlib import Path
    import shutil

    exec_path = Path(executable_path)
    if not exec_path.exists():
        return

    source = exec_path.parent.parent / "Resources/properties.json"
    target = exec_path.parent / "properties.json"

    if not target.exists() and source.exists():
        shutil.copy2(source, target)

# Вызов перед AsyncCamoufox:
ensure_properties_json(profile.executable_path)
```

## Статус проблемы в Camoufox

- **Версия с багом:** 0.4.11 (актуальная на 25.12.2025)
- **Issue:** [#210 - properties.json file not found](https://github.com/daijro/camoufox/issues/210)
- **Статус:** Открыт (разработчик предлагает переустановку, но это не решает проблему для кастомных установок)
- **Новые версии:** Нет (0.4.11 - последняя версия на PyPI)

## Технические детали

### Структура стандартной установки Camoufox:

```
~/Library/Caches/camoufox/Camoufox.app/Contents/
├── MacOS/
│   ├── camoufox              (исполняемый файл)
│   └── properties.json       ✓ ЕСТЬ
└── Resources/
    ├── properties.json       ✓ ЕСТЬ
    ├── camoufox.cfg
    └── ...
```

### Структура Donut Browser установки:

```
~/Library/Application Support/DonutBrowserDev/binaries/camoufox/v135.0.1-beta.24/Camoufox.app/Contents/
├── MacOS/
│   ├── camoufox              (исполняемый файл)
│   └── properties.json       ✗ ОТСУТСТВУЕТ (нужно скопировать)
└── Resources/
    ├── properties.json       ✓ ЕСТЬ
    ├── camoufox.cfg
    └── ...
```

### Содержимое properties.json:

Файл содержит схему валидации для 100+ свойств fingerprint:

```json
[
  { "property": "navigator.userAgent", "type": "str" },
  { "property": "navigator.hardwareConcurrency", "type": "uint" },
  { "property": "screen.width", "type": "uint" },
  { "property": "webGl:renderer", "type": "str" },
  ...
]
```

Используется в `camoufox/utils.py:validate_config()` для проверки типов значений в fingerprint конфигурации.

## Источники

- [Camoufox Issue #210](https://github.com/daijro/camoufox/issues/210) - обсуждение проблемы
- [Camoufox Releases](https://github.com/daijro/camoufox/releases) - релизы браузера
- [Camoufox на PyPI](https://pypi.org/project/camoufox/) - Python библиотека

---

**Последнее обновление:** 25.12.2025
