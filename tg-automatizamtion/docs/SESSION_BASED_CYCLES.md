# Session-Based Cycle Tracking

## Overview

Starting from this version, the Telegram automation system supports **per-session cycle tracking**. This means that `max_cycles` now applies to each individual run/session, while `max_messages_per_hour` remains a global limit.

## Key Changes

### Before
- `max_cycles`: Global limit - counted across all runs and saved in database
- Each chat could only receive `max_cycles` messages **ever** (until manually reset)
- Progress persisted between restarts

### After
- `max_cycles`: Per-session limit - resets with each new `start` command
- `max_messages_per_hour`: Global limit - still enforced across all runs
- Each new session can send up to `max_cycles` messages to each chat
- Historical stats (`completed_cycles`) still tracked for analytics

## How It Works

### Session ID (run_id)

Each time you run `python -m src.main start`, a unique **session ID** (run_id) is generated:

```
Session ID (run_id): 7f3a2b1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c
```

All messages sent during this session are tagged with this ID in the database.

### Cycle Counting

- **Per-session**: Each chat can receive `max_cycles` messages in the current session
- **Global hourly**: Each profile can send max `max_messages_per_hour` messages per hour (across all chats)
- **Historical**: `completed_cycles` in `tasks` table tracks total sends for statistics

### Example

**Configuration:**
```yaml
limits:
  max_messages_per_hour: 30      # Global hourly limit per profile
  max_cycles: 2                  # Per-session limit per chat
  cycle_delay_minutes: 20        # Delay between sends to same chat
```

**Scenario:**
1. **First run** (`start`):
   - Session ID: `abc-123`
   - Sends 2 messages to each of 100 chats (200 total)
   - Takes ~7 hours due to hourly rate limit
   - Stop with Ctrl+C after 50 chats completed

2. **Second run** (`start` again):
   - Session ID: `def-456` (**new session!**)
   - **Continues from where it stopped** (remaining 50 chats get 2 messages)
   - Then **starts over**: all 100 chats can receive 2 more messages
   - Total sent in session 2: 100 + 200 = 300 messages

3. **Third run** (`start` again):
   - Session ID: `ghi-789` (**another new session!**)
   - All 100 chats can receive 2 more messages again
   - And so on...

## Migration for Existing Databases

If you have an existing database, run the migration script:

```bash
cd tg-automatizamtion
python scripts/migrate_db.py
```

This adds the `run_id` column to the `task_attempts` table. The migration is:
- **Safe**: Doesn't delete or modify existing data
- **Idempotent**: Can be run multiple times without issues
- **Backward compatible**: Old records will have `run_id = NULL`

## Database Schema Changes

### task_attempts Table

**New column:**
```sql
run_id TEXT  -- Session ID (NULL for old records)
```

**New indexes:**
```sql
CREATE INDEX idx_attempts_run_id ON task_attempts(run_id);
CREATE INDEX idx_attempts_task_run ON task_attempts(task_id, run_id);
```

## Benefits

### 1. Flexible Campaign Management
- Run multiple campaigns to the same chats without manual database resets
- Stop and restart anytime without losing progress

### 2. Better Control
- `max_cycles` limits each session (prevents spam in single run)
- `max_messages_per_hour` prevents account bans (global protection)

### 3. Historical Tracking
- Every attempt tagged with session ID
- Full audit trail of all campaigns
- Analytics: "How many sessions did it take to get responses?"

### 4. Cleaner Workflow
```bash
# Campaign 1: Introduction
python -m src.main start
# Session: abc-123, sends 1 message to each chat

# Wait a week...

# Campaign 2: Follow-up
python -m src.main start
# Session: def-456, sends 1 message to each chat again
```

## Implementation Details

### Code Changes

1. **Schema** ([db/schema.sql](../db/schema.sql:75))
   - Added `run_id TEXT` to `task_attempts`

2. **Database** ([src/database.py](../src/database.py:330))
   - `add_task_attempt()`: Added `run_id` parameter
   - `get_task_attempts_count_by_run()`: New method for session counting

3. **Task Queue** ([src/task_queue.py](../src/task_queue.py:26))
   - `get_next_incomplete_task()`: Checks attempts by `run_id`
   - `mark_task_success()`: Records `run_id` with each attempt
   - `mark_task_failed()`: Records `run_id` with each attempt

4. **Worker** ([src/worker.py](../src/worker.py:26))
   - Constructor accepts `run_id`
   - Passes `run_id` to all queue operations

5. **Error Handler** ([src/error_handler.py](../src/error_handler.py:24))
   - Constructor accepts `run_id`
   - Passes `run_id` when marking failures

6. **Main CLI** ([src/main.py](../src/main.py:30))
   - `WorkerManager`: Generates UUID for each session
   - Passes `run_id` to worker subprocesses
   - Displays session ID on startup

### Backward Compatibility

- **Legacy mode**: If `run_id` is not provided (or `None`), falls back to global `completed_cycles` counting
- **Old records**: Existing `task_attempts` with `run_id = NULL` don't affect new sessions
- **Gradual transition**: System works with mixed old/new records

## Configuration

No configuration changes needed! The system automatically uses per-session tracking.

Just set your limits in `config.yaml`:
```yaml
limits:
  max_messages_per_hour: 30      # Global hourly limit (protects accounts)
  max_cycles: 2                  # Per-session limit (controls spam per run)
  cycle_delay_minutes: 20        # Delay between cycles
```

## FAQ

**Q: Will my historical data be affected?**
A: No. Old records remain unchanged with `run_id = NULL`. New sessions create new records.

**Q: Can I still see total sends per chat?**
A: Yes. The `completed_cycles` field in `tasks` table tracks total sends for statistics.

**Q: What if I want global cycle limits like before?**
A: Set `max_cycles` very high (e.g., 1000) and manually track progress. Or keep `max_cycles` low and run multiple sessions.

**Q: How do I see which session sent which message?**
A: Query `task_attempts` table:
```sql
SELECT * FROM task_attempts WHERE run_id = 'your-session-id';
```

**Q: Can I restart a specific session?**
A: Not directly. Each `start` creates a new session. But you can query old sessions for analysis.

## Summary

- ✅ `max_cycles` is now per-session (resets each `start`)
- ✅ `max_messages_per_hour` remains global (prevents bans)
- ✅ Full backward compatibility
- ✅ Better campaign management
- ✅ Complete audit trail with session IDs
