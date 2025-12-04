#!/bin/bash

# ============================================================================
# Скрипт переноса профилей Donut Browser на удалённый сервер
# ============================================================================
# Использование: ./sync-profiles-to-server.sh
# Зависимости: sshpass (brew install hudochenkov/sshpass/sshpass)
# ============================================================================

set -e

# Очистка при выходе
trap 'rm -rf /tmp/donut_profiles_sync 2>/dev/null' EXIT

# === КОНФИГУРАЦИЯ (можно изменить) ===
# Локальные пути - используем данные из проекта donutbrowser
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_PROFILES_DIR="$PROJECT_ROOT/donutbrowser/data/profiles"
LOCAL_PROXIES_DIR="$PROJECT_ROOT/donutbrowser/data/proxies"

# Удалённые пути на сервере
REMOTE_PROFILES_DIR="\$HOME/.local/share/DonutBrowserDev/profiles"
REMOTE_PROXIES_DIR="\$HOME/.local/share/DonutBrowserDev/proxies"
# Camoufox устанавливается через pip в ~/.cache/camoufox/
REMOTE_CAMOUFOX_PATH="\$HOME/.cache/camoufox/camoufox"
TEMP_DIR="/tmp/donut_profiles_sync"
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

# Очистка временных файлов
cleanup() {
    if [[ -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
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
    local remote_proxies_expanded="${REMOTE_PROXIES_DIR//\$HOME/$REMOTE_HOME}"

    log_info "Проверка директорий на сервере..."

    # Проверяем директорию профилей
    if ! ssh_cmd "test -d $remote_profiles_expanded"; then
        log_warning "Директория профилей не существует: $remote_profiles_expanded"
        ssh_cmd "mkdir -p $remote_profiles_expanded"
        log_success "Директория профилей создана"
    else
        log_success "Директория профилей существует"
    fi

    # Проверяем директорию прокси
    if ! ssh_cmd "test -d $remote_proxies_expanded"; then
        log_warning "Директория прокси не существует: $remote_proxies_expanded"
        ssh_cmd "mkdir -p $remote_proxies_expanded"
        log_success "Директория прокси создана"
    else
        log_success "Директория прокси существует"
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
    echo "" >&2
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}" >&2
    echo -e "${CYAN}║              Выберите режим копирования                    ║${NC}" >&2
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}" >&2
    echo "" >&2
    echo -e "  ${GREEN}1)${NC} Скопировать ВСЕ профили" >&2
    echo -e "     ${YELLOW}→ Перезапишет существующие профили на сервере${NC}" >&2
    echo -e "     ${YELLOW}→ Используйте для полной синхронизации${NC}" >&2
    echo "" >&2
    echo -e "  ${GREEN}2)${NC} Только НОВЫЕ профили" >&2
    echo -e "     ${YELLOW}→ Копирует только те, которых нет на сервере${NC}" >&2
    echo -e "     ${YELLOW}→ Существующие профили не трогает${NC}" >&2
    echo "" >&2
    echo -e "  ${GREEN}3)${NC} Выбрать вручную (с заменой)" >&2
    echo -e "     ${YELLOW}→ Покажет список, вы выберете какие копировать${NC}" >&2
    echo -e "     ${YELLOW}→ Перезапишет если профиль уже есть на сервере${NC}" >&2
    echo "" >&2
    echo -e "  ${GREEN}4)${NC} Выбрать вручную (без замены)" >&2
    echo -e "     ${YELLOW}→ Покажет только профили, которых нет на сервере${NC}" >&2
    echo -e "     ${YELLOW}→ Существующие профили пропускаются${NC}" >&2
    echo "" >&2
    echo -e "  ${RED}0)${NC} Выход" >&2
    echo "" >&2
    read -p "Выберите режим [0-4]: " mode
    echo "$mode"
}

