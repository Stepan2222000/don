#!/bin/bash
set -euo pipefail

# Добавляем Rust в PATH если установлен
[[ -d "${HOME}/.cargo/bin" ]] && export PATH="${HOME}/.cargo/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/package.json" && -d "${SCRIPT_DIR}/src-tauri" ]]; then
  PROJECT_DIR="${SCRIPT_DIR}"
elif [[ -d "${SCRIPT_DIR}/donutbrowser" && -f "${SCRIPT_DIR}/donutbrowser/package.json" ]]; then
  PROJECT_DIR="$(cd "${SCRIPT_DIR}/donutbrowser" && pwd)"
else
  echo "[run.sh] Не удалось найти директорию проекта donutbrowser относительно ${SCRIPT_DIR}" >&2
  exit 1
fi

# Переопределяем директорию данных (профили будут в PROJECT_DIR/data/profiles/)
export DONUTBROWSER_DATA_DIR="${PROJECT_DIR}/data"

NODE_VERSION="23.11.1"
OS=$(uname -s)
ARCH=$(uname -m)

# Определяем платформу и архитектуру для Node.js
case "${OS}" in
  Darwin)
    if [[ "${ARCH}" == "arm64" ]]; then
      NODE_PLATFORM="darwin-arm64"
    else
      NODE_PLATFORM="darwin-x64"
    fi
    ;;
  Linux)
    if [[ "${ARCH}" == "aarch64" ]]; then
      NODE_PLATFORM="linux-arm64"
    else
      NODE_PLATFORM="linux-x64"
    fi
    ;;
  *)
    echo "[run.sh] Неподдерживаемая платформа: ${OS}" >&2
    exit 1
    ;;
esac

NODE_DIR="${PROJECT_DIR}/.tools/node-v${NODE_VERSION}-${NODE_PLATFORM}/bin"
COREPACK_DATA="${HOME}/.local/share/corepack"

if [[ ! -d "${NODE_DIR}" ]]; then
  echo "[run.sh] Node ${NODE_VERSION} не найден. Скачиваю автоматически..."
  mkdir -p "${PROJECT_DIR}/.tools"
  NODE_TAR="node-v${NODE_VERSION}-${NODE_PLATFORM}.tar.xz"
  NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TAR}"

  echo "[run.sh] Скачиваю ${NODE_URL}..."
  curl -L "${NODE_URL}" -o "${PROJECT_DIR}/.tools/${NODE_TAR}"

  echo "[run.sh] Распаковываю..."
  tar -xf "${PROJECT_DIR}/.tools/${NODE_TAR}" -C "${PROJECT_DIR}/.tools"

  echo "[run.sh] Удаляю архив..."
  rm "${PROJECT_DIR}/.tools/${NODE_TAR}"

  echo "[run.sh] Node ${NODE_VERSION} установлен успешно!"
fi

export PATH="${NODE_DIR}:${COREPACK_DATA}:${PATH}"

# На Linux запускаем через Xvfb (виртуальный дисплей)
if [[ "${OS}" == "Linux" ]]; then
  echo "[run.sh] Linux: запускаю через Xvfb (виртуальный дисплей)..."

  # Проверяем наличие Xvfb
  if ! command -v Xvfb >/dev/null 2>&1; then
    echo "[run.sh] Xvfb не найден. Установите: sudo apt install xvfb" >&2
    exit 1
  fi

  # Запускаем Xvfb на :99 с разрешением 1920x1080
  Xvfb :99 -screen 0 1920x1080x24 &
  XVFB_PID=$!
  export DISPLAY=:99

  # Cleanup Xvfb при выходе
  trap "kill ${XVFB_PID} 2>/dev/null || true" EXIT

  echo "[run.sh] Xvfb запущен на DISPLAY=${DISPLAY}"
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "[run.sh] pnpm не найден. Устанавливаю через corepack..."
  corepack enable
  corepack prepare pnpm@latest --activate
fi

cd "${PROJECT_DIR}"

# Завершаю предыдущие процессы Donut Browser (только для этого проекта)
pkill -f "${PROJECT_DIR}.*tauri dev" >/dev/null 2>&1 || true
pkill -f "${PROJECT_DIR}.*next dev" >/dev/null 2>&1 || true
pkill -f "${PROJECT_DIR}/src-tauri/target/debug/donutbrowser" >/dev/null 2>&1 || true

# Освобождаем порт 3001, чтобы Tauri смог достучаться до Next.js
PORT=3001
busy_pids=$(lsof -tiTCP:${PORT} -sTCP:LISTEN || true)
if [[ -n "${busy_pids}" ]]; then
  echo "[run.sh] Завершаю процессы на порту ${PORT}: ${busy_pids}"
  # Используем xargs -r, чтобы не запускать kill без аргументов
  echo "${busy_pids}" | xargs -r kill
  # Ждём, пока порт освободится
  for _ in {1..20}; do
    if lsof -tiTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
      sleep 0.1
    else
      break
    fi
  done
  if lsof -tiTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[run.sh] Не удалось освободить порт ${PORT}. Отменяю запуск." >&2
    exit 1
  fi
fi

if [[ ! -d node_modules ]]; then
  echo "[run.sh] node_modules отсутствует, выполняю pnpm install..."
  pnpm install
fi

if [[ ! -x src-tauri/binaries/nodecar ]]; then
  echo "[run.sh] бинарник nodecar отсутствует, выполняю pnpm build в nodecar..."
  pnpm -C nodecar build
fi

if [[ src-tauri/binaries/nodecar -ot nodecar/package.json ]]; then
  echo "[run.sh] Обновляю nodecar после изменений в package.json..."
  pnpm -C nodecar build
fi

echo "[run.sh] Запускаю 'pnpm tauri dev'..."
pnpm tauri dev
