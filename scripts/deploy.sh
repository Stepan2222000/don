#!/bin/bash
# =============================================================================
# Скрипт деплоя - запускается на сервере при пуше в master
# =============================================================================
# Использование: ./scripts/deploy.sh
# Вызывается автоматически из GitHub Actions
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    Деплой tg-automatizamtion                 ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

cd "$PROJECT_DIR"

# =============================================================================
# 1. Обновление кода
# =============================================================================
log_info "Обновление кода из репозитория..."

git fetch origin
git reset --hard origin/master

log_info "Код обновлён ✓"

# =============================================================================
# 2. Проверка зависимостей (только если setup-server.sh изменился или первый запуск)
# =============================================================================
SETUP_SCRIPT="$SCRIPT_DIR/setup-server.sh"
SETUP_MARKER="$PROJECT_DIR/.setup-done"

# Проверяем нужно ли запускать setup
RUN_SETUP=false

if [[ ! -f "$SETUP_MARKER" ]]; then
    log_info "Первый запуск - требуется установка зависимостей"
    RUN_SETUP=true
elif [[ "$SETUP_SCRIPT" -nt "$SETUP_MARKER" ]]; then
    log_info "setup-server.sh обновлён - перезапускаем установку"
    RUN_SETUP=true
fi

if [[ "$RUN_SETUP" == "true" ]]; then
    log_info "Запуск установки зависимостей..."
    chmod +x "$SETUP_SCRIPT"
    "$SETUP_SCRIPT"
    touch "$SETUP_MARKER"
else
    log_info "Зависимости актуальны, пропускаем установку ✓"
fi

# =============================================================================
# 3. Обновление Python зависимостей (если requirements.txt изменился)
# =============================================================================
REQUIREMENTS="$PROJECT_DIR/tg-automatizamtion/requirements.txt"
REQ_MARKER="$PROJECT_DIR/.requirements-done"

if [[ -f "$REQUIREMENTS" ]]; then
    if [[ ! -f "$REQ_MARKER" ]] || [[ "$REQUIREMENTS" -nt "$REQ_MARKER" ]]; then
        log_info "Обновление Python зависимостей..."
        python3 -m pip install -r "$REQUIREMENTS" --quiet
        touch "$REQ_MARKER"
        log_info "Python зависимости обновлены ✓"
    else
        log_info "Python зависимости актуальны ✓"
    fi
fi

# =============================================================================
# 4. Проверка запущенной автоматизации
# =============================================================================
log_info "Проверка запущенных процессов..."

# Ищем запущенные процессы worker.py
WORKER_PIDS=$(pgrep -f "python.*src\.worker" 2>/dev/null || true)
MAIN_PIDS=$(pgrep -f "python.*src\.main" 2>/dev/null || true)

if [[ -n "$WORKER_PIDS" ]] || [[ -n "$MAIN_PIDS" ]]; then
    log_warn "Найдены запущенные процессы автоматизации"

    if [[ -n "$WORKER_PIDS" ]]; then
        echo "  Воркеры: $WORKER_PIDS"
    fi
    if [[ -n "$MAIN_PIDS" ]]; then
        echo "  Main: $MAIN_PIDS"
    fi

    log_warn "Останавливаем процессы..."

    # Отправляем SIGTERM для graceful shutdown
    if [[ -n "$MAIN_PIDS" ]]; then
        kill $MAIN_PIDS 2>/dev/null || true
    fi
    if [[ -n "$WORKER_PIDS" ]]; then
        kill $WORKER_PIDS 2>/dev/null || true
    fi

    # Ждём завершения
    sleep 3

    # Проверяем что процессы завершились
    REMAINING=$(pgrep -f "python.*src\.(worker|main)" 2>/dev/null || true)
    if [[ -n "$REMAINING" ]]; then
        log_warn "Процессы не завершились, принудительное завершение..."
        kill -9 $REMAINING 2>/dev/null || true
        sleep 1
    fi

    log_info "Процессы остановлены"
    echo ""
    log_warn "ВАЖНО: Запустите автоматизацию вручную:"
    echo "  cd $PROJECT_DIR/tg-automatizamtion"
    echo "  python scripts/start_automation.py <group_id>"
    echo ""
else
    log_info "Запущенных процессов автоматизации не найдено ✓"
fi

# =============================================================================
# Готово
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Деплой завершён успешно!                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Время: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
