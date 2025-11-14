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
