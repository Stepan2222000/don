#!/bin/bash
# =============================================================================
# Скрипт установки зависимостей для tg-automatizamtion на Ubuntu сервере
# =============================================================================
# Использование: ./scripts/setup-server.sh
# Запускается автоматически при деплое или вручную при первой настройке
# =============================================================================

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Установка зависимостей для tg-automatizamtion            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# =============================================================================
# Проверка Python 3.11+
# =============================================================================
check_python() {
    log_info "Проверка Python..."

    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_OK=$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 11) else "no")')

        if [[ "$PYTHON_OK" == "yes" ]]; then
            log_info "Python $PYTHON_VERSION найден ✓"
            return 0
        else
            log_warn "Python $PYTHON_VERSION < 3.11, требуется обновление"
        fi
    else
        log_warn "Python не найден"
    fi

    return 1
}

install_python() {
    log_info "Установка Python 3.11..."

    apt update
    apt install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update
    apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

    # Устанавливаем python3.11 как python3 по умолчанию
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 || true

    log_info "Python 3.11 установлен ✓"
}

# =============================================================================
# Системные зависимости
# =============================================================================
install_system_deps() {
    log_info "Установка системных зависимостей..."

    apt update
    apt install -y \
        git \
        xvfb \
        libgtk-3-0 \
        libasound2 \
        libdbus-glib-1-2 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libxcursor1 \
        libxi6 \
        libxtst6 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libnss3 \
        libxss1 \
        fonts-liberation \
        libappindicator3-1 \
        libu2f-udev \
        libvulkan1 \
        jq \
        curl \
        wget

    log_info "Системные зависимости установлены ✓"
}

# =============================================================================
# Python зависимости
# =============================================================================
install_python_deps() {
    log_info "Установка Python зависимостей..."

    # Обновляем pip
    python3 -m pip install --upgrade pip

    # Устанавливаем зависимости
    python3 -m pip install playwright pyyaml

    log_info "Python зависимости установлены ✓"
}

# =============================================================================
# Playwright и браузер
# =============================================================================
install_playwright() {
    log_info "Установка Playwright и Firefox..."

    # Устанавливаем Firefox для Playwright
    python3 -m playwright install firefox

    # Устанавливаем системные зависимости для Playwright
    python3 -m playwright install-deps firefox || true

    log_info "Playwright установлен ✓"
}

# =============================================================================
# Директории для Donut Browser
# =============================================================================
create_directories() {
    log_info "Создание директорий для профилей..."

    mkdir -p ~/.local/share/DonutBrowserDev/profiles
    mkdir -p ~/.local/share/DonutBrowserDev/binaries

    log_info "Директории созданы ✓"
}

# =============================================================================
# Основная логика
# =============================================================================
main() {
    # Проверяем что запущены под root
    if [[ $EUID -ne 0 ]]; then
        log_error "Этот скрипт должен запускаться от root"
        exit 1
    fi

    # Python
    if ! check_python; then
        install_python
    fi

    # Системные зависимости
    install_system_deps

    # Python зависимости
    install_python_deps

    # Playwright
    install_playwright

    # Директории
    create_directories

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     Все зависимости установлены успешно!                     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # Показываем версии
    log_info "Python: $(python3 --version)"
    log_info "Playwright: $(python3 -m playwright --version 2>/dev/null || echo 'установлен')"
}

main "$@"
