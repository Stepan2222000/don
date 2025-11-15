# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Donut Browser is an anti-detect browser application that allows users to create isolated browser profiles with fingerprint protection, powered by Camoufox. The project is built as a Tauri desktop application with a Next.js frontend.

## Development Commands

### Running the Application

```bash
# Automated setup and run (recommended for first-time setup)
# This script handles Node.js setup, dependency installation, nodecar building, and running the app
./run.sh

# Manual development workflow
pnpm install                # Install dependencies
cd nodecar && pnpm build    # Build nodecar sidecar binary (requires banderole)
pnpm tauri dev              # Start development server
```

### Building

```bash
pnpm build                  # Build Next.js frontend
cd src-tauri && cargo build # Build Rust backend
pnpm tauri build            # Build complete Tauri application
```

### Testing

```bash
pnpm test                   # Run Rust tests (alias for test:rust)
pnpm test:rust              # Run Cargo tests in src-tauri
pnpm check-unused-commands  # Verify no unused Tauri commands
```

### Linting and Formatting

```bash
pnpm lint                   # Lint both JS and Rust
pnpm lint:js                # Biome check + TypeScript check
pnpm lint:rust              # Cargo clippy + fmt check

pnpm format                 # Format both JS and Rust
pnpm format:js              # Biome format with --unsafe flag
pnpm format:rust            # Cargo clippy --fix + cargo fmt
```

### Other Useful Commands

```bash
pnpm cargo <command>        # Run cargo commands from root
pnpm unused-exports:js      # Find unused TypeScript exports
pnpm shadcn:add <component> # Add shadcn/ui components
```

## Architecture

### Three-Layer Architecture

1. **Frontend (Next.js + React)**
   - Located in `src/`
   - Next.js 15 with App Router (`src/app/`)
   - React 19 with TypeScript
   - Tailwind CSS v4 for styling
   - shadcn/ui components (`src/components/ui/`)
   - Custom hooks in `src/hooks/`
   - Path alias: `@/*` maps to `src/*`

2. **Backend (Tauri/Rust)**
   - Located in `src-tauri/src/`
   - Handles native OS integration, file system, updates
   - Key modules:
     - `browser_runner.rs` - Browser process management
     - `profile/` - Profile management and storage
     - `browser_version_manager.rs` - Browser version updates
     - `auto_updater.rs` - Application updates
     - `api_server.rs` - Internal API for frontend-backend communication
     - `camoufox_manager.rs` - Camoufox browser integration
     - `proxy_manager.rs` - Proxy configuration
     - `profile_importer.rs` - Import from other browsers

3. **Nodecar Sidecar (Node.js Binary)**
   - Located in `nodecar/`
   - Packaged as standalone executable using Banderole
   - Provides access to Node.js ecosystem (Playwright, Camoufox JS API)
   - Handles browser automation and fingerprinting
   - Built independently and bundled with Tauri app
   - Must be rebuilt when `nodecar/package.json` changes

### Communication Flow

```
Next.js Frontend (port 3000)
       ↕ (Tauri API)
Tauri Rust Backend
       ↕ (IPC/stdio)
Nodecar Sidecar Binary
       ↕
Camoufox Browser Instance
```

## Technology Stack

- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS v4
- **UI Components**: Radix UI primitives via shadcn/ui
- **Backend**: Rust with Tauri v2
- **Browser Engine**: Camoufox (anti-detect Firefox fork)
- **Browser Automation**: Playwright Core + donutbrowser-camoufox-js
- **Package Manager**: pnpm (v10.14.0+)
- **Linting**: Biome (JS/TS), Clippy (Rust)
- **Build Tools**: Banderole (nodecar bundling), Cargo, Next.js

## Important Development Notes

### Prerequisites

- Node.js v23 (see `.node-version` file, or use bundled version in `.tools/`)
- pnpm package manager
- Rust and Cargo toolchain (latest stable)
- Banderole CLI for building nodecar (`npm i -g banderole`)
- Tauri prerequisites: https://v2.tauri.app/start/prerequisites/

### Nodecar Binary

- Nodecar must be built before running the app for the first time
- The binary is stored at `src-tauri/binaries/nodecar` (platform-specific name)
- Rebuild nodecar when changing dependencies in `nodecar/package.json`
- The `run.sh` script automatically rebuilds nodecar if needed

### Code Style

- **JavaScript/TypeScript**: Use Biome (not ESLint or Prettier)
- **Rust**: Use Clippy and rustfmt with strict settings
- Git hooks (Husky + lint-staged) automatically format on commit
- No third-party libraries should be added without discussion

### Path Handling

- Use Tauri's path APIs for cross-platform file paths
- Frontend uses `@/` import alias for `src/` directory
- Rust uses relative module paths within `src-tauri/src/`

