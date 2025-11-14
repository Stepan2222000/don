#!/usr/bin/env python3
"""
Console helper to launch Donut Browser profiles via nodecar.

Steps:
1. Prompts for the profile name (case-insensitive).
2. Reads profile metadata from Donut Browser storage.
3. Invokes the bundled nodecar sidecar with correct arguments.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


BASE_APP_DIR = Path.home() / "Library" / "Application Support" / "DonutBrowserDev"
PROFILES_DIR = BASE_APP_DIR / "profiles"
PROXIES_DIR = BASE_APP_DIR / "proxies"
DATA_DIR = BASE_APP_DIR / "data"
BINARIES_DIR = BASE_APP_DIR / "binaries"
NODECAR_PATH = (
    Path(__file__).resolve().parents[1] / "donutbrowser" / "src-tauri" / "binaries" / "nodecar"
)


def collect_profiles() -> List[Tuple[str, Dict, Path]]:
    if not PROFILES_DIR.exists():
        print(f"[error] Profiles directory not found: {PROFILES_DIR}", file=sys.stderr)
        sys.exit(1)

    profiles: List[Tuple[str, Dict, Path]] = []
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        metadata_path = profile_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"[warn] Skipping {metadata_path}: {exc}", file=sys.stderr)
            continue
        name = metadata.get("name")
        if not name:
            continue
        profiles.append((name, metadata, profile_dir))
    return profiles


def choose_profile(profiles: List[Tuple[str, Dict, Path]]) -> Tuple[str, Dict, Path]:
    requested = input("Введите название профиля: ").strip()
    if not requested:
        print("[error] Пустое название профиля.", file=sys.stderr)
        sys.exit(1)

    matches = [
        (name, meta, path)
        for name, meta, path in profiles
        if name.lower() == requested.lower()
    ]

    if not matches:
        available = ", ".join(name for name, _, _ in profiles) or "нет профилей"
        print(f"[error] Профиль '{requested}' не найден. Доступные профили: {available}")
        sys.exit(1)

    if len(matches) > 1:
        print(f"[info] Найдено несколько профилей с именем '{requested}':")
        for idx, (name, meta, _) in enumerate(matches, start=1):
            print(f"  {idx}. {name} (id={meta.get('id')})")
        try:
            idx = int(input("Укажите номер профиля для запуска: ").strip())
            chosen = matches[idx - 1]
        except (ValueError, IndexError):
            print("[error] Некорректный выбор профиля.", file=sys.stderr)
            sys.exit(1)
        return chosen

    return matches[0]


def build_command(meta: Dict, profile_dir: Path, url: str | None = None) -> List[str]:
    camoufox_cfg = meta.get("camoufox_config") or {}
    fingerprint = camoufox_cfg.get("fingerprint")
    if isinstance(fingerprint, dict):
        fingerprint = json.dumps(fingerprint)
    if not isinstance(fingerprint, str):
        raise RuntimeError("Fingerprint не найден в metadata.json; запустите профиль из UI один раз.")

    executable_path = camoufox_cfg.get("executable_path")
    if not executable_path:
        raise RuntimeError("executable_path отсутствует в metadata.json.")

    profile_path = (profile_dir / "profile").resolve()
    if not profile_path.exists():
        raise RuntimeError(f"Каталог профиля не найден: {profile_path}")

    if not NODECAR_PATH.exists():
        raise RuntimeError(f"nodecar не найден: {NODECAR_PATH}")

    cmd = [
        str(NODECAR_PATH),
        "camoufox",
        "start",
        "--profile-path",
        str(profile_path),
        "--executable-path",
        executable_path,
        "--custom-config",
        fingerprint,
    ]

    proxy = camoufox_cfg.get("proxy")
    if proxy:
        cmd.extend(["--proxy", proxy])

    if url:
        cmd.extend(["--url", url])

    return cmd


def run_nodecar(cmd: List[str]) -> Dict:
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        print(f"[error] nodecar завершился с кодом {exc.returncode}")
        if stdout:
            print(f"[stdout]\n{stdout}")
        if stderr:
            print(f"[stderr]\n{stderr}")
        raise RuntimeError(
            f"nodecar завершился с кодом {exc.returncode}\nstdout:\n{stdout or '<пусто>'}\nstderr:\n{stderr or '<пусто>'}"
        )

    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Не удалось разобрать вывод nodecar: {stdout}")

    success = payload.get("success")
    if success is None:
        success = payload.get("processId") is not None

    if success:
        pid = payload.get("processId")
        sid = payload.get("id")
        print(f"[ok] Профиль запущен (id={sid}, PID={pid}).")
    else:
        raise RuntimeError(f"nodecar вернул неожиданный ответ: {stdout}")

    return payload


def stop_profile(sidecar_id: str) -> None:
    cmd = [
        str(NODECAR_PATH),
        "camoufox",
        "stop",
        "--id",
        sidecar_id,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        print(
            f"[warn] Не удалось остановить профиль через nodecar (код {exc.returncode}).",
            file=sys.stderr,
        )
        if stdout:
            print(f"[stdout]\n{stdout}")
        if stderr:
            print(f"[stderr]\n{stderr}")
        return

    stdout = result.stdout.strip()
    if stdout:
        print(stdout)


def main() -> None:
    profiles = collect_profiles()
    if not profiles:
        print("[error] Профили не найдены. Создайте профиль в Donut Browser.")
        sys.exit(1)

    name, metadata, profile_dir = choose_profile(profiles)
    print(f"[info] Запуск профиля '{name}'...")

    try:
        cmd = build_command(metadata, profile_dir)
        payload = run_nodecar(cmd)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    sidecar_id = payload.get("id")
    try:
        print("Профиль запущен. Чтобы закрыть браузер, нажмите Enter (или Ctrl+C)...")
        input()
    except KeyboardInterrupt:
        print("\n[info] Получен Ctrl+C, закрываем профиль...")
    finally:
        if sidecar_id:
            stop_profile(sidecar_id)
        else:
            print("[warn] Неизвестный id профиля, остановите процессы вручную.", file=sys.stderr)


if __name__ == "__main__":
    main()
