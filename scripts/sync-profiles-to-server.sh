#!/bin/bash

# ============================================================================
# Скрипт переноса профилей Donut Browser на удалённый сервер
# ============================================================================
# Использование: ./sync-profiles-to-server.sh
# Зависимости: sshpass (brew install hudochenkov/sshpass/sshpass)
# ============================================================================

set -e

# === КОНФИГУРАЦИЯ (можно изменить) ===
LOCAL_PROFILES_DIR="$HOME/Library/Application Support/DonutBrowserDev/profiles"
REMOTE_PROFILES_DIR="\$HOME/.local/share/DonutBrowserDev/profiles"
REMOTE_BINARIES_DIR="\$HOME/.local/share/DonutBrowserDev/binaries"
# =====================================

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Глобальные переменные
SERVER_IP=""
SERVER_USER=""
SERVER_PASS=""
REMOTE_HOME=""

# Логирование
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка зависимостей
check_dependencies() {
    if ! command -v sshpass &> /dev/null; then
        log_error "sshpass не установлен!"
        echo ""
        echo "Установите его командой:"
        echo "  brew install hudochenkov/sshpass/sshpass"
        echo ""
        exit 1
    fi
}

# SSH команда с паролем
ssh_cmd() {
    sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER_USER@$SERVER_IP" "$1"
}

# SCP команда с паролем
scp_cmd() {
    sshpass -p "$SERVER_PASS" scp -o StrictHostKeyChecking=no -r "$1" "$SERVER_USER@$SERVER_IP:$2"
}

# Rsync команда с паролем (если доступен)
rsync_cmd() {
    if command -v rsync &> /dev/null; then
        sshpass -p "$SERVER_PASS" rsync -avz --progress --exclude='cache2/' --exclude='.parentlock' \
            -e "ssh -o StrictHostKeyChecking=no" "$1" "$SERVER_USER@$SERVER_IP:$2"
        return 0
    else
        return 1
    fi
}

# Запрос данных сервера
prompt_server_credentials() {
    echo -e "${CYAN}=== Подключение к серверу ===${NC}"
    echo ""

    read -p "IP адрес сервера: " SERVER_IP
    read -p "Логин: " SERVER_USER
    read -s -p "Пароль: " SERVER_PASS
    echo ""
    echo ""
}

# Проверка подключения
test_connection() {
    log_info "Проверка подключения к $SERVER_USER@$SERVER_IP..."

    if ! ssh_cmd "echo 'OK'" &> /dev/null; then
        log_error "Не удалось подключиться к серверу!"
        exit 1
    fi

    # Получаем home директорию на сервере
    REMOTE_HOME=$(ssh_cmd "echo \$HOME")
    log_success "Подключение установлено (HOME: $REMOTE_HOME)"
}

# Проверка/создание директорий на сервере
check_remote_dirs() {
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"

    log_info "Проверка директории на сервере: $remote_profiles_expanded"

    if ! ssh_cmd "test -d $remote_profiles_expanded"; then
        log_warning "Директория не существует на сервере!"
        read -p "Создать директорию? (y/n): " create_dir

        if [[ "$create_dir" == "y" || "$create_dir" == "Y" ]]; then
            ssh_cmd "mkdir -p $remote_profiles_expanded"
            log_success "Директория создана"
        else
            log_error "Отмена операции"
            exit 1
        fi
    else
        log_success "Директория существует"
    fi
}

