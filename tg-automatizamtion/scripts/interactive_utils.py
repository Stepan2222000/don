"""
Interactive utilities for scripts.

Provides common functions for interactive user input, validation, and menu display.
"""

import sys
from pathlib import Path
from typing import List, Optional, Callable, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_groups
from src.profile_manager import get_all_profiles


def show_header(title: str):
    """Show formatted header."""
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print()


def show_menu(options: List[tuple]):
    """
    Show menu options.

    Args:
        options: List of (number, description) tuples

    Example:
        show_menu([
            (1, "Option 1"),
            (2, "Option 2"),
            (0, "Exit")
        ])
    """
    print("Выберите действие:")
    for num, desc in options:
        print(f"  {num}. {desc}")
    print()


def get_choice(prompt: str, valid_choices: List[str]) -> str:
    """
    Get user choice with validation.

    Args:
        prompt: Input prompt
        valid_choices: List of valid choices (as strings)

    Returns:
        User's choice
    """
    while True:
        try:
            choice = input(prompt).strip()
            if choice in valid_choices:
                return choice
            print(f"Ошибка: введите один из вариантов: {', '.join(valid_choices)}")
        except (KeyboardInterrupt, EOFError):
            print("\n\nОперация отменена пользователем.")
            sys.exit(0)


def get_input(
    prompt: str,
    validator: Optional[Callable[[str], tuple[bool, Optional[str]]]] = None,
    allow_empty: bool = False,
    default: Optional[str] = None
) -> str:
    """
    Get user input with optional validation.

    Args:
        prompt: Input prompt
        validator: Optional function that takes input and returns (is_valid, error_message)
        allow_empty: Whether to allow empty input
        default: Default value if input is empty

    Returns:
        User's input
    """
    while True:
        try:
            prompt_text = prompt
            if default:
                prompt_text += f" [{default}]"
            prompt_text += ": "

            value = input(prompt_text).strip()

            # Handle empty input
            if not value:
                if default:
                    return default
                if allow_empty:
                    return value
                print("Ошибка: введите значение")
                continue

            # Validate if validator provided
            if validator:
                is_valid, error_msg = validator(value)
                if not is_valid:
                    print(f"Ошибка: {error_msg}")
                    continue

            return value

        except (KeyboardInterrupt, EOFError):
            print("\n\nОперация отменена пользователем.")
            sys.exit(0)


def confirm(prompt: str, default: bool = False) -> bool:
    """
    Get yes/no confirmation from user.

    Args:
        prompt: Confirmation prompt
        default: Default value if user just presses Enter

    Returns:
        True if confirmed, False otherwise
    """
    default_str = "да" if default else "нет"
    full_prompt = f"{prompt} (да/нет) [{default_str}]: "

    try:
        response = input(full_prompt).strip().lower()

        if not response:
            return default

        return response in ['да', 'yes', 'y', 'д']

    except (KeyboardInterrupt, EOFError):
        print("\n\nОперация отменена пользователем.")
        sys.exit(0)


def list_groups() -> List[str]:
    """
    Get list of available groups.

    Returns:
        List of group IDs
    """
    try:
        groups_data = load_groups()
        return [g.id for g in groups_data.groups]
    except FileNotFoundError:
        return []


def show_groups():
    """Show available groups."""
    groups = list_groups()

    if not groups:
        print("Нет доступных групп.")
        print("Создайте группу с помощью: python scripts/manage_groups.py")
        return

    print("\nДоступные группы:")
    for group_id in groups:
        print(f"  - {group_id}")
    print()


def list_profiles() -> List[tuple[str, str]]:
    """
    Get list of available Donut Browser profiles.

    Returns:
        List of (profile_name, profile_id) tuples
    """
    try:
        profiles = get_all_profiles()
        return [(p.profile_name, p.profile_id) for p in profiles]
    except Exception:
        return []


def show_profiles():
    """Show available Donut Browser profiles."""
    profiles = list_profiles()

    if not profiles:
        print("Нет доступных профилей Donut Browser.")
        return

    print("\nДоступные профили:")
    for name, profile_id in profiles:
        print(f"  - {name} ({profile_id[:8]}...)")
    print()


def validate_file_exists(file_path: str) -> tuple[bool, Optional[str]]:
    """Validate that file exists."""
    if Path(file_path).exists():
        return True, None
    return False, f"Файл не найден: {file_path}"


def validate_group_exists(group_id: str) -> tuple[bool, Optional[str]]:
    """Validate that group exists."""
    groups = list_groups()
    if group_id in groups:
        return True, None
    return False, f"Группа не найдена: {group_id}"


def validate_not_empty(value: str) -> tuple[bool, Optional[str]]:
    """Validate that value is not empty."""
    if value.strip():
        return True, None
    return False, "Значение не может быть пустым"


def get_multiline_input(prompt: str) -> List[str]:
    """
    Get multiple lines of input from user.

    Args:
        prompt: Input prompt

    Returns:
        List of input lines
    """
    print(prompt)
    print("(Введите пустую строку для завершения)")

    lines = []
    try:
        while True:
            line = input().strip()
            if not line:
                break
            lines.append(line)
    except (KeyboardInterrupt, EOFError):
        print("\n\nОперация отменена пользователем.")
        sys.exit(0)

    return lines
