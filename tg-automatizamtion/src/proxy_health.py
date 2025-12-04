"""
Proxy Health Monitor - мониторинг здоровья прокси и автоматическая ротация.

Функции:
- Запись попыток отправки
- Расчёт chat_not_found rate
- Автоматическая ротация при превышении порога
- Разблокировка задач при ротации
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

from .config import load_config, get_config
from .proxy_manager import ProxyManager, get_proxy_manager

logger = logging.getLogger('tg_automation.proxy_health')


@dataclass
class ProxyStats:
    """Статистика прокси."""
    proxy_url: str
    profile_id: str
    total_attempts: int = 0
    successful_sends: int = 0
    chat_not_found: int = 0
    other_errors: int = 0

    @property
    def chat_not_found_rate(self) -> float:
        """Процент chat_not_found ошибок."""
        if self.total_attempts == 0:
            return 0.0
        return (self.chat_not_found / self.total_attempts) * 100

    @property
    def success_rate(self) -> float:
        """Процент успешных отправок."""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful_sends / self.total_attempts) * 100


class ProxyHealthMonitor:
    """Мониторинг здоровья прокси и автоматическая ротация."""

    def __init__(self, db_path: str = None):
        """
        Инициализация монитора.

        Args:
            db_path: Путь к БД (по умолчанию из конфига)
        """
        try:
            self.config = get_config()
        except RuntimeError:
            self.config = load_config()

        self.db_path = db_path or self.config.database.absolute_path
        self.proxy_manager = get_proxy_manager()

        # Параметры из конфига
        self.min_attempts = self.config.proxy.min_attempts_for_check
        self.threshold = self.config.proxy.chat_not_found_threshold
        self.unblock_on_rotate = self.config.proxy.unblock_tasks_on_rotate
        self.health_reset_hours = self.config.proxy.health_reset_hours

    def _get_connection(self) -> sqlite3.Connection:
        """Получить соединение с БД."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_attempt(self, proxy_url: str, profile_id: str,
                       status: str, error_type: Optional[str] = None):
        """
        Записать попытку отправки.

        Args:
            proxy_url: URL прокси
            profile_id: ID профиля
            status: "success" или "failed"
            error_type: Тип ошибки (chat_not_found, send_error, etc.)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()

            # Проверяем существует ли запись
            cursor.execute("""
                SELECT id FROM proxy_stats
                WHERE proxy_url = ? AND profile_id = ?
            """, (proxy_url, profile_id))

            if cursor.fetchone():
                # Обновляем существующую
                if status == "success":
                    cursor.execute("""
                        UPDATE proxy_stats
                        SET total_attempts = total_attempts + 1,
                            successful_sends = successful_sends + 1,
                            last_attempt_at = ?
                        WHERE proxy_url = ? AND profile_id = ?
                    """, (now, proxy_url, profile_id))
                else:
                    if error_type == "chat_not_found":
                        cursor.execute("""
                            UPDATE proxy_stats
                            SET total_attempts = total_attempts + 1,
                                chat_not_found = chat_not_found + 1,
                                last_attempt_at = ?
                            WHERE proxy_url = ? AND profile_id = ?
                        """, (now, proxy_url, profile_id))
                    else:
                        cursor.execute("""
                            UPDATE proxy_stats
                            SET total_attempts = total_attempts + 1,
                                other_errors = other_errors + 1,
                                last_attempt_at = ?
                            WHERE proxy_url = ? AND profile_id = ?
                        """, (now, proxy_url, profile_id))
            else:
                # Создаём новую запись
                successful = 1 if status == "success" else 0
                chat_not_found = 1 if error_type == "chat_not_found" else 0
                other_errors = 1 if status == "failed" and error_type != "chat_not_found" else 0

                cursor.execute("""
                    INSERT INTO proxy_stats
                    (proxy_url, profile_id, total_attempts, successful_sends,
                     chat_not_found, other_errors, last_attempt_at)
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                """, (proxy_url, profile_id, successful, chat_not_found,
                      other_errors, now))

            conn.commit()
        finally:
            conn.close()

    def get_stats(self, proxy_url: str, profile_id: str) -> Optional[ProxyStats]:
        """
        Получить статистику прокси для профиля.

        Args:
            proxy_url: URL прокси
            profile_id: ID профиля

        Returns:
            ProxyStats или None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT proxy_url, profile_id, total_attempts,
                       successful_sends, chat_not_found, other_errors
                FROM proxy_stats
                WHERE proxy_url = ? AND profile_id = ?
            """, (proxy_url, profile_id))

            row = cursor.fetchone()
            if row:
                return ProxyStats(
                    proxy_url=row['proxy_url'],
                    profile_id=row['profile_id'],
                    total_attempts=row['total_attempts'],
                    successful_sends=row['successful_sends'],
                    chat_not_found=row['chat_not_found'],
                    other_errors=row['other_errors']
                )
            return None
        finally:
            conn.close()

    def should_rotate(self, proxy_url: str, profile_id: str) -> bool:
        """
        Проверить нужна ли ротация прокси.

        Args:
            proxy_url: URL прокси
            profile_id: ID профиля

        Returns:
            True если нужна ротация
        """
        stats = self.get_stats(proxy_url, profile_id)

        if not stats:
            return False

        # Недостаточно попыток для анализа
        if stats.total_attempts < self.min_attempts:
            return False

        # Проверяем порог chat_not_found
        if stats.chat_not_found_rate > self.threshold:
            logger.warning(
                f"Прокси {proxy_url[:20]}... превысил порог: "
                f"{stats.chat_not_found_rate:.1f}% > {self.threshold}%"
            )
            return True

        return False

    def rotate_proxy(self, profile_id: str) -> Optional[str]:
        """
        Выполнить ротацию прокси для профиля.

        1. Помечает текущий прокси как unhealthy
        2. Получает новый прокси из пула
        3. Назначает профилю
        4. Разблокирует задачи (если включено)
        5. Сбрасывает статистику

        Args:
            profile_id: ID профиля

        Returns:
            Новый proxy_url или None если нет доступных
        """
        # Получаем текущий прокси
        current = self.proxy_manager.get_proxy_for_profile(profile_id)
        if not current:
            logger.error(f"Нет текущего прокси для профиля {profile_id}")
            return None

        old_proxy_url = current.url
        logger.info(f"Начинаем ротацию прокси для профиля {profile_id}")

        # 1. Помечаем текущий как unhealthy
        self.proxy_manager.mark_unhealthy(old_proxy_url)
        logger.info(f"Прокси {old_proxy_url[:20]}... помечен как unhealthy")

        # 2. Получаем новый прокси
        new_proxy = self.proxy_manager.get_available_proxy()
        if not new_proxy:
            logger.error("Нет доступных прокси в пуле!")
            return None

        # 3. Назначаем профилю
        self.proxy_manager.assign_proxy(profile_id, new_proxy.url)
        logger.info(f"Новый прокси назначен: {new_proxy.url[:20]}...")

        # 4. Разблокируем задачи
        if self.unblock_on_rotate:
            unblocked = self._unblock_tasks_for_profile(profile_id)
            logger.info(f"Разблокировано {unblocked} задач")

        # 5. Сбрасываем статистику
        self._reset_stats(new_proxy.url, profile_id)

        return new_proxy.url

    def _unblock_tasks_for_profile(self, profile_id: str) -> int:
        """
        Разблокировать все задачи для профиля.

        При ротации прокси даём чатам ещё один шанс.

        Args:
            profile_id: ID профиля

        Returns:
            Количество разблокированных задач
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Разблокируем все задачи с block_reason = 'chat_not_found'
            cursor.execute("""
                UPDATE tasks
                SET is_blocked = 0, status = 'pending', block_reason = NULL
                WHERE is_blocked = 1
                AND block_reason = 'chat_not_found'
            """)

            affected = cursor.rowcount
            conn.commit()
            return affected
        finally:
            conn.close()

    def _reset_stats(self, proxy_url: str, profile_id: str):
        """
        Сбросить статистику для пары прокси+профиль.

        Args:
            proxy_url: URL прокси
            profile_id: ID профиля
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()
            cursor.execute("""
                DELETE FROM proxy_stats
                WHERE proxy_url = ? AND profile_id = ?
            """, (proxy_url, profile_id))
            conn.commit()
        finally:
            conn.close()

    def check_and_rotate_if_needed(self, proxy_url: str, profile_id: str) -> Optional[str]:
        """
        Проверить здоровье прокси и выполнить ротацию если нужно.

        Args:
            proxy_url: URL прокси
            profile_id: ID профиля

        Returns:
            Новый proxy_url если была ротация, иначе None
        """
        if self.should_rotate(proxy_url, profile_id):
            return self.rotate_proxy(profile_id)
        return None

    def reset_unhealthy_proxies(self) -> int:
        """
        Сбросить unhealthy статус для старых прокси.

        Returns:
            Количество сброшенных прокси
        """
        return self.proxy_manager.reset_unhealthy_proxies(self.health_reset_hours)


# Синглтон для глобального доступа
_health_monitor: Optional[ProxyHealthMonitor] = None


def get_health_monitor() -> ProxyHealthMonitor:
    """Получить глобальный экземпляр ProxyHealthMonitor."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = ProxyHealthMonitor()
    return _health_monitor
