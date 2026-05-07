# Script Visualizer (Tauri rewrite)

A reimplementation of the original `~/Projects/script_visualizer` (PySide6) as a
Tauri + Svelte desktop app on a Python FastAPI sidecar. Parses a screenplay
(PDF / Fountain / plain text) and generates storyboard images for each scene
via local or hosted image-generation models.

## Architecture

```
script-visualizer-tauri/
├── pyproject.toml        Python deps (uv-managed)
├── src/
│   ├── core/             screenplay parsing, scene model, prompt structure
│   │   ├── parser.py
│   │   ├── scene.py
│   │   └── prompt_structure.py
│   ├── ai/               image-gen + analysis clients
│   │   ├── sd_connector.py
│   │   ├── style_manager.py
│   │   ├── asset_manager.py
│   │   └── visual_analysis.py
│   └── utils/
├── server/               FastAPI sidecar (uvicorn on 127.0.0.1:8767)
│   ├── __main__.py
│   └── main.py
└── ui/                   Tauri 2 + Svelte 5 + TypeScript
    ├── src/              Svelte frontend
    └── src-tauri/        Rust shell, auto-spawns `python -m server`
```

The Rust shell spawns the Python sidecar on app launch and reaps it on exit.
Override the Python binary with env var `SV_PYTHON=/path/to/python`. Set
`SV_NO_SIDECAR=1` to opt out of auto-spawn (useful when running the server
yourself in another terminal during dev).

## Origin

Lifted from `~/Projects/script_visualizer` (originally in iCloud, moved
2026-05-07). The original `core/` and `ai/` modules were copied into `src/`
verbatim — they're the working logic and don't need rewriting. The PySide6
GUI in the original `gui/` is being replaced by the Tauri+Svelte UI.

## Build / run

### First-time setup
```bash
# Python (uv-managed, mise Python 3.12+)
uv venv
uv pip install -e '.[dev]'  # if you add dev extras
# or:
uv pip install -e .

# UI deps
cd ui && pnpm install
```

### Dev
```bash
# Terminal 1 — run the server yourself if iterating on Python
cd ~/Projects/script-visualizer-tauri
.venv/bin/python -m server

# Terminal 2 — Tauri (will auto-spawn server if SV_NO_SIDECAR isn't set)
cd ui
SV_NO_SIDECAR=1 pnpm tauri dev   # if your own server is running
# or just:
pnpm tauri dev                    # let Tauri spawn the server
```

### Release build
```bash
cd ui
pnpm tauri build
```

## Conventions

- **Python deps** managed by uv. Always `uv add <pkg>` — never raw `pip install`.
- **Node deps** managed by pnpm.
- **Python version** from mise (3.12). Never the Homebrew system Python.
- `src/core` and `src/ai` are pure Python — no UI imports. The server module
  wraps them with HTTP endpoints.
- Image generation backends are swappable via `src/ai/sd_connector.py`. Default
  to local (Automatic1111 / Comfy / MLX-Diffusion) when possible; cloud is
  opt-in via `.env` API keys.

## TODO

- Wire `/parse` endpoint to `src/core/parser.py`
- Wire `/render` endpoint to `src/ai/sd_connector.py`
- File picker in UI (use `@tauri-apps/plugin-dialog`)
- Storyboard grid view in UI
- Style selector tied to `src/ai/style_manager.py`
