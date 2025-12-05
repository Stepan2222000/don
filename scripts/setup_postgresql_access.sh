#!/bin/bash
# =============================================================================
# Скрипт настройки PostgreSQL для удалённого доступа
# Запускай на СЕРВЕРЕ (81.30.105.134)
# =============================================================================

echo "========================================="
echo "Настройка PostgreSQL для удалённого доступа"
echo "========================================="

# Найти pg_hba.conf
PG_HBA=$(find /etc/postgresql /var/lib/pgsql 2>/dev/null -name "pg_hba.conf" | head -1)

if [ -z "$PG_HBA" ]; then
    echo "❌ pg_hba.conf не найден!"
    echo "Попробуй: sudo find / -name pg_hba.conf 2>/dev/null"
    exit 1
fi

echo "Найден: $PG_HBA"

# Проверить есть ли уже правило
if grep -q "telegram_ras.*admin" "$PG_HBA"; then
    echo "✅ Правило уже существует"
else
    echo "Добавляю правило для удалённого доступа..."
    echo "" | sudo tee -a "$PG_HBA"
    echo "# Remote access for Telegram Automation" | sudo tee -a "$PG_HBA"
    echo "host    telegram_ras    admin    0.0.0.0/0    md5" | sudo tee -a "$PG_HBA"
    echo "✅ Правило добавлено"
fi

# Перезапустить PostgreSQL
echo "Перезагружаю PostgreSQL..."
if command -v systemctl &> /dev/null; then
    sudo systemctl reload postgresql
elif command -v service &> /dev/null; then
    sudo service postgresql reload
else
    echo "⚠️ Не могу перезагрузить PostgreSQL автоматически"
    echo "Выполни вручную: sudo systemctl reload postgresql"
fi

echo ""
echo "========================================="
echo "Готово! Теперь можно подключаться удалённо."
echo "========================================="
