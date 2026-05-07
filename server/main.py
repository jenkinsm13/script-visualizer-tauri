"""FastAPI sidecar for the Script Visualizer Tauri app.

Endpoints (skeleton — flesh out as features land):
  GET  /healthz                 liveness
  POST /parse                   screenplay file → list of scenes
  POST /scenes/{i}/prompt       scene → image-gen prompt
  POST /scenes/{i}/render       prompt → generated storyboard frame
  GET  /styles                  available visual styles
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="script-visualizer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "project": "script-visualizer"}
