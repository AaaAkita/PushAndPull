# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **AutomaticScriptTool** — a visual automation workflow editor. Users drag-and-drop components in a web UI to build Playwright-based automation tasks. It supports Excel data-driven batch execution, smart element picking, and auto-login.

**Tech stack:** Python (Flask + Playwright + Pandas), vanilla JavaScript frontend, Tkinter launcher GUI.

## Common Commands

| Task | Command |
|------|---------|
| Install dependencies | `pip install -r requirements.txt` |
| Install Playwright browsers | `playwright install` |
| Run the application | `python launcher.py` |
| Run backend server directly (dev) | `python server.py` |
| Build distributable (PyInstaller) | `python build.py` |

**Development workflow:** Running `python launcher.py` opens a Tkinter window. Click **"启动服务"** to start the Flask server on `http://localhost:6115`, then **"打开编辑器界面"** to open the web UI in a browser. The server can also be started directly with `python server.py` for backend-only development.

The `build.py` script packages everything into `dist/AutomaticScriptTool/` using PyInstaller (`--windowed` for GUI mode). It also copies Chromium browsers from `%LOCALAPPDATA%\ms-playwright` into the distribution.

## High-Level Architecture

### Three-Layer Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend UI   │────▶│   Flask API     │────▶│ PlaywrightWorker│
│  (static/*.js)  │◄────│   (server.py)   │◄────│ (core/engine.py)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **Frontend** — Vanilla JS SPA served from `static/`. Step data is pure JSON. The UI posts step arrays to Flask endpoints.
2. **Flask API** (`server.py`) — REST endpoints for CRUD on flows (`/api/flows/*`), execution control (`/api/execution/*`), element picking (`/api/pick_selector`), and Excel introspection (`/api/get_excel_columns`).
3. **Playwright Engine** (`core/engine.py`) — A single `PlaywrightWorker` thread owns the browser lifecycle. All Playwright calls are dispatched through a `queue.Queue` to avoid threading issues. The worker persists browser context in `user_data/` so login sessions survive across runs.

### Execution Flow

When a flow runs:

1. `server.py` receives the step JSON and calls `execute_flow_async()` in `core/engine.py`.
2. `PlaywrightWorker._internal_run_steps()` is invoked on the worker thread.
3. The worker does a **first pass** over steps to find `excel_read` and `record_excel` configs, determining the Excel file path and the result column name.
4. Each Excel row becomes one iteration. For each row, the worker iterates steps, skipping `excel_read` and `record_excel` (those are metadata-only).
5. After each row, if a `record_excel` column is configured, the result ("成功" or failure reason) is written back to the Excel file.
6. Every 100 rows, the browser is restarted automatically to prevent memory leaks.
7. If the browser crashes (`"Target page, context or browser has been closed"`), it auto-restarts and continues to the next row.

### Step Registry Pattern

All automation actions are implemented as classes extending `BaseStep` (`core/steps/base.py`). New step types must be registered with `StepRegistry.register('type_name', StepClass)` in the module where the class is defined.

Current registered steps:
- `wait` — `WaitStep` (`core/steps/basic.py`)
- `open_url` — `OpenUrlStep` (`core/steps/basic.py`)
- `click` — `ClickStep` (`core/steps/interaction.py`)
- `input_text` — `InputTextStep` (`core/steps/interaction.py`)
- `label_input` — `LabelInputStep` (`core/steps/interaction.py`)
- `upload_file` — `UploadFileStep` (`core/steps/interaction.py`)
- `dropdown_select` — `DropdownSelectStep` (`core/steps/interaction.py`)
- `keyboard` — `KeyboardStep` (`core/steps/interaction.py`)

**To add a new step type:** create a class in `core/steps/` (existing or new file), implement `execute()` returning `bool`, and call `StepRegistry.register('my_step', MyStep)` at module level. The frontend must also be updated to render the step's config UI.

### Variable Interpolation

Step config strings support Excel column interpolation via `{ColumnName}` syntax. The `replace_variables()` function in `core/utils.py` replaces these placeholders with values from the current Excel row. This works across all step types automatically because `BaseStep.replace_vars()` wraps it.

### Selector Resolution

The `resolve_selector()` helper in `core/utils.py` automatically prefixes plain XPath selectors with `xpath=`. Selectors already containing ` >> `, or starting with `text=`, `css=`, `xpath=`, or `id=` are left untouched.

### Smart Element Picker

The element picker (`pick_debug_element`) injects JavaScript into the page that generates robust selectors with the following priority:
1. Static ID (filters out dynamic IDs with 4+ digits, Vue/React scoped IDs)
2. ElementUI dropdown items (`.el-select-dropdown`, `.el-autocomplete-suggestion`, etc.) using visible text
3. Visible text content (if unique across the page, or scoped by parent)
4. Unique class combination
5. Absolute XPath as fallback

### Tkinter Launcher & Packaged Mode

`launcher.py` has dual-mode behavior:
- **GUI mode (default):** opens a Tkinter window that spawns the Flask server as a subprocess.
- **Server mode (`--server` argument):** used by PyInstaller to run the backend from the packaged executable.

In packaged mode (`sys.frozen`), `PLAYWRIGHT_BROWSERS_PATH` is set to the `browsers/` folder bundled next to the executable.

### Auto-Login

`OpenUrlStep` and `PlaywrightWorker._handle_auto_login` both implement the same auto-login logic: after navigating to a URL, if the page redirects to a login page (detected by a configured username selector being visible), the credentials are filled and submitted, then the original target URL is re-opened.

### Flow Persistence

Flows are stored as JSON files in the `flows/` directory. Each file contains `{"steps": [...]}`. The `_get_flow_path()` helper in `server.py` secures filenames by using `os.path.basename()` and enforcing `.json` extension.

## Important Notes

- **Port:** The server hardcodes port `6115`. The launcher cleans up any process occupying this port on Windows via `netstat`/`taskkill`.
- **Browser data:** Persistent context uses `user_data/` as the user data directory. Do not delete this folder if you want to keep login sessions.
- **Logs:** Execution logs are written to `logs/execution_YYYY-MM-DD.log` and also kept in memory (`PlaywrightWorker.execution_logs`) for the status API.
- **Test mode:** Passing `mode='test'` to execution runs only the first Excel row and uses a 2-second Playwright timeout instead of 30 seconds.
- **Stop flag:** Flow execution checks `stop_flag.is_set()` at row boundaries and during wait sleeps. The stop API sets this flag; it does not force-kill the thread.