# Получение списка локальных профилей
get_local_profiles() {
    local profiles=()

    if [[ ! -d "$LOCAL_PROFILES_DIR" ]]; then
        log_error "Локальная директория профилей не найдена: $LOCAL_PROFILES_DIR"
        exit 1
    fi

    for dir in "$LOCAL_PROFILES_DIR"/*/; do
        if [[ -d "$dir" && -f "${dir}metadata.json" ]]; then
            local uuid=$(basename "$dir")
            local name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "${dir}metadata.json" | sed 's/"name"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            profiles+=("$uuid|$name")
        fi
    done

    echo "${profiles[@]}"
}

# Получение списка профилей на сервере
get_remote_profiles() {
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    local profiles=""

    profiles=$(ssh_cmd "ls -1 $remote_profiles_expanded 2>/dev/null || echo ''")
    echo "$profiles"
}

# Отображение меню
show_menu() {
    echo ""
    echo -e "${CYAN}=== Режим копирования ===${NC}"
    echo ""
    echo "  1) Все профили (полная замена на сервере)"
    echo "  2) Только новые профили (которых нет на сервере)"
    echo "  3) Выбрать конкретные профили (с заменой)"
    echo "  4) Выбрать конкретные профили (только если их нет)"
    echo "  0) Выход"
    echo ""
    read -p "Выберите режим [1-4]: " mode
    echo "$mode"
}

# Отображение списка профилей для выбора
select_profiles() {
    local profiles_str="$1"
    local filter_existing="$2"  # "yes" или "no"
    local remote_profiles="$3"

    IFS=' ' read -ra profiles <<< "$profiles_str"
    local selected=()

    echo ""
    echo -e "${CYAN}=== Доступные профили ===${NC}"
    echo ""

    local idx=1
    local display_profiles=()

    for profile in "${profiles[@]}"; do
        local uuid="${profile%%|*}"
        local name="${profile##*|}"
        local status=""

        if echo "$remote_profiles" | grep -q "^${uuid}$"; then
            if [[ "$filter_existing" == "yes" ]]; then
                continue  # Пропускаем существующие
            fi
            status="${YELLOW}(существует на сервере)${NC}"
        else
            status="${GREEN}(новый)${NC}"
        fi

        display_profiles+=("$profile")
        echo -e "  $idx) $name ${BLUE}[$uuid]${NC} $status"
        ((idx++))
    done

    if [[ ${#display_profiles[@]} -eq 0 ]]; then
        log_warning "Нет профилей для копирования"
        return
    fi

    echo ""
    echo "  a) Выбрать все"
    echo "  0) Отмена"
    echo ""
    read -p "Введите номера через пробел (например: 1 3 5) или 'a' для всех: " selection

    if [[ "$selection" == "0" ]]; then
        return
    fi

    if [[ "$selection" == "a" || "$selection" == "A" ]]; then
        for profile in "${display_profiles[@]}"; do
            echo "${profile%%|*}"
        done
        return
    fi

    for num in $selection; do
        if [[ "$num" =~ ^[0-9]+$ ]] && [[ $num -ge 1 ]] && [[ $num -le ${#display_profiles[@]} ]]; then
            local profile="${display_profiles[$((num-1))]}"
            echo "${profile%%|*}"
        fi
    done
}

# Копирование одного профиля
copy_profile() {
    local uuid="$1"
    local local_path="$LOCAL_PROFILES_DIR/$uuid"
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    local remote_path="$remote_profiles_expanded/$uuid"

    local name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "${local_path}/metadata.json" | sed 's/"name"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')

    log_info "Копирование профиля: $name [$uuid]"

    # Удаляем .parentlock локально перед копированием
    rm -f "$local_path/profile/.parentlock" 2>/dev/null || true

    # Копируем через rsync (если есть) или scp
    if rsync_cmd "$local_path/" "$remote_path/"; then
        log_success "Профиль скопирован через rsync"
    else
        log_info "rsync недоступен, используем scp..."
        scp_cmd "$local_path" "$remote_profiles_expanded/"
        log_success "Профиль скопирован через scp"
    fi

    # Удаляем .parentlock на сервере (на всякий случай)
    ssh_cmd "rm -f '$remote_path/profile/.parentlock'" 2>/dev/null || true

    # Адаптируем пути
    adapt_paths "$uuid"
}

# Адаптация путей в конфигах на сервере
adapt_paths() {
    local uuid="$1"
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    local remote_binaries_expanded="${REMOTE_BINARIES_DIR//\$HOME/$REMOTE_HOME}"
    local remote_path="$remote_profiles_expanded/$uuid"

    log_info "Адаптация путей для Linux..."

    # Получаем версию браузера из metadata.json
    local version=$(ssh_cmd "grep -o '\"version\"[[:space:]]*:[[:space:]]*\"[^\"]*\"' '$remote_path/metadata.json' | sed 's/\"version\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\"/\1/'")

    # Обновляем executable_path в metadata.json
    local new_executable="$remote_binaries_expanded/camoufox/$version/camoufox"

    ssh_cmd "sed -i 's|\"executable_path\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"executable_path\": \"$new_executable\"|g' '$remote_path/metadata.json'"

    # Обновляем путь к proxy.pac в user.js (если файл существует)
    local new_proxy_path="file://$remote_path/proxy.pac"

    ssh_cmd "if [ -f '$remote_path/profile/user.js' ]; then sed -i 's|file://[^\"]*proxy.pac|$new_proxy_path|g' '$remote_path/profile/user.js'; fi"

    log_success "Пути адаптированы"
}

# Основная функция
main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     Donut Browser - Синхронизация профилей на сервер       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Проверка зависимостей
    check_dependencies

    # Запрос данных сервера
    prompt_server_credentials

    # Проверка подключения
    test_connection

    # Проверка директорий
    check_remote_dirs

    # Получаем списки профилей
    log_info "Сканирование профилей..."
    local local_profiles=$(get_local_profiles)
    local remote_profiles=$(get_remote_profiles)

    local local_count=$(echo "$local_profiles" | wc -w | tr -d ' ')
    local remote_count=$(echo "$remote_profiles" | grep -c . || echo "0")

    echo ""
    log_info "Локальных профилей: $local_count"
    log_info "Профилей на сервере: $remote_count"

    # Показываем меню
    local mode=$(show_menu)

    local profiles_to_copy=()

    case $mode in
        1)
            # Все профили с заменой
            log_info "Режим: Все профили (полная замена)"
            for profile in $local_profiles; do
                profiles_to_copy+=("${profile%%|*}")
            done
            ;;
        2)
            # Только новые
            log_info "Режим: Только новые профили"
            for profile in $local_profiles; do
                local uuid="${profile%%|*}"
                if ! echo "$remote_profiles" | grep -q "^${uuid}$"; then
                    profiles_to_copy+=("$uuid")
                fi
            done
            ;;
        3)
            # Выбор с заменой
            log_info "Режим: Выбор профилей (с заменой)"
            while IFS= read -r uuid; do
                [[ -n "$uuid" ]] && profiles_to_copy+=("$uuid")
            done < <(select_profiles "$local_profiles" "no" "$remote_profiles")
            ;;
        4)
            # Выбор только новых
            log_info "Режим: Выбор профилей (только новые)"
            while IFS= read -r uuid; do
                [[ -n "$uuid" ]] && profiles_to_copy+=("$uuid")
            done < <(select_profiles "$local_profiles" "yes" "$remote_profiles")
            ;;
        0)
            log_info "Выход"
            exit 0
            ;;
        *)
            log_error "Неверный выбор"
            exit 1
            ;;
    esac

    # Проверяем что есть что копировать
    if [[ ${#profiles_to_copy[@]} -eq 0 ]]; then
        log_warning "Нет профилей для копирования"
        exit 0
    fi

    echo ""
    log_info "Профилей для копирования: ${#profiles_to_copy[@]}"
    echo ""
    read -p "Начать копирование? (y/n): " confirm

    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        log_info "Отменено"
        exit 0
    fi

    # Копируем профили
    echo ""
    local success_count=0
    local fail_count=0

    for uuid in "${profiles_to_copy[@]}"; do
        if copy_profile "$uuid"; then
            ((success_count++))
        else
            ((fail_count++))
            log_error "Ошибка при копировании $uuid"
        fi
        echo ""
    done

    # Итоговый отчёт
    echo ""
    echo -e "${CYAN}=== Результат ===${NC}"
    echo ""
    log_success "Успешно скопировано: $success_count"
    [[ $fail_count -gt 0 ]] && log_error "Ошибок: $fail_count"
    echo ""

    log_info "Путь на сервере: ${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    echo ""
}

# Запуск
main "$@"