# Отображение списка профилей для выбора
select_profiles() {
    local profiles_str="$1"
    local filter_existing="$2"  # "yes" или "no"
    local remote_profiles="$3"

    IFS=' ' read -ra profiles <<< "$profiles_str"
    local selected=()

    echo "" >&2
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}" >&2
    echo -e "${CYAN}║                   Доступные профили                        ║${NC}" >&2
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}" >&2
    echo "" >&2

    local display_profiles=()
    local profile_names=()

    for profile in "${profiles[@]}"; do
        local uuid="${profile%%|*}"
        local name="${profile##*|}"
        local status=""

        if echo "$remote_profiles" | grep -q "^${uuid}$"; then
            if [[ "$filter_existing" == "yes" ]]; then
                continue  # Пропускаем существующие
            fi
            status="${YELLOW}(на сервере)${NC}"
        else
            status="${GREEN}(новый)${NC}"
        fi

        display_profiles+=("$profile")
        profile_names+=("$name")
        echo -e "  ${GREEN}•${NC} ${CYAN}$name${NC} $status" >&2
    done

    if [[ ${#display_profiles[@]} -eq 0 ]]; then
        log_warning "Нет профилей для копирования" >&2
        return
    fi

    echo "" >&2
    echo -e "  ${GREEN}all${NC} - Выбрать все профили" >&2
    echo -e "  ${RED}0${NC}   - Отмена" >&2
    echo "" >&2
    echo -e "${YELLOW}Введите названия профилей через пробел или 'all' для всех:${NC}" >&2
    read -p "> " selection

    if [[ "$selection" == "0" ]]; then
        return
    fi

    if [[ "$selection" == "all" || "$selection" == "ALL" ]]; then
        for profile in "${display_profiles[@]}"; do
            echo "${profile%%|*}"
        done
        return
    fi

    # Поиск по именам
    for input_name in $selection; do
        for profile in "${display_profiles[@]}"; do
            local uuid="${profile%%|*}"
            local name="${profile##*|}"
            # Поиск по частичному совпадению (без учета регистра)
            if [[ "${name,,}" == *"${input_name,,}"* ]]; then
                echo "$uuid"
                break
            fi
        done
    done
}

# Старая функция для совместимости (выбор по номерам)
select_profiles_by_number() {
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

# Копирование одного профиля через tar-архив (надёжнее чем rsync/scp)
copy_profile() {
    local uuid="$1"
    local local_path="$LOCAL_PROFILES_DIR/$uuid"
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    local remote_path="$remote_profiles_expanded/$uuid"

    local name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "${local_path}/metadata.json" | sed 's/"name"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')

    log_info "Копирование профиля: $name [$uuid]"

    # Удаляем .parentlock локально перед архивацией
    rm -f "$local_path/profile/.parentlock" 2>/dev/null || true

    # Создаём локальную временную директорию
    mkdir -p "$TEMP_DIR"
    local archive_name="${uuid}.tar.gz"
    local local_archive="$TEMP_DIR/$archive_name"

    # Создаём tar-архив (COPYFILE_DISABLE для macOS - исключает ._ файлы)
    log_info "Создание tar-архива..."
    cd "$LOCAL_PROFILES_DIR"
    COPYFILE_DISABLE=1 tar -czf "$local_archive" "$uuid"

    local archive_size=$(du -h "$local_archive" | cut -f1)
    log_info "Размер архива: $archive_size"

    # Удаляем старый профиль на сервере если есть
    ssh_cmd "rm -rf '$remote_path'" 2>/dev/null || true

    # Копируем архив на сервер (один файл - надёжнее)
    log_info "Копирование архива на сервер..."
    scp_cmd "$local_archive" "/tmp/"

    # Распаковываем на сервере
    log_info "Распаковка на сервере..."
    ssh_cmd "cd '$remote_profiles_expanded' && tar -xzf /tmp/$archive_name && rm /tmp/$archive_name"

    # Удаляем локальный архив
    rm -f "$local_archive"

    # Удаляем .parentlock на сервере
    ssh_cmd "rm -f '$remote_path/profile/.parentlock'" 2>/dev/null || true

    # Проверяем что профиль скопирован
    local remote_files=$(ssh_cmd "find '$remote_path' -type f | wc -l")
    log_success "Профиль скопирован ($remote_files файлов)"

    # Адаптируем пути
    adapt_paths "$uuid"
}

# Адаптация путей в конфигах на сервере
adapt_paths() {
    local uuid="$1"
    local remote_profiles_expanded="${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    local remote_camoufox_expanded="${REMOTE_CAMOUFOX_PATH//\$HOME/$REMOTE_HOME}"
    local remote_path="$remote_profiles_expanded/$uuid"

    log_info "Адаптация путей для Linux..."

    # Проверяем что camoufox установлен на сервере
    if ! ssh_cmd "test -f '$remote_camoufox_expanded'"; then
        log_warning "Camoufox не найден на сервере: $remote_camoufox_expanded"
        log_warning "Установите его: pip install camoufox && python -c 'import camoufox; camoufox.install()'"
    fi

    # Обновляем executable_path в metadata.json на путь к camoufox
    # Заменяем любой macOS путь на Linux путь к camoufox
    ssh_cmd "sed -i 's|\"executable_path\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"executable_path\": \"$remote_camoufox_expanded\"|g' '$remote_path/metadata.json'"

    # Обновляем путь к proxy.pac в user.js (если файл существует)
    local new_proxy_path="file://$remote_path/proxy.pac"
    ssh_cmd "if [ -f '$remote_path/profile/user.js' ]; then sed -i 's|file://[^\"]*proxy.pac|$new_proxy_path|g' '$remote_path/profile/user.js'; fi"

    # Проверяем результат
    local new_path=$(ssh_cmd "grep -o '\"executable_path\"[[:space:]]*:[[:space:]]*\"[^\"]*\"' '$remote_path/metadata.json'" 2>/dev/null)
    log_success "Пути адаптированы: $new_path"
}

# Копирование всех прокси на сервер
copy_all_proxies() {
    local remote_proxies_expanded="${REMOTE_PROXIES_DIR//\$HOME/$REMOTE_HOME}"

    if [[ ! -d "$LOCAL_PROXIES_DIR" ]]; then
        log_warning "Локальная директория прокси не найдена: $LOCAL_PROXIES_DIR"
        return 1
    fi

    local proxy_files=("$LOCAL_PROXIES_DIR"/*.json)
    local proxy_count=${#proxy_files[@]}

    if [[ $proxy_count -eq 0 ]] || [[ ! -f "${proxy_files[0]}" ]]; then
        log_warning "Нет прокси для копирования"
        return 0
    fi

    log_info "Копирование $proxy_count прокси на сервер..."

    # Создаём архив всех прокси
    mkdir -p "$TEMP_DIR"
    local archive_name="proxies.tar.gz"
    local local_archive="$TEMP_DIR/$archive_name"

    cd "$LOCAL_PROXIES_DIR"
    COPYFILE_DISABLE=1 tar -czf "$local_archive" *.json

    # Копируем архив на сервер
    scp_cmd "$local_archive" "/tmp/"

    # Распаковываем на сервере (перезаписываем существующие)
    ssh_cmd "cd '$remote_proxies_expanded' && tar -xzf /tmp/$archive_name && rm /tmp/$archive_name"

    # Удаляем локальный архив
    rm -f "$local_archive"

    log_success "Прокси скопированы: $proxy_count файлов"
}

# Копирование нового proxies.txt для системы автоматизации
copy_proxies_txt() {
    local local_proxies_txt="$PROJECT_ROOT/tg-automatizamtion/data/proxies.txt"
    local remote_proxies_txt="/root/don/tg-automatizamtion/data/proxies.txt"

    if [[ ! -f "$local_proxies_txt" ]]; then
        log_warning "Файл proxies.txt не найден: $local_proxies_txt"
        return 1
    fi

    log_info "Копирование proxies.txt для системы автоматизации..."

    # Создаём директорию на сервере если не существует
    ssh_cmd "mkdir -p /root/don/tg-automatizamtion/data"

    # Копируем файл
    scp_cmd "$local_proxies_txt" "$remote_proxies_txt"

    log_success "proxies.txt скопирован на сервер"
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

    # Копируем все прокси (JSON файлы для DonutBrowser)
    echo ""
    copy_all_proxies

    # Копируем proxies.txt для системы автоматизации
    echo ""
    copy_proxies_txt

    # Итоговый отчёт
    echo ""
    echo -e "${CYAN}=== Результат ===${NC}"
    echo ""
    log_success "Профилей скопировано: $success_count"
    [[ $fail_count -gt 0 ]] && log_error "Ошибок: $fail_count"
    echo ""

    log_info "Путь профилей на сервере: ${REMOTE_PROFILES_DIR//\$HOME/$REMOTE_HOME}"
    log_info "Путь прокси на сервере: ${REMOTE_PROXIES_DIR//\$HOME/$REMOTE_HOME}"
    echo ""
}

# Запуск
main "$@"
