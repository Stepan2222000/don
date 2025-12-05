"""
Proxy Manager - управление пулом прокси и привязками к профилям.

Функции:
- Загрузка прокси из текстового файла (резервный пул)
- Привязка прокси к профилям в БД
- Ротация прокси при проблемах
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

from .config import load_config, get_config, PROJECT_ROOT
from .database import get_database


@dataclass
class Proxy:
    """Данные прокси."""
    url: str                      # host:port:user:pass
    profile_id: Optional[str]     # К какому профилю привязан
    is_healthy: bool = True
    is_blocked: bool = False
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

    def __init__(self, pool_file: str = None):
        """
        Инициализация менеджера прокси.

        Args:
            pool_file: Путь к файлу с резервными прокси (по умолчанию из конфига)
        """
        try:
            config = get_config()
        except RuntimeError:
            config = load_config()

        self.pool_file = pool_file or config.proxy.absolute_pool_path
        self._db = get_database()

    def _placeholder(self) -> str:
        """Get placeholder for parameterized queries."""
        return "%s" if self._db._db_type == "postgresql" else "?"

    def load_proxies_from_file(self) -> List[str]:
        """
        Загрузить прокси из текстового файла (резервный пул).

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

    def sync_reserve_proxies(self) -> tuple:
        """
        Синхронизировать резервные прокси из файла в БД.
        Добавляет новые прокси, не трогает существующие.

        Returns:
            (added_count, total_in_file)
        """
        file_proxies = self.load_proxies_from_file()
        ph = self._placeholder()
        added = 0

        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            for proxy_url in file_proxies:
                if self._db._db_type == "postgresql":
                    cursor.execute(f"""
                        INSERT INTO proxy_assignments (proxy_url, is_healthy)
                        VALUES ({ph}, TRUE)
                        ON CONFLICT(proxy_url) DO NOTHING
                    """, (proxy_url,))
                else:
                    cursor.execute(f"""
                        INSERT OR IGNORE INTO proxy_assignments (proxy_url, is_healthy)
                        VALUES ({ph}, 1)
                    """, (proxy_url,))
                added += cursor.rowcount

        return added, len(file_proxies)

    def get_proxy_for_profile(self, profile_id: str) -> Optional[Proxy]:
        """
        Получить прокси привязанный к профилю.

        Args:
            profile_id: ID профиля

        Returns:
            Proxy если есть привязка, иначе None
        """
        ph = self._placeholder()
        conn = self._db._get_connection()
        cursor = self._db._get_cursor(conn)

        cursor.execute(f"""
            SELECT proxy_url, profile_id, is_healthy, is_blocked, assigned_at
            FROM proxy_assignments
            WHERE profile_id = {ph}
        """, (profile_id,))

        row = cursor.fetchone()
        if row:
            if self._db._db_type == "postgresql":
                return Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=row['is_healthy'],
                    is_blocked=row['is_blocked'],
                    assigned_at=str(row['assigned_at']) if row['assigned_at'] else None
                )
            else:
                return Proxy(
                    url=row[0],
                    profile_id=row[1],
                    is_healthy=bool(row[2]),
                    is_blocked=bool(row[3]),
                    assigned_at=row[4]
                )
        return None

    def get_available_proxy(self) -> Optional[Proxy]:
        """
        Получить свободный здоровый прокси из резервного пула.

        Returns:
            Proxy если есть свободный, иначе None
        """
        conn = self._db._get_connection()
        cursor = self._db._get_cursor(conn)

        if self._db._db_type == "postgresql":
            cursor.execute("""
                SELECT proxy_url, profile_id, is_healthy, is_blocked, assigned_at
                FROM proxy_assignments
                WHERE profile_id IS NULL AND is_healthy = TRUE AND is_blocked = FALSE
                ORDER BY RANDOM()
                LIMIT 1
            """)
        else:
            cursor.execute("""
                SELECT proxy_url, profile_id, is_healthy, is_blocked, assigned_at
                FROM proxy_assignments
                WHERE profile_id IS NULL AND is_healthy = 1 AND is_blocked = 0
                ORDER BY RANDOM()
                LIMIT 1
            """)

        row = cursor.fetchone()
        if row:
            if self._db._db_type == "postgresql":
                return Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=row['is_healthy'],
                    is_blocked=row['is_blocked'],
                    assigned_at=str(row['assigned_at']) if row['assigned_at'] else None
                )
            else:
                return Proxy(
                    url=row[0],
                    profile_id=row[1],
                    is_healthy=bool(row[2]),
                    is_blocked=bool(row[3]),
                    assigned_at=row[4]
                )
        return None

    def _ensure_proxy_in_db(self, proxy_url: str):
        """
        Убедиться что прокси есть в БД (INSERT OR IGNORE).

        Args:
            proxy_url: URL прокси в формате host:port:user:pass
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            if self._db._db_type == "postgresql":
                cursor.execute(f"""
                    INSERT INTO proxy_assignments (proxy_url, is_healthy)
                    VALUES ({ph}, TRUE)
                    ON CONFLICT(proxy_url) DO NOTHING
                """, (proxy_url,))
            else:
                cursor.execute(f"""
                    INSERT OR IGNORE INTO proxy_assignments (proxy_url, is_healthy)
                    VALUES ({ph}, 1)
                """, (proxy_url,))

    def assign_proxy(self, profile_id: str, proxy_url: str):
        """
        Привязать прокси к профилю.

        Args:
            profile_id: ID профиля
            proxy_url: URL прокси
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            cursor.execute(f"""
                UPDATE proxy_assignments
                SET profile_id = {ph}, assigned_at = CURRENT_TIMESTAMP
                WHERE proxy_url = {ph}
            """, (profile_id, proxy_url))

    def release_proxy(self, proxy_url: str):
        """
        Освободить прокси (убрать привязку).

        Args:
            proxy_url: URL прокси
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            cursor.execute(f"""
                UPDATE proxy_assignments
                SET profile_id = NULL, assigned_at = NULL
                WHERE proxy_url = {ph}
            """, (proxy_url,))

    def mark_unhealthy(self, proxy_url: str):
        """
        Пометить прокси как нездоровый.

        Args:
            proxy_url: URL прокси
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            if self._db._db_type == "postgresql":
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = FALSE, last_rotation_at = CURRENT_TIMESTAMP
                    WHERE proxy_url = {ph}
                """, (proxy_url,))
            else:
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = 0, last_rotation_at = CURRENT_TIMESTAMP
                    WHERE proxy_url = {ph}
                """, (proxy_url,))

    def mark_blocked(self, proxy_url: str):
        """
        Пометить прокси как заблокированный.

        Args:
            proxy_url: URL прокси
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            if self._db._db_type == "postgresql":
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_blocked = TRUE, is_healthy = FALSE,
                        profile_id = NULL, last_rotation_at = CURRENT_TIMESTAMP
                    WHERE proxy_url = {ph}
                """, (proxy_url,))
            else:
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_blocked = 1, is_healthy = 0,
                        profile_id = NULL, last_rotation_at = CURRENT_TIMESTAMP
                    WHERE proxy_url = {ph}
                """, (proxy_url,))

    def mark_healthy(self, proxy_url: str):
        """
        Пометить прокси как здоровый.

        Args:
            proxy_url: URL прокси
        """
        ph = self._placeholder()
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            if self._db._db_type == "postgresql":
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = TRUE
                    WHERE proxy_url = {ph}
                """, (proxy_url,))
            else:
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = 1
                    WHERE proxy_url = {ph}
                """, (proxy_url,))

    def reset_unhealthy_proxies(self, hours: int = 1) -> int:
        """
        Сбросить unhealthy статус для прокси старше N часов.
        Даёт "второй шанс" прокси которые давно не использовались.

        Args:
            hours: Через сколько часов сбрасывать

        Returns:
            Количество сброшенных прокси
        """
        with self._db.transaction() as conn:
            cursor = self._db._get_cursor(conn)
            if self._db._db_type == "postgresql":
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = TRUE
                    WHERE is_healthy = FALSE AND is_blocked = FALSE
                    AND last_rotation_at < CURRENT_TIMESTAMP - INTERVAL '{hours} hours'
                """)
            else:
                cursor.execute(f"""
                    UPDATE proxy_assignments
                    SET is_healthy = 1
                    WHERE is_healthy = 0 AND is_blocked = 0
                    AND last_rotation_at < datetime('now', '-{hours} hours')
                """)
            return cursor.rowcount

    def get_all_proxies(self) -> List[Proxy]:
        """Получить все прокси."""
        conn = self._db._get_connection()
        cursor = self._db._get_cursor(conn)

        cursor.execute("""
            SELECT proxy_url, profile_id, is_healthy, is_blocked, assigned_at
            FROM proxy_assignments
            ORDER BY profile_id NULLS LAST
        """)

        proxies = []
        for row in cursor.fetchall():
            if self._db._db_type == "postgresql":
                proxies.append(Proxy(
                    url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    is_healthy=row['is_healthy'],
                    is_blocked=row['is_blocked'],
                    assigned_at=str(row['assigned_at']) if row['assigned_at'] else None
                ))
            else:
                proxies.append(Proxy(
                    url=row[0],
                    profile_id=row[1],
                    is_healthy=bool(row[2]),
                    is_blocked=bool(row[3]),
                    assigned_at=row[4]
                ))
        return proxies

    def get_or_assign_proxy(self, profile_id: str, profile_proxy: str = None) -> Optional[Proxy]:
        """
        Получить прокси для профиля или назначить новый.

        Логика:
        1. Проверяем БД - есть ли уже привязка?
        2. Если нет - используем profile_proxy из DonutBrowser
        3. Если profile_proxy нет - берём из резервного пула

        Args:
            profile_id: ID профиля
            profile_proxy: Прокси из профиля DonutBrowser (host:port:user:pass)

        Returns:
            Proxy (существующий или новый)
        """
        # 1. Проверяем существующую привязку в БД
        proxy = self.get_proxy_for_profile(profile_id)
        if proxy and proxy.is_healthy and not proxy.is_blocked:
            return proxy

        # 2. Если нет привязки - используем прокси из профиля DonutBrowser
        if profile_proxy:
            self._ensure_proxy_in_db(profile_proxy)
            self.assign_proxy(profile_id, profile_proxy)
            return Proxy(url=profile_proxy, profile_id=profile_id, is_healthy=True)

        # 3. Fallback - резервный пул
        available = self.get_available_proxy()
        if available:
            self.assign_proxy(profile_id, available.url)
            available.profile_id = profile_id
            return available

        # Если нет свободных - возвращаем текущий (даже если нездоровый)
        return proxy

    def rotate_proxy(self, profile_id: str) -> Optional[Proxy]:
        """
        Ротация прокси для профиля.
        Блокирует текущий прокси и назначает новый.

        Args:
            profile_id: ID профиля

        Returns:
            Новый Proxy или None если нет свободных
        """
        # Получаем текущий прокси
        current = self.get_proxy_for_profile(profile_id)
        if current:
            # Блокируем текущий
            self.mark_blocked(current.url)

        # Получаем новый из резервного пула
        new_proxy = self.get_available_proxy()
        if new_proxy:
            self.assign_proxy(profile_id, new_proxy.url)
            new_proxy.profile_id = profile_id
            return new_proxy

        return None


# Синглтон для глобального доступа
_proxy_manager: Optional[ProxyManager] = None


def get_proxy_manager() -> ProxyManager:
    """Получить глобальный экземпляр ProxyManager."""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
