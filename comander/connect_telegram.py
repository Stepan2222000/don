#!/usr/bin/env python3
"""
Utility to launch a Donut Browser profile and open Telegram Web.

Reuses helper functions from launch_profile.py to ensure the profile is
started via nodecar and stopped cleanly afterwards.
"""

from __future__ import annotations

import sys
from typing import Dict, Tuple

from launch_profile import (
    PROFILES_DIR,
    build_command,
    collect_profiles,
    run_nodecar,
    stop_profile,
    choose_profile,
)

TELEGRAM_URL = "https://web.telegram.org/a/"


def main() -> None:
    profiles = collect_profiles()
    if not profiles:
        print(
            f"[error] В {PROFILES_DIR} не найдено ни одного профиля. "
            "Добавьте профиль в Donut Browser.",
            file=sys.stderr,
        )
        sys.exit(1)

    name, metadata, profile_path = choose_profile(profiles)
    print(f"[info] Подключаюсь к профилю '{name}' и открываю Telegram Web...")

    try:
        cmd = build_command(metadata, profile_path, url=TELEGRAM_URL)
        payload = run_nodecar(cmd)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    sidecar_id = payload.get("id")
    try:
        print("Telegram Web открыт. Нажмите Enter, чтобы закрыть браузер (или Ctrl+C).")
        input()
    except KeyboardInterrupt:
        print("\n[info] Получен Ctrl+C, завершаю...")
    finally:
        if sidecar_id:
            stop_profile(sidecar_id)
        else:
            print(
                "[warn] Идентификатор запуска не получен. Закройте браузер вручную.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
