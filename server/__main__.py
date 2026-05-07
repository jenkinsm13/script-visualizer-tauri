"""`python -m server` — uvicorn entry point for the Script Visualizer sidecar."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host="127.0.0.1",
        port=8767,
        reload=False,
        log_level="info",
    )
