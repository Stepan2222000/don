#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/package.json" && -d "${SCRIPT_DIR}/src-tauri" ]]; then
  PROJECT_DIR="${SCRIPT_DIR}"
elif [[ -d "${SCRIPT_DIR}/donutbrowser" && -f "${SCRIPT_DIR}/donutbrowser/package.json" ]]; then
  PROJECT_DIR="$(cd "${SCRIPT_DIR}/donutbrowser" && pwd)"
else
  echo "[run.sh] Не удалось найти директорию проекта donutbrowser относительно ${SCRIPT_DIR}" >&2
  exit 1
fi
NODE_DIR="${PROJECT_DIR}/.tools/node-v23.11.1-darwin-arm64/bin"
COREPACK_DATA="${HOME}/.local/share/corepack"

if [[ ! -d "${NODE_DIR}" ]]; then
  cat <<MSG
[run.sh] Node 23.11.1 не найден в ${PROJECT_DIR}/.tools.
Запусти из директории проекта:
  curl -L https://nodejs.org/dist/v23.11.1/node-v23.11.1-darwin-arm64.tar.xz -o .tools/node-v23.11.1.tar.xz
  tar -xf .tools/node-v23.11.1.tar.xz -C .tools
MSG
  exit 1
fi

export PATH="${NODE_DIR}:${COREPACK_DATA}:${PATH}"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "[run.sh] pnpm не найден. Установи corepack или pnpm вручную." >&2
  exit 1
fi

cd "${PROJECT_DIR}"

# Завершаю предыдущие процессы Donut Browser
pkill -f "${PROJECT_DIR}" >/dev/null 2>&1 || true

# Освобождаем порт 3000, чтобы Tauri смог достучаться до Next.js
PORT=3000
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
