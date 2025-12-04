-- Миграция: Система управления прокси
-- Дата: 2025-12-04

-- Таблица привязок прокси к профилям (sticky assignment)
CREATE TABLE IF NOT EXISTS proxy_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_url TEXT NOT NULL UNIQUE,           -- host:port:user:pass
    profile_id TEXT,                          -- К какому профилю привязан (NULL = свободен)
    is_healthy BOOLEAN DEFAULT 1,             -- Здоров ли прокси
    assigned_at TIMESTAMP,                    -- Когда привязали
    last_rotation_at TIMESTAMP,               -- Когда последний раз ротировали
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица статистики прокси
CREATE TABLE IF NOT EXISTS proxy_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_url TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    successful_sends INTEGER DEFAULT 0,
    chat_not_found INTEGER DEFAULT 0,
    other_errors INTEGER DEFAULT 0,
    period_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMP,
    UNIQUE(proxy_url, profile_id)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_proxy_assignments_profile ON proxy_assignments(profile_id);
CREATE INDEX IF NOT EXISTS idx_proxy_assignments_healthy ON proxy_assignments(is_healthy);
CREATE INDEX IF NOT EXISTS idx_proxy_stats_profile ON proxy_stats(profile_id);
CREATE INDEX IF NOT EXISTS idx_proxy_stats_proxy ON proxy_stats(proxy_url);

-- View для отображения статистики прокси
CREATE VIEW IF NOT EXISTS proxy_health_view AS
SELECT
    pa.proxy_url,
    pa.profile_id,
    pa.is_healthy,
    pa.assigned_at,
    ps.total_attempts,
    ps.successful_sends,
    ps.chat_not_found,
    ps.other_errors,
    CASE
        WHEN ps.total_attempts > 0
        THEN ROUND(ps.chat_not_found * 100.0 / ps.total_attempts, 1)
        ELSE 0
    END as chat_not_found_rate,
    CASE
        WHEN ps.total_attempts > 0
        THEN ROUND(ps.successful_sends * 100.0 / ps.total_attempts, 1)
        ELSE 0
    END as success_rate
FROM proxy_assignments pa
LEFT JOIN proxy_stats ps ON pa.proxy_url = ps.proxy_url AND pa.profile_id = ps.profile_id;
