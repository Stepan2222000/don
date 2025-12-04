"""
Proxy Manager - управление пулом прокси и привязками к профилям.

Функции:
- Загрузка прокси из текстового файла
- Синхронизация с БД
- Sticky assignment прокси к профилям
- Получение прокси для профиля
"""

import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

from .config import load_config, get_config, PROJECT_ROOT


@dataclass
class Proxy:
    """Данные прокси."""
    url: str                      # host:port:user:pass
    profile_id: Optional[str]     # К какому профилю привязан
    is_healthy: bool = True
    assigned_at: Optional[str] = None

    @property
    def playwright_url(self) -> str:
        """Преобразовать в формат для Playwright: http://user:pass@host:port"""
        parts = self.url.split(':')
        if len(parts) == 4:
            host, port, user, password = parts
            return f"http://{user}:{password}@{host}:{port}"
        return self.url

    @property
    def host(self) -> str:
        """Получить хост прокси."""
        return self.url.split(':')[0] if ':' in self.url else self.url

    @property
    def port(self) -> int:
        """Получить порт прокси."""
        parts = self.url.split(':')
        return int(parts[1]) if len(parts) >= 2 else 0


class ProxyManager:
    """Управление пулом прокси и привязками."""

    def __init__(self, db_path: str = None, pool_file: str = None):
        """
        Инициализация менеджера прокси.

        Args:
            db_path: Путь к БД (по умолчанию из конфига)
            pool_file: Путь к файлу с прокси (по умолчанию из конфига)
        """
        try:
            config = get_config()
        except RuntimeError:
            config = load_config()

        self.db_path = db_path or config.database.absolute_path
        self.pool_file = pool_file or config.proxy.absolute_pool_path

    def _get_connection(self) -> sqlite3.Connection:
        """Получить соединение с БД."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_proxies_from_file(self) -> List[str]:
        """
        Загрузить прокси из текстового файла.

        Returns:
            Список прокси в формате host:port:user:pass
        """
        proxies = []
        pool_path = Path(self.pool_file)

        if not pool_path.exists():
            return proxies

        with open(pool_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                proxies.append(line)

        return proxies

    def sync_with_file(self):
        """
        Синхронизировать БД с файлом прокси.

        - Новые прокси из файла добавляются в БД
        - Удалённые из файла - помечаются как неактивные (но не удаляются)
        """
        file_proxies = set(self.load_proxies_from_file())
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Получаем текущие прокси из БД
            cursor.execute("SELECT proxy_url FROM proxy_assignments")
            db_proxies = {row['proxy_url'] for row in cursor.fetchall()}

            # Добавляем новые прокси
            new_proxies = file_proxies - db_proxies
            for proxy_url in new_proxies:
                cursor.execute("""
                    INSERT INTO proxy_assignments (proxy_url, is_healthy)
                    VALUES (?, 1)
                """, (proxy_url,))

            # Помечаем удалённые как unhealthy
            removed_proxies = db_proxies - file_proxies
            for proxy_url in removed_proxies:
                cursor.execute("""
                    UPDATE proxy_assignments
                    SET is_healthy = 0
                    WHERE proxy_url = ?
                """, (proxy_url,))

            conn.commit()
            return len(new_proxies), len(removed_proxies)
        finally:
            conn.close()

    def get_proxy_for_profile(self, profile_id: str) -> Optional[Proxy]:
        """
        Получить прокси для профиля.

        Args:
            profile_id: ID профиля

        Returns:
            Proxy если есть привязка, иначе None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT proxy_url, profile_id, is_healthy, assigned_at
                FROM proxy_assignments
                WHERE profile_id = ?
            """, (profile_id,))

            row = cursor.fetchone()
            if row:
                return Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=bool(row['is_healthy']),
                    assigned_at=row['assigned_at']
                )
            return None
        finally:
            conn.close()

    def get_available_proxy(self) -> Optional[Proxy]:
        """
        Получить свободный здоровый прокси.

        Returns:
            Proxy если есть свободный, иначе None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT proxy_url, profile_id, is_healthy, assigned_at
                FROM proxy_assignments
                WHERE profile_id IS NULL AND is_healthy = 1
                ORDER BY RANDOM()
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row:
                return Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=bool(row['is_healthy']),
                    assigned_at=row['assigned_at']
                )
            return None
        finally:
            conn.close()

    def assign_proxy(self, profile_id: str, proxy_url: str):
        """
        Привязать прокси к профилю.

        Args:
            profile_id: ID профиля
            proxy_url: URL прокси
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE proxy_assignments
                SET profile_id = ?, assigned_at = ?
                WHERE proxy_url = ?
            """, (profile_id, now, proxy_url))
            conn.commit()
        finally:
            conn.close()

    def release_proxy(self, proxy_url: str):
        """
        Освободить прокси (убрать привязку).

        Args:
            proxy_url: URL прокси
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE proxy_assignments
                SET profile_id = NULL, assigned_at = NULL
                WHERE proxy_url = ?
            """, (proxy_url,))
            conn.commit()
        finally:
            conn.close()

    def mark_unhealthy(self, proxy_url: str):
        """
        Пометить прокси как нездоровый.

        Args:
            proxy_url: URL прокси
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE proxy_assignments
                SET is_healthy = 0, last_rotation_at = ?
                WHERE proxy_url = ?
            """, (now, proxy_url))
            conn.commit()
        finally:
            conn.close()

    def mark_healthy(self, proxy_url: str):
        """
        Пометить прокси как здоровый.

        Args:
            proxy_url: URL прокси
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE proxy_assignments
                SET is_healthy = 1
                WHERE proxy_url = ?
            """, (proxy_url,))
            conn.commit()
        finally:
            conn.close()

    def reset_unhealthy_proxies(self, hours: int = 1):
        """
        Сбросить unhealthy статус для прокси старше N часов.

        Даёт "второй шанс" прокси которые давно не использовались.

        Args:
            hours: Через сколько часов сбрасывать
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE proxy_assignments
                SET is_healthy = 1
                WHERE is_healthy = 0
                AND last_rotation_at < datetime('now', ? || ' hours')
            """, (f'-{hours}',))
            affected = cursor.rowcount
            conn.commit()
            return affected
        finally:
            conn.close()

    def get_all_proxies(self) -> List[Proxy]:
        """Получить все прокси."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT proxy_url, profile_id, is_healthy, assigned_at
                FROM proxy_assignments
                ORDER BY profile_id NULLS LAST
            """)

            return [
                Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=bool(row['is_healthy']),
                    assigned_at=row['assigned_at']
                )
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_or_assign_proxy(self, profile_id: str) -> Optional[Proxy]:
        """
        Получить прокси для профиля или назначить новый.

        Args:
            profile_id: ID профиля

        Returns:
            Proxy (существующий или новый)
        """
        # Сначала пробуем получить существующий
        proxy = self.get_proxy_for_profile(profile_id)
        if proxy and proxy.is_healthy:
            return proxy

        # Если нет или нездоровый - пробуем получить свободный
        available = self.get_available_proxy()
        if available:
            self.assign_proxy(profile_id, available.url)
            available.profile_id = profile_id
            return available

        # Если нет свободных - возвращаем текущий (даже если нездоровый)
        return proxy


# Синглтон для глобального доступа
_proxy_manager: Optional[ProxyManager] = None


def get_proxy_manager() -> ProxyManager:
    """Получить глобальный экземпляр ProxyManager."""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
