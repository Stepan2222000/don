import sqlite3
import os

DB_PATH = 'db/telegram_automation.db'

def reset_tasks():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Update query to reset ALL tasks (removed WHERE clause)
        query = """
        UPDATE tasks
        SET 
            status = 'pending',
            is_blocked = 0,
            block_reason = NULL,
            failed_count = 0,
            next_available_at = NULL,
            completed_cycles = 0
        """
        
        cursor.execute(query)
        rows_affected = cursor.rowcount
        
        conn.commit()
        print(f"Successfully reset {rows_affected} tasks (ALL groups).")
        
        # Verify
        cursor.execute("SELECT count(*) FROM tasks WHERE is_blocked = 1")
        blocked_count = cursor.fetchone()[0]
        print(f"Remaining blocked tasks: {blocked_count}")

        conn.close()

    except Exception as e:
        print(f"Error resetting tasks: {e}")

if __name__ == "__main__":
    reset_tasks()
