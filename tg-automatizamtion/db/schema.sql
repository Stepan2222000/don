-- Telegram Automation System - Database Schema
-- SQLite database with WAL mode for concurrent access
-- Version: 2.0 - Added support for campaign groups
-- Date: 2024-11-15

-- Enable WAL mode for better concurrency
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- =====================================================
-- Table: profiles
-- Профили Donut Browser, участвующие в рассылке
-- =====================================================
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT UNIQUE NOT NULL,           -- UUID профиля Donut Browser
    profile_name TEXT NOT NULL,                -- Название профиля
    is_active BOOLEAN DEFAULT 1,               -- Участвует ли в рассылке
    is_blocked BOOLEAN DEFAULT 0,              -- Заблокирован ли Telegram в профиле
    messages_sent_current_hour INTEGER DEFAULT 0,
    hour_reset_time TIMESTAMP,                 -- Время сброса счетчика
    last_message_time TIMESTAMP,               -- Время последней отправки
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Table: tasks
-- Задача = работа с одним чатом (одна запись на чат)
-- Задача накапливает статистику по всем попыткам отправки
-- =====================================================
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,                    -- ID группы рассылки
    chat_username TEXT NOT NULL,               -- @username чата
    status TEXT DEFAULT 'pending',             -- pending/in_progress/completed/blocked
    assigned_profile_id TEXT,                  -- Текущий обработчик (NULL если свободна)

    -- Прогресс
    total_cycles INTEGER DEFAULT 1,            -- Сколько циклов нужно (из конфига)
    completed_cycles INTEGER DEFAULT 0,        -- Сколько циклов выполнено

    -- Статистика
    success_count INTEGER DEFAULT 0,           -- Успешных отправок
    failed_count INTEGER DEFAULT 0,            -- Неудачных попыток

    -- Флаги
    is_blocked BOOLEAN DEFAULT 0,              -- Навсегда заблокирована
    block_reason TEXT,                         -- Причина блокировки

    -- Времена
    last_attempt_at TIMESTAMP,                 -- Последняя попытка
    next_available_at TIMESTAMP,               -- Когда можно снова (для задержек)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Уникальность: один чат может быть в разных группах
    UNIQUE(group_id, chat_username)
);

CREATE INDEX IF NOT EXISTS idx_tasks_group_id ON tasks(group_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_next_available ON tasks(next_available_at);
CREATE INDEX IF NOT EXISTS idx_tasks_is_blocked ON tasks(is_blocked);
CREATE INDEX IF NOT EXISTS idx_tasks_group_status ON tasks(group_id, status);

-- =====================================================
-- Table: task_attempts
-- История всех попыток отправки (детали каждой отправки)
-- =====================================================
CREATE TABLE IF NOT EXISTS task_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,                  -- FK -> tasks.id
    profile_id TEXT NOT NULL,                  -- Кто отправлял
    cycle_number INTEGER NOT NULL,             -- Номер цикла (1, 2, 3...)
    status TEXT NOT NULL,                      -- success/failed
    message_text TEXT,                         -- Отправленное сообщение
    error_type TEXT,                           -- chat_not_found/send_error/blocked/etc
    error_message TEXT,                        -- Детали ошибки
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attempts_task_id ON task_attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON task_attempts(status);
CREATE INDEX IF NOT EXISTS idx_attempts_timestamp ON task_attempts(timestamp);

-- =====================================================
-- Table: messages
-- Шаблоны сообщений для рассылки
-- =====================================================
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,                    -- ID группы рассылки
    text TEXT NOT NULL,                        -- Текст сообщения
    is_active BOOLEAN DEFAULT 1,               -- Используется ли в рассылке
    usage_count INTEGER DEFAULT 0,             -- Сколько раз использовано
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_group_id ON messages(group_id);
CREATE INDEX IF NOT EXISTS idx_messages_group_active ON messages(group_id, is_active);

-- =====================================================
-- Table: send_log
-- Общий лог всех отправок (для быстрого поиска и аналитики)
-- =====================================================
CREATE TABLE IF NOT EXISTS send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,                           -- FK -> tasks.id (NULL если задача удалена)
    group_id TEXT NOT NULL,                    -- ID группы рассылки
    profile_id TEXT NOT NULL,
    chat_username TEXT NOT NULL,
    message_text TEXT,
    status TEXT NOT NULL,                      -- success/failed
    error_type TEXT,                           -- chat_not_found/send_error/blocked/etc
    error_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_send_log_group_id ON send_log(group_id);
CREATE INDEX IF NOT EXISTS idx_send_log_status ON send_log(status);
CREATE INDEX IF NOT EXISTS idx_send_log_timestamp ON send_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_send_log_chat ON send_log(chat_username);
CREATE INDEX IF NOT EXISTS idx_send_log_profile_time ON send_log(profile_id, timestamp);

-- =====================================================
-- Table: profile_daily_stats
-- Статистика отправленных сообщений по профилям за день
-- Используется для отслеживания активности профилей
-- =====================================================
CREATE TABLE IF NOT EXISTS profile_daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    date DATE NOT NULL,                        -- Дата (YYYY-MM-DD)
    messages_sent INTEGER DEFAULT 0,           -- Отправлено сообщений за день
    successful_sends INTEGER DEFAULT 0,        -- Успешных отправок
    failed_sends INTEGER DEFAULT 0,            -- Неудачных отправок
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(profile_id, date)
);