### Testing

- Rust tests use standard `#[cfg(test)]` modules and `cargo test`
- Frontend testing is minimal; focus on Rust backend testing
- Test browser profiles in development with real Camoufox instances

### Browser Profile Storage

- Profiles stored in app data directory (platform-specific)
- Each profile has isolated browser data, settings, and fingerprint
- Profile metadata stored separately from browser data
- Use Tauri FS plugin for file operations

### Supported Platforms

- macOS (Intel & Apple Silicon) - primary development platform
- Linux (x64 & arm64) - supported
- Windows - planned, not yet implemented

### CI/CD

The project uses GitHub Actions for:
- JavaScript/TypeScript linting (`lint-js.yml`)
- Rust linting (`lint-rs.yml`)
- PR checks (`pr-checks.yml`)
- Release builds (`release.yml`, `rolling-release.yml`)
- Security scanning (CodeQL, OSV)
- Dependency auto-merge (`dependabot-automerge.yml`)

## Common Patterns

### Adding a New Tauri Command

1. Define command in appropriate Rust module in `src-tauri/src/`
2. Add to `lib.rs` invoke handler
3. Create TypeScript types in `src/types.ts`
4. Call from frontend using `@tauri-apps/api`

### Adding a UI Component

1. Use `pnpm shadcn:add <component>` for Radix-based components
2. Custom components go in `src/components/`
3. Icons from `react-icons` or custom in `src/components/icons/`

### Working with Browser Profiles

- Profile creation/management flows through Rust backend
- Nodecar handles actual browser launching and fingerprint injection
- Frontend receives profile state via Tauri events

## Telegram Automation System (`tg-automatizamtion/`)

The project includes a Python-based Telegram automation system that leverages Donut Browser profiles for automated message distribution to Telegram chats via web.telegram.org/k.

### Overview

- **Purpose**: Automated messaging to multiple Telegram chats using Donut Browser profiles
- **Architecture**: Worker Pool model with concurrent multi-profile processing
- **Storage**: SQLite database with WAL mode for concurrent access
- **Automation**: Playwright-based browser automation for Telegram Web
- **Interface**: CLI commands for management and execution

### Technology Stack

- **Language**: Python 3.11+
- **Browser Automation**: Playwright (Firefox/Camoufox)
- **Database**: SQLite3 with WAL mode
- **Configuration**: YAML-based config management
- **Integration**: Direct integration with Donut Browser profiles

### Directory Structure

```
tg-automatizamtion/
├── src/                      # Python source modules
│   ├── main.py              # CLI entry point and command handlers
│   ├── config.py            # Configuration management (dataclasses)
│   ├── database.py          # SQLite operations with thread-safe connections
│   ├── profile_manager.py   # Donut Browser profile discovery and validation
│   ├── browser_automation.py # Browser launch with Playwright + Camoufox
│   ├── telegram_sender.py   # Telegram Web automation (search, send, error detection)
│   ├── task_queue.py        # Atomic task queue with fair distribution
│   ├── worker.py            # Worker process implementation
│   ├── error_handler.py     # Error scenario handlers (4 types)
│   └── logger.py            # Multi-file structured logging
├── db/
│   ├── schema.sql           # Database schema (6 tables, 2 views)
│   └── telegram_automation.db # SQLite database (auto-created)
├── data/
│   ├── chats.txt            # Target chat list (@username per line)
│   └── messages.json        # Message templates (JSON array)
├── docs/
│   ├── REQUIREMENTS.md      # Detailed system specification
│   └── SELECTORS.md         # Telegram Web CSS selectors reference
├── htmls/                   # Telegram Web HTML examples for reference
├── logs/                    # Auto-generated logs and screenshots
│   ├── main.log
│   ├── success.log
│   ├── failed_chats.log
│   ├── failed_send.log
│   └── screenshots/         # Error/warning/debug screenshots
├── config.yaml              # Configuration file
└── requirements.txt         # Python dependencies
```

### Core Modules

#### main.py - CLI Interface
- **Commands**: `init`, `import-chats`, `import-messages`, `add-profile`, `list-profiles`, `start`, `status`, `stop`
- **WorkerManager**: Manages multiple worker subprocesses, handles graceful shutdown
- **Entry Points**: Argument parsing, command routing, subprocess spawning

#### config.py - Configuration Management
- **Dataclasses**: `LimitsConfig`, `TimeoutsConfig`, `TelegramConfig`, `RetryConfig`, `ScreenshotsConfig`, `LoggingConfig`, `DatabaseConfig`
- **Validation**: Type checking, range validation for all config values
- **Serialization**: YAML loading/saving with defaults

