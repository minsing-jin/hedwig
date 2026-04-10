"""
Hedwig Native App — wraps the FastAPI dashboard in a native window.

Uses pywebview for lightweight cross-platform native windows.
Starts the dashboard server in a background thread, then opens a native
window pointing to it.

Run with:
    python -m hedwig --native
    # or
    python -m hedwig.native.app
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8766  # different from dashboard default to avoid conflicts
DEFAULT_HOST = "127.0.0.1"


def _run_server(host: str, port: int):
    """Run the FastAPI dashboard in the current thread."""
    import uvicorn
    from hedwig.dashboard.app import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def run_native(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    width: int = 1280,
    height: int = 800,
):
    """Start Hedwig as a native desktop app."""
    try:
        import webview
    except ImportError:
        print("\n❌ pywebview not installed. Install with:")
        print("   uv pip install pywebview")
        print("\nOn macOS, also install pyobjc:")
        print("   uv pip install pyobjc\n")
        raise SystemExit(1)

    # Start server in background thread
    print("🦉 Starting Hedwig backend...")
    server_thread = threading.Thread(
        target=_run_server,
        args=(host, port),
        daemon=True,
    )
    server_thread.start()

    # Wait for server to be ready
    import httpx
    url = f"http://{host}:{port}"
    for _ in range(50):  # 5 seconds max
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code in (200, 303):
                break
        except Exception:
            time.sleep(0.1)

    print(f"🦉 Opening Hedwig native window...")

    # Create native window
    window = webview.create_window(
        title="Hedwig — AI Signal Radar",
        url=url,
        width=width,
        height=height,
        resizable=True,
        min_size=(800, 600),
        background_color="#0d0f14",
    )

    webview.start(debug=False)


if __name__ == "__main__":
    run_native()
