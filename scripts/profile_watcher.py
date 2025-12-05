#!/usr/bin/env python3
"""
Profile Watcher - автосинхронизация профилей DonutBrowser.

Отслеживает какие профили изменились и синхронизирует их после закрытия браузера.

Использование:
    python scripts/profile_watcher.py
    python scripts/profile_watcher.py --daemon  # Запуск в фоне
"""

import os
import sys
import time
import signal
import argparse
import subprocess
from pathlib import Path
from typing import Set

import psutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Пути к профилям
PROFILES_PATHS = [
    Path.home() / "Library/Application Support/DonutBrowserDev/profiles",
    Path(__file__).parent.parent / "donutbrowser/data/profiles",
]


class ProfileChangeHandler(FileSystemEventHandler):
    """Отслеживает изменения в папках профилей."""

    def __init__(self):
        self.modified_profiles: Set[str] = set()

    def on_modified(self, event):
        self._record_change(event.src_path)

    def on_created(self, event):
        self._record_change(event.src_path)

    def _record_change(self, src_path: str):
        """Извлекаем profile_id из пути."""
        path = Path(src_path)
        for parent in path.parents:
            if parent.parent.name == "profiles":
                self.modified_profiles.add(parent.name)
                break

    def get_and_clear(self) -> Set[str]:
        """Получить изменённые профили и очистить список."""
        profiles = self.modified_profiles.copy()
        self.modified_profiles.clear()
        return profiles


class ProfileWatcher:
    """Watcher для автосинхронизации профилей."""

    def __init__(self):
        self.browser_was_running = False
        self.handler = ProfileChangeHandler()
        self.observer = Observer()
        self.running = True
        self.profiles_dir = self._find_profiles_dir()
        self.sync_script = Path(__file__).parent / "sync-profiles-to-server.sh"
        self.config_file = Path.home() / ".donut-sync.conf"

        # Обработка сигналов
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Graceful shutdown."""
        print("\nОстановка watcher...")
        self.running = False
        self.observer.stop()

    def _find_profiles_dir(self) -> Path:
        """Найти директорию с профилями."""
        for path in PROFILES_PATHS:
            if path.exists():
                return path
        raise FileNotFoundError("Директория профилей не найдена")

    def is_browser_running(self) -> bool:
        """Проверить запущен ли браузер."""
        browser_names = ['donutbrowser', 'camoufox', 'firefox']
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                name = proc.info['name'].lower() if proc.info['name'] else ''
                for browser in browser_names:
                    if browser in name:
                        return True
                # Проверка cmdline для camoufox
                cmdline = proc.info.get('cmdline') or []
                for arg in cmdline:
                    if arg and 'camoufox' in arg.lower():
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def _load_config(self) -> dict:
        """Загрузить credentials из конфиг файла."""
        config = {}
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        return config

    def sync_profiles(self, profile_ids: Set[str]):
        """Синхронизировать конкретные профили."""
        if not profile_ids:
            print("Нет изменённых профилей для синхронизации")
            return

        print(f"\nСинхронизация {len(profile_ids)} профилей:")
        for pid in profile_ids:
            print(f"  - {pid[:8]}...")

        if not self.sync_script.exists():
            print(f"Sync скрипт не найден: {self.sync_script}")
            return

        # Загружаем конфиг
        config = self._load_config()

        # Формируем команду
        profiles_arg = ",".join(profile_ids)

        # Если есть конфиг с credentials - используем автоматический режим
        if config.get('SERVER_IP') and config.get('SERVER_USER') and config.get('SERVER_PASS'):
            env = os.environ.copy()
            env['AUTO_MODE'] = '1'
            env['PROFILES'] = profiles_arg
            env['SERVER_IP'] = config['SERVER_IP']
            env['SERVER_USER'] = config['SERVER_USER']
            env['SERVER_PASS'] = config['SERVER_PASS']

            try:
                result = subprocess.run(
                    [str(self.sync_script), '--auto', '--profiles', profiles_arg],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    print("Синхронизация завершена успешно")
                else:
                    print(f"Ошибка синхронизации: {result.stderr}")
            except subprocess.TimeoutExpired:
                print("Таймаут синхронизации (5 минут)")
            except Exception as e:
                print(f"Ошибка: {e}")
        else:
            # Интерактивный режим
            print(f"\nДля автоматической синхронизации создай файл {self.config_file}:")
            print("SERVER_IP=81.30.105.134")
            print("SERVER_USER=root")
            print("SERVER_PASS=your_password")
            print("\nИли запусти вручную:")
            print(f"  {self.sync_script}")

    def run(self):
        """Главный цикл."""
        # Запускаем наблюдатель
        try:
            self.observer.schedule(self.handler, str(self.profiles_dir), recursive=True)
            self.observer.start()
        except Exception as e:
            print(f"Ошибка запуска observer: {e}")
            return

        print("=" * 60)
        print("Profile Watcher запущен")
        print("=" * 60)
        print(f"Слежу за: {self.profiles_dir}")
        print(f"Sync скрипт: {self.sync_script}")
        print(f"Конфиг: {self.config_file}")
        print("-" * 60)
        print("Браузер открыт → работаешь с профилем")
        print("Браузер закрыт → автоматическая синхронизация")
        print("-" * 60)
        print("Нажми Ctrl+C для остановки")
        print()

        try:
            while self.running:
                is_running = self.is_browser_running()

                if is_running and not self.browser_was_running:
                    print(f"[{time.strftime('%H:%M:%S')}] Браузер запущен")

                if self.browser_was_running and not is_running:
                    # Браузер только что закрылся
                    print(f"[{time.strftime('%H:%M:%S')}] Браузер закрыт")
                    time.sleep(2)  # Даём время на запись файлов

                    modified = self.handler.get_and_clear()
                    if modified:
                        self.sync_profiles(modified)
                    else:
                        print("Нет изменённых профилей")

                self.browser_was_running = is_running
                time.sleep(3)

        except KeyboardInterrupt:
            pass
        finally:
            self.observer.stop()
            self.observer.join()
            print("Watcher остановлен")


def create_config_template():
    """Создать шаблон конфига."""
    config_path = Path.home() / ".donut-sync.conf"
    if config_path.exists():
        print(f"Конфиг уже существует: {config_path}")
        return

    template = """# Donut Browser Sync Configuration
# Этот файл используется для автоматической синхронизации профилей

SERVER_IP=81.30.105.134
SERVER_USER=root
SERVER_PASS=your_password_here
"""
    with open(config_path, 'w') as f:
        f.write(template)
    os.chmod(config_path, 0o600)  # Только владелец может читать
    print(f"Создан шаблон конфига: {config_path}")
    print("Отредактируй его и добавь свой пароль!")


def main():
    parser = argparse.ArgumentParser(description='Profile Watcher - автосинхронизация профилей')
    parser.add_argument('--daemon', '-d', action='store_true', help='Запуск в фоне')
    parser.add_argument('--create-config', action='store_true', help='Создать шаблон конфига')
    args = parser.parse_args()

    if args.create_config:
        create_config_template()
        return

    if args.daemon:
        # Fork в фоновый процесс
        pid = os.fork()
        if pid > 0:
            print(f"Watcher запущен в фоне (PID: {pid})")
            sys.exit(0)
        # Дочерний процесс продолжает работу
        os.setsid()

    watcher = ProfileWatcher()
    watcher.run()


if __name__ == "__main__":
    main()
