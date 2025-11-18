#!/usr/bin/env python3
"""Clear database without confirmation."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import load_config, DEFAULT_CONFIG_PATH

config = load_config(DEFAULT_CONFIG_PATH)
db_path = config.database.absolute_path

print(f"Clearing database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Disable foreign key constraints
cursor.execute("PRAGMA foreign_keys=OFF")

# Clear tables
tables = ['screenshots', 'send_log', 'task_attempts', 'tasks', 'messages', 'profile_daily_stats', 'profiles', 'groups']

for table in tables:
    try:
        cursor.execute(f"DELETE FROM {table}")
        print(f"✓ Cleared {table}: {cursor.rowcount} rows deleted")
    except Exception as e:
        print(f"⚠ Skipped {table}: {e}")

# Re-enable foreign key constraints
cursor.execute("PRAGMA foreign_keys=ON")

conn.commit()

# Vacuum (must be outside transaction)
cursor.execute("VACUUM")

conn.close()

print("\n✅ Database cleared successfully!")
print("\nYou can now:")
print("  1. Import chats: python -m src.main import-chats <group_id> data/chats.txt")
print("  2. Import messages: python -m src.main import-messages <group_id> data/messages.json")
print("  3. Add profiles: python -m src.main add-profile ProfileName")
