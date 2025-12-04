#!/usr/bin/env python3
"""
Миграция прокси из DonutBrowser в новую систему.

Читает:
- donutbrowser/data/proxies/*.json - файлы прокси
- donutbrowser/data/profiles/*/metadata.json - привязки к профилям

Создаёт:
- data/proxies.txt - текстовый файл с прокси (host:port:user:pass)
- Записи в БД таблицу proxy_assignments
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Database
from src.config import load_config


def get_donut_data_dir() -> Path:
    """Получить путь к данным DonutBrowser."""
    # Проверяем переменную окружения
    env_path = os.environ.get('DONUTBROWSER_DATA_DIR')
    if env_path:
        return Path(env_path)

    # Путь по умолчанию относительно проекта
    project_root = Path(__file__).parent.parent.parent
    return project_root / 'donutbrowser' / 'data'


def load_proxy_files(proxies_dir: Path) -> dict:
    """Загрузить все файлы прокси."""
    proxies = {}

    if not proxies_dir.exists():
        print(f"Директория прокси не найдена: {proxies_dir}")
        return proxies

    for proxy_file in proxies_dir.glob('*.json'):
        try:
            with open(proxy_file, 'r') as f:
                data = json.load(f)
                proxy_id = data.get('id')
                if proxy_id:
                    proxies[proxy_id] = data
                    print(f"  Загружен прокси: {data.get('name', proxy_id)}")
        except Exception as e:
            print(f"  Ошибка загрузки {proxy_file}: {e}")

    return proxies


def load_profile_assignments(profiles_dir: Path) -> dict:
    """Загрузить привязки proxy_id к profile_id."""
    assignments = {}

    if not profiles_dir.exists():
        print(f"Директория профилей не найдена: {profiles_dir}")
        return assignments

    for metadata_file in profiles_dir.glob('*/metadata.json'):
        try:
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                profile_id = data.get('id')
                proxy_id = data.get('proxy_id')
                profile_name = data.get('name', profile_id)

                if profile_id and proxy_id:
                    assignments[proxy_id] = {
                        'profile_id': profile_id,
                        'profile_name': profile_name
                    }
                    print(f"  Профиль '{profile_name}' -> proxy_id: {proxy_id[:8]}...")
        except Exception as e:
            print(f"  Ошибка загрузки {metadata_file}: {e}")

    return assignments


def proxy_to_line(proxy_data: dict) -> str:
    """Преобразовать данные прокси в строку host:port:user:pass."""
    settings = proxy_data.get('proxy_settings', {})
    host = settings.get('host', '')
    port = settings.get('port', '')
    username = settings.get('username', '')
    password = settings.get('password', '')

    if not host or not port:
        return None

    return f"{host}:{port}:{username}:{password}"


def create_proxies_txt(proxies: dict, output_path: Path):
    """Создать файл proxies.txt."""
    lines = [
        "# Прокси для автоматизации Telegram",
        "# Формат: host:port:user:pass",
        "# Пустые строки и комментарии (#) игнорируются",
        f"# Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]

    for proxy_id, proxy_data in proxies.items():
        line = proxy_to_line(proxy_data)
        if line:
            lines.append(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"\nСоздан файл: {output_path}")
    print(f"Всего прокси: {len(proxies)}")


def save_assignments_to_db(db: Database, proxies: dict, assignments: dict):
    """Сохранить привязки в БД."""
    now = datetime.now().isoformat()

    for proxy_id, proxy_data in proxies.items():
        proxy_line = proxy_to_line(proxy_data)
        if not proxy_line:
            continue

        # Получаем привязку к профилю
        assignment = assignments.get(proxy_id, {})
        profile_id = assignment.get('profile_id')

        # Записываем в БД
        try:
            db.execute("""
                INSERT OR REPLACE INTO proxy_assignments
                (proxy_url, profile_id, is_healthy, assigned_at)
                VALUES (?, ?, 1, ?)
            """, (proxy_line, profile_id, now if profile_id else None))

            status = f"-> профиль {assignment.get('profile_name', profile_id)}" if profile_id else "(свободен)"
            print(f"  {proxy_line[:30]}... {status}")
        except Exception as e:
            print(f"  Ошибка записи {proxy_line}: {e}")

    db.commit()


def main():
    print("=" * 60)
    print("Миграция прокси из DonutBrowser")
    print("=" * 60)

    # Пути
    donut_dir = get_donut_data_dir()
    proxies_dir = donut_dir / 'proxies'
    profiles_dir = donut_dir / 'profiles'

    project_root = Path(__file__).parent.parent
    output_path = project_root / 'data' / 'proxies.txt'

    print(f"\nDonutBrowser данные: {donut_dir}")
    print(f"Выходной файл: {output_path}")

    # Загружаем прокси
    print("\n[1/4] Загрузка файлов прокси...")
    proxies = load_proxy_files(proxies_dir)

    if not proxies:
        print("Прокси не найдены!")
        return 1

    # Загружаем привязки
    print("\n[2/4] Загрузка привязок к профилям...")
    assignments = load_profile_assignments(profiles_dir)

    # Создаём proxies.txt
    print("\n[3/4] Создание proxies.txt...")
    create_proxies_txt(proxies, output_path)

    # Сохраняем в БД
    print("\n[4/4] Сохранение привязок в БД...")
    try:
        config = load_config()
        db_path = config.database.absolute_path
        print(f"  Путь к БД: {db_path}")

        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем что таблица существует
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proxy_assignments'")
        if not cursor.fetchone():
            print("  Таблица proxy_assignments не существует. Запустите миграцию БД.")
            print("  Пропускаем сохранение в БД...")
            conn.close()
            return 0

        # Сохраняем привязки
        now = datetime.now().isoformat()
        for proxy_id, proxy_data in proxies.items():
            proxy_line = proxy_to_line(proxy_data)
            if not proxy_line:
                continue

            assignment = assignments.get(proxy_id, {})
            profile_id = assignment.get('profile_id')

            cursor.execute("""
                INSERT OR REPLACE INTO proxy_assignments
                (proxy_url, profile_id, is_healthy, assigned_at)
                VALUES (?, ?, 1, ?)
            """, (proxy_line, profile_id, now if profile_id else None))

            status = f"-> профиль {assignment.get('profile_name', profile_id)}" if profile_id else "(свободен)"
            print(f"  {proxy_line[:30]}... {status}")

        conn.commit()
        conn.close()
        print("\nПривязки сохранены в БД.")
    except Exception as e:
        import traceback
        print(f"Ошибка работы с БД: {e}")
        traceback.print_exc()
        print("Файл proxies.txt создан, но привязки не сохранены в БД.")

    print("\n" + "=" * 60)
    print("Миграция завершена!")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