#### database.py - SQLite Operations
- **Thread Safety**: Thread-local connections for concurrent access
- **Transactions**: Context managers for atomic operations
- **Operations**: Profiles, tasks, task attempts, messages, send log, screenshots
- **Schema**: 6 tables (profiles, tasks, task_attempts, messages, send_log, screenshots) + 2 views

#### profile_manager.py - Donut Browser Integration
- **Discovery**: Scans `~/Library/Application Support/DonutBrowserDev/profiles/`
- **Metadata**: Reads `metadata.json` from each profile directory
- **Validation**: Checks executable path, fingerprint config, browser data directory
- **DonutProfile**: Dataclass with profile_id, name, browser, version, paths, camoufox config, proxy

#### browser_automation.py - Browser Launching
- **BrowserAutomation**: Full automation with Playwright persistent context
- **BrowserAutomationSimplified**: Direct Playwright launch (faster, used by workers)
- **Fingerprint Handling**: Parses fingerprint JSON, prepares CAMOU_CONFIG_* env vars
- **Context Management**: Handles browser lifecycle, proxy configuration

#### telegram_sender.py - Telegram Web Automation
- **TelegramSelectors**: CSS selectors for Telegram Web K version
- **Operations**:
  - `search_chat()`: Search with retry logic, handles search container
  - `open_chat()`: Opens chat from search results
  - `check_chat_restrictions()`: Detects frozen account, join required, premium required, blocked user
  - `send_message()`: Sends message via contenteditable input
  - `save_screenshot()`: Conditional screenshot capture
- **Reliability**: Multiple load states, explicit waits, retry mechanisms

#### task_queue.py - Task Queue Management
- **Atomic Operations**: UPDATE + RETURNING for race-condition-free task claiming
- **Prioritization**:
  1. Tasks with fewer completed cycles (balancing)
  2. Tasks not attempted recently (fairness)
- **Rate Limiting**: Per-profile hourly message limits
- **Cycle Management**: Automatic cycle delay, completion tracking
- **Statistics**: Queue stats, progress tracking

#### worker.py - Worker Process
- **Lifecycle**: Launch browser → Process tasks → Close browser
- **Main Loop**: Get task → Search → Open → Check restrictions → Send → Record result → Delay
- **Error Handling**: Delegates to ErrorHandler for 4 error scenarios
- **Cleanup**: Resets interrupted tasks on shutdown, closes DB connections
- **Subprocess Entry**: CLI args parsing, profile validation, worker execution

#### error_handler.py - Error Scenarios
Handles 4 main error types:
1. **Chat Not Found**: Block task permanently, screenshot (warning), log to failed_chats.log
2. **Account Frozen**: Block profile, stop worker, screenshot (error), critical log
3. **Send Restrictions**: Don't block (may work later), screenshot (warning), log to failed_send.log
   - `need_to_join`: Must join channel/group
   - `premium_required`: Premium subscription needed
   - `user_blocked`: User has blocked account
   - `input_not_available`: Cannot access message input
4. **Unexpected Errors**: Network/exception errors, screenshot (error), continue processing

#### logger.py - Multi-File Logging
- **Files**:
  - `main.log`: General application logs (console + file)
  - `success.log`: Successful sends only
  - `failed_chats.log`: Chat not found errors
  - `failed_send.log`: Send restriction errors
- **Screenshots**: Organized by type (errors/, warnings/, debug/)
- **Structured Logging**: Consistent format with timestamps, levels, context
- **Progress Tracking**: Task completion, worker lifecycle, browser operations

### Database Schema

#### Tables

1. **profiles**: Donut Browser profiles participating in automation
   - Fields: profile_id (UUID), profile_name, is_active, is_blocked, messages_sent_current_hour, hour_reset_time, last_message_time
   - Purpose: Track profile state and hourly rate limits

2. **tasks**: One record per chat, accumulates statistics
   - Fields: chat_username, status (pending/in_progress/completed/blocked), assigned_profile_id, total_cycles, completed_cycles, success_count, failed_count, is_blocked, block_reason
   - Purpose: Main task queue with progress tracking

3. **task_attempts**: History of all send attempts
   - Fields: task_id (FK), profile_id, cycle_number, status, message_text, error_type, error_message
   - Purpose: Detailed audit trail of every attempt

4. **messages**: Message templates for sending
   - Fields: text, is_active, usage_count
   - Purpose: Rotating message pool for distribution

5. **send_log**: General log of all sends for analytics
   - Fields: task_id (FK), profile_id, chat_username, message_text, status, error_type, error_details
   - Purpose: Fast search and analytics

6. **screenshots**: Screenshot metadata
   - Fields: log_id (FK), screenshot_type, file_name, description
   - Purpose: Link screenshots to send attempts

#### Views

1. **profile_stats**: Aggregated statistics per profile
2. **task_progress**: Progress percentage per task

### Worker Pool Architecture

