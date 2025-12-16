"""
Proxy Manager - async управление пулом прокси и привязками к профилям.

Функции:
- Загрузка прокси из текстового файла (резервный пул)
- Привязка прокси к профилям в БД
- Ротация прокси при проблемах
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

from .config import load_config, get_config
from .database import get_database, AsyncDatabase


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


class AsyncProxyManager:
    """Async управление пулом прокси и привязками."""

    def __init__(self, db: AsyncDatabase, pool_file: str = None):
        """
        Инициализация менеджера прокси.

        Args:
            db: AsyncDatabase instance
            pool_file: Путь к файлу с резервными прокси (по умолчанию из конфига)
        """
        try:
            config = get_config()
        except RuntimeError:
            config = load_config()

        self.pool_file = pool_file or config.proxy.absolute_pool_path
        self._db = db

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

    async def sync_reserve_proxies(self) -> tuple:
        """
        Синхронизировать резервные прокси из файла в БД.
        Добавляет новые прокси, не трогает существующие.

        Returns:
            (added_count, total_in_file)
        """
        file_proxies = self.load_proxies_from_file()
        added = await self._db.sync_proxies_from_file(file_proxies)
        return added, len(file_proxies)

    async def get_proxy_for_profile(self, profile_id: str) -> Optional[Proxy]:
        """
        Получить прокси привязанный к профилю.

        Args:
            profile_id: ID профиля

        Returns:
            Proxy если есть привязка, иначе None
        """
        proxy_url = await self._db.get_proxy_for_profile(profile_id)
        if proxy_url:
            return Proxy(url=proxy_url, profile_id=profile_id, is_healthy=True)
        return None

    async def get_available_proxy(self) -> Optional[Proxy]:
        """
        Получить свободный здоровый прокси из резервного пула.

        Returns:
            Proxy если есть свободный, иначе None
        """
        proxy_url = await self._db.get_available_proxy()
        if proxy_url:
            return Proxy(url=proxy_url, profile_id=None, is_healthy=True)
        return None

    async def assign_proxy(self, profile_id: str, proxy_url: str):
        """
        Привязать прокси к профилю.

        Args:
            profile_id: ID профиля
            proxy_url: URL прокси
        """
        await self._db.assign_proxy(proxy_url, profile_id)

    async def release_proxy(self, profile_id: str):
        """
        Освободить прокси (убрать привязку).

        Args:
            profile_id: ID профиля
        """
        await self._db.release_proxy(profile_id)

    async def mark_unhealthy(self, proxy_url: str):
        """
        Пометить прокси как нездоровый.

        Args:
            proxy_url: URL прокси
        """
        await self._db.mark_proxy_unhealthy(proxy_url)

    async def mark_blocked(self, proxy_url: str):
        """
        Пометить прокси как заблокированный.

        Args:
            proxy_url: URL прокси
        """
        await self._db.mark_proxy_blocked(proxy_url)

    async def get_all_proxies(self) -> List[Proxy]:
        """Получить все прокси."""
        rows = await self._db.get_all_proxies()
        proxies = []
        for row in rows:
            proxies.append(Proxy(
                url=row['proxy_url'],
                profile_id=row.get('profile_id'),
                is_healthy=row.get('is_healthy', True),
                is_blocked=row.get('is_blocked', False),
                assigned_at=str(row['assigned_at']) if row.get('assigned_at') else None
            ))
        return proxies

    async def get_or_assign_proxy(self, profile_id: str, profile_proxy: str = None) -> Optional[Proxy]:
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
        proxy = await self.get_proxy_for_profile(profile_id)
        if proxy and proxy.is_healthy and not proxy.is_blocked:
            return proxy

        # 2. Если нет привязки - используем прокси из профиля DonutBrowser
        if profile_proxy:
            await self._db.sync_proxies_from_file([profile_proxy])
            await self.assign_proxy(profile_id, profile_proxy)
            return Proxy(url=profile_proxy, profile_id=profile_id, is_healthy=True)

        # 3. Fallback - резервный пул
        available = await self.get_available_proxy()
        if available:
            await self.assign_proxy(profile_id, available.url)
            available.profile_id = profile_id
            return available

        # Если нет свободных - возвращаем текущий (даже если нездоровый)
        return proxy

    async def rotate_proxy(self, profile_id: str) -> Optional[Proxy]:
        """
        Ротация прокси для профиля.
        Блокирует текущий прокси и назначает новый.

        Args:
            profile_id: ID профиля

        Returns:
            Новый Proxy или None если нет свободных
        """
        # Получаем текущий прокси
        current = await self.get_proxy_for_profile(profile_id)
        if current:
            # Блокируем текущий
            await self.mark_blocked(current.url)

        # Получаем новый из резервного пула
        new_proxy = await self.get_available_proxy()
        if new_proxy:
            await self.assign_proxy(profile_id, new_proxy.url)
            new_proxy.profile_id = profile_id
            return new_proxy

        return None


# Синглтон для глобального доступа
_proxy_manager: Optional[AsyncProxyManager] = None


def get_proxy_manager() -> AsyncProxyManager:
    """Получить глобальный экземпляр AsyncProxyManager."""
    global _proxy_manager
    if _proxy_manager is None:
        db = get_database()
        _proxy_manager = AsyncProxyManager(db)
    return _proxy_manager


def init_proxy_manager(db: AsyncDatabase, pool_file: str = None) -> AsyncProxyManager:
    """Инициализировать глобальный экземпляр AsyncProxyManager."""
    global _proxy_manager
    _proxy_manager = AsyncProxyManager(db, pool_file)
    return _proxy_manager
