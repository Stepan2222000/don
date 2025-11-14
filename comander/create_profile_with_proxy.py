#!/usr/bin/env python3
"""
Create a new Donut Browser Camoufox profile with a specified proxy.

Steps performed:
 1. Stores proxy configuration in Donut's proxies directory.
 2. Generates a new profile skeleton with unique UUID.
 3. Calls nodecar to create a Camoufox fingerprint (honouring the proxy).
 4. Writes metadata.json compatible with Donut Browser.

Usage:
    python create_profile_with_proxy.py --name MyProfile --proxy http://user:pass@host:port

You can optionally specify a custom proxy display name via --proxy-name.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse
from uuid import uuid4

from launch_profile import (
    BASE_APP_DIR,
    PROFILES_DIR,
    PROXIES_DIR,
    DATA_DIR,
    BINARIES_DIR,
    NODECAR_PATH,
    collect_profiles,
)


DOWNLOADS_FILE = DATA_DIR / "downloaded_browsers.json"
ALLOWED_SCHEMES = {"http", "https", "socks4", "socks5"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Camoufox profile with proxy.")
    parser.add_argument("--name", required=True, help="Profile name (must be unique).")
    parser.add_argument(
        "--proxy",
        required=True,
        help="Proxy URL, e.g., http://user:pass@host:port or socks5://host:port",
    )
    parser.add_argument(
        "--proxy-name",
        help="Stored proxy display name (defaults to <profile-name>-proxy).",
    )
    return parser.parse_args()


def ensure_unique_profile(name: str) -> None:
    profiles = collect_profiles()
    existing = {p_name.lower() for p_name, _, _ in profiles}
    if name.lower() in existing:
        print(f"[error] Профиль с именем '{name}' уже существует.", file=sys.stderr)
        sys.exit(1)


def parse_proxy(proxy_url: str) -> Tuple[str, str, int, str | None, str | None]:
    parsed = urlparse(proxy_url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        print(
            f"[error] Неподдерживаемый тип прокси '{parsed.scheme}'. "
            f"Допустимые: {', '.join(sorted(ALLOWED_SCHEMES))}.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not parsed.hostname or parsed.port is None:
        print(
            "[error] В прокси-URL должны быть указаны host и port "
            "(например, http://host:port).",
            file=sys.stderr,
        )
        sys.exit(1)
    return (
        scheme,
        parsed.hostname,
        parsed.port,
        parsed.username,
        parsed.password,
    )


def resolve_camoufox_version() -> Tuple[str, Path]:
    if not DOWNLOADS_FILE.exists():
        print(f"[error] Файл с загруженными браузерами не найден: {DOWNLOADS_FILE}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(DOWNLOADS_FILE.read_text())
    camoufox = data.get("browsers", {}).get("camoufox")
    if not camoufox:
        print("[error] Camoufox ещё не загружен. Сначала скачайте его через Donut UI.", file=sys.stderr)
        sys.exit(1)
    # Берём последнюю (по алфавиту) версию
    version = sorted(camoufox.keys())[-1]
    file_path = Path(camoufox[version]["file_path"])
    executable = file_path / "Camoufox.app" / "Contents" / "MacOS" / "camoufox"
    if not executable.exists():
        print(f"[error] Исполняемый файл Camoufox не найден: {executable}", file=sys.stderr)
        sys.exit(1)
    return version, executable


def _run_generate_config(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_fingerprint(executable_path: Path, proxy_url: str) -> str:
    base_cmd = [
        str(NODECAR_PATH),
        "camoufox",
        "generate-config",
        "--executable-path",
        str(executable_path),
        "--geoip",
    ]

    attempts: list[tuple[list[str], str | None]] = []
    # First attempt with proxy (may fail if proxy unreachable)
    attempts.append((base_cmd + ["--proxy", proxy_url], proxy_url))
    # Fallback without proxy
    attempts.append((base_cmd.copy(), None))

    last_error: subprocess.CalledProcessError | None = None
    for cmd, proxy in attempts:
        try:
            result = _run_generate_config(cmd)
            break
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(
                "[warn] generate-config завершился с ошибкой "
                f"(код {exc.returncode}){' при использовании прокси' if proxy else ''}.",
                file=sys.stderr,
            )
            if exc.stdout:
                print(f"[stdout]\n{exc.stdout}", file=sys.stderr)
            if exc.stderr:
                print(f"[stderr]\n{exc.stderr}", file=sys.stderr)
            # если это была попытка с прокси — пробуем без него
            if proxy is not None:
                print("[info] Повторяю генерацию fingerprint без прокси...", file=sys.stderr)
                continue
            print("[error] Не удалось сгенерировать fingerprint.", file=sys.stderr)
            sys.exit(1)
    else:
        # Should not reach here
        print("[error] Не удалось сгенерировать fingerprint.", file=sys.stderr)
        if last_error and last_error.stderr:
            print(last_error.stderr, file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(result.stdout.strip())
        fingerprint = payload.get("output") or payload
    except json.JSONDecodeError as exc:
        print(f"[error] Некорректный ответ generate-config: {exc}", file=sys.stderr)
        print(result.stdout)
        sys.exit(1)

    if not isinstance(fingerprint, str):
        fingerprint = json.dumps(fingerprint)

    return fingerprint


def save_proxy(proxy_id: str, name: str, settings: dict) -> None:
    PROXIES_DIR.mkdir(parents=True, exist_ok=True)
    proxy_path = PROXIES_DIR / f"{proxy_id}.json"
    data = {
        "id": proxy_id,
        "name": name,
        "proxy_settings": settings,
    }
    proxy_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[ok] Сохранён прокси {name} ({proxy_path}).")


def save_profile(
    profile_id: str,
    profile_name: str,
    version: str,
    proxy_id: str,
    executable_path: Path,
    fingerprint: str,
) -> None:
    profile_dir = PROFILES_DIR / profile_id
    data_dir = profile_dir / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    (profile_dir / "proxy.pac").write_text("function FindProxyForURL(url, host) { return 'DIRECT'; }\n")

    metadata = {
        "id": profile_id,
        "name": profile_name,
        "browser": "camoufox",
        "version": version,
        "proxy_id": proxy_id,
        "process_id": None,
        "last_launch": None,
        "release_type": "stable",
        "camoufox_config": {
            "proxy": None,
            "screen_max_width": None,
            "screen_max_height": None,
            "screen_min_width": None,
            "screen_min_height": None,
            "geoip": True,
            "block_images": None,
            "block_webrtc": None,
            "block_webgl": None,
            "executable_path": str(executable_path),
            "fingerprint": fingerprint,
        },
        "group_id": None,
        "tags": [],
    }

    metadata_path = profile_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"[ok] Создан профиль '{profile_name}' ({metadata_path}).")


def main() -> None:
    args = parse_args()
    ensure_unique_profile(args.name)

    scheme, host, port, username, password = parse_proxy(args.proxy)

    proxy_id = str(uuid4())
    proxy_name = args.proxy_name or f"{args.name}-proxy"
    proxy_settings = {
        "proxy_type": scheme,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }

    version, executable = resolve_camoufox_version()
    fingerprint = generate_fingerprint(executable, args.proxy)

    profile_id = str(uuid4())

    save_proxy(proxy_id, proxy_name, proxy_settings)
    save_profile(profile_id, args.name, version, proxy_id, executable, fingerprint)

    print()
    print("[done] Профиль создан. Возможно, понадобится перезапустить Donut Browser, "
          "чтобы новый профиль и прокси появились в интерфейсе.")


if __name__ == "__main__":
    main()