CREATE INDEX IF NOT EXISTS idx_profile_daily_stats_profile ON profile_daily_stats(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_daily_stats_date ON profile_daily_stats(date);
CREATE INDEX IF NOT EXISTS idx_profile_daily_stats_profile_date ON profile_daily_stats(profile_id, date);

-- =====================================================
-- Table: screenshots
-- Скриншоты при ошибках и для отладки
-- =====================================================
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER,                            -- FK -> send_log.id (NULL для отладочных)
    screenshot_type TEXT NOT NULL,             -- error/warning/debug
    file_name TEXT NOT NULL,                   -- Имя файла
    description TEXT,                          -- Описание
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (log_id) REFERENCES send_log(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_screenshots_log_id ON screenshots(log_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_type ON screenshots(screenshot_type);
CREATE INDEX IF NOT EXISTS idx_screenshots_created ON screenshots(created_at);

-- =====================================================
-- Views для удобного доступа к данным
-- =====================================================

-- Статистика по профилям (общая)
CREATE VIEW IF NOT EXISTS profile_stats AS
SELECT
    p.profile_id,
    p.profile_name,
    p.is_active,
    p.is_blocked,
    COUNT(DISTINCT ta.task_id) as tasks_processed,
    SUM(CASE WHEN ta.status = 'success' THEN 1 ELSE 0 END) as successful_sends,
    SUM(CASE WHEN ta.status = 'failed' THEN 1 ELSE 0 END) as failed_sends,
    p.last_message_time
FROM profiles p
LEFT JOIN task_attempts ta ON ta.profile_id = p.profile_id
GROUP BY p.profile_id, p.profile_name, p.is_active, p.is_blocked, p.last_message_time;

-- Прогресс по задачам
CREATE VIEW IF NOT EXISTS task_progress AS
SELECT
    t.group_id,
    t.chat_username,
    t.status,
    t.completed_cycles,
    t.total_cycles,
    ROUND(CAST(t.completed_cycles AS FLOAT) / CAST(t.total_cycles AS FLOAT) * 100, 2) as progress_percent,
    t.success_count,
    t.failed_count,
    t.last_attempt_at,
    t.assigned_profile_id
FROM tasks t;

-- Статистика по группам
CREATE VIEW IF NOT EXISTS group_stats AS
SELECT
    t.group_id,
    COUNT(*) as total_tasks,
    SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending_tasks,
    SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
    SUM(CASE WHEN t.is_blocked = 1 THEN 1 ELSE 0 END) as blocked_tasks,
    SUM(t.success_count) as total_successful_sends,
    SUM(t.failed_count) as total_failed_sends,
    (SELECT COUNT(*) FROM messages m WHERE m.group_id = t.group_id AND m.is_active = 1) as message_templates_count
FROM tasks t
GROUP BY t.group_id;

-- =====================================================
-- Initial data / примеры (опционально)
-- =====================================================

-- Можно добавить здесь примеры сообщений, если нужно