```
Main Process (CLI)
    ├── Worker 1 (Profile A) → Playwright → Camoufox → web.telegram.org/k
    ├── Worker 2 (Profile B) → Playwright → Camoufox → web.telegram.org/k
    └── Worker 3 (Profile C) → Playwright → Camoufox → web.telegram.org/k
                ↓
        SQLite Database (WAL mode)
                ↓
          Shared Task Queue
```

Each worker:
1. Claims task atomically from shared queue (prevents race conditions)
2. Launches browser with Donut Browser profile (fingerprint + proxy)
3. Navigates to Telegram Web and waits for UI load
4. Executes: Search → Open → Check Restrictions → Send → Record Result
5. Applies calculated delay (randomized to avoid patterns)
6. Claims next task and repeats
7. Stops when no more tasks or account frozen

### Configuration (`config.yaml`)

```yaml
limits:
  max_messages_per_hour: 30      # Per-profile rate limit
  max_cycles: 1                  # How many times to send to each chat
  delay_randomness: 0.2          # ±20% randomness to avoid patterns
  cycle_delay_minutes: 20        # Delay between cycles for same chat

timeouts:
  search_timeout: 10             # Chat search timeout
  send_timeout: 5                # Message send timeout
  page_load_timeout: 30          # Page load timeout

telegram:
  url: "https://web.telegram.org/k"
  headless: false                # Set to true for headless mode

screenshots:
  enabled: true                  # Master switch
  on_error: true                 # Screenshot on errors (account frozen, exceptions)
  on_warning: false              # Screenshot on warnings (chat not found, restrictions)
  on_debug: false                # Screenshot for debugging
  full_page: true                # Full page screenshots
  quality: 80                    # JPEG quality (0-100)
  format: "png"                  # png or jpeg
  max_age_days: 30               # Auto-cleanup old screenshots

logging:
  level: "INFO"                  # DEBUG/INFO/WARNING/ERROR/CRITICAL
  format: "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

database:
  path: "db/telegram_automation.db"
  wal_mode: true                 # Write-Ahead Logging for concurrency
```

### CLI Usage

#### Initialization
```bash
cd tg-automatizamtion
python -m src.main init                          # Create DB and default config
```

#### Data Import
```bash
python -m src.main import-chats data/chats.txt       # Import target chats
python -m src.main import-messages data/messages.json # Import message templates
```

#### Profile Management
```bash
python -m src.main list-profiles                 # Show all Donut Browser profiles
python -m src.main list-profiles --db-only       # Show profiles in database
python -m src.main add-profile "ProfileName1" "ProfileName2"  # Add profiles to automation
```

#### Execution
```bash
python -m src.main start                         # Start all workers
python -m src.main start --workers 2             # Limit to 2 workers
python -m src.main status                        # Check progress
# Ctrl+C to gracefully stop workers
```

### Integration with Donut Browser

1. **Profile Discovery**: Scans `~/Library/Application Support/DonutBrowserDev/profiles/` for profile directories
2. **Metadata Reading**: Loads `metadata.json` from each profile for configuration
3. **Fingerprint Application**: Parses `camoufox_config.fingerprint` JSON and sets CAMOU_CONFIG_* env vars
4. **Proxy Usage**: Applies proxy from `camoufox_config.proxy` if configured
5. **Browser Data**: Uses `profile/` directory for persistent browser storage (cookies, localStorage)
6. **Executable Path**: Uses `camoufox_config.executable_path` to launch Camoufox browser

### Prerequisites

- Python 3.11+
- Playwright installed: `pip install playwright && playwright install firefox`
- Donut Browser with created and authorized profiles
- Each profile must be manually logged into Telegram (web.telegram.org/k) before automation

### Common Workflows

#### First-Time Setup
1. Create Donut Browser profiles with fingerprints and proxies
2. Manually log into Telegram on each profile (saves session in profile data)
3. Run `python -m src.main init` to create database
4. Edit `config.yaml` for rate limits and timeouts
5. Import chats and messages
6. Add profiles to automation
7. Run `python -m src.main start`

#### Monitoring
- View `logs/main.log` for general application flow
- View `logs/success.log` for successful sends
- View `logs/failed_chats.log` for chats not found
- View `logs/failed_send.log` for send errors (restrictions)
- Check `logs/screenshots/` for error screenshots
- Run `python -m src.main status` for queue statistics

#### Troubleshooting
- **Profile not found**: Check profile name with `list-profiles`
- **Fingerprint errors**: Ensure profile has valid fingerprint in Donut Browser
- **Telegram not loading**: Increase `page_load_timeout` in config.yaml
- **Chat search fails**: Check network/proxy, increase `search_timeout`
- **Account frozen**: Check screenshots, profile will be auto-blocked in database
