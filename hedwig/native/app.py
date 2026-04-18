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
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from hedwig.native.updater import check_latest_version

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8766  # different from dashboard default to avoid conflicts
DEFAULT_HOST = "127.0.0.1"
NATIVE_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "hedwig-icon.svg"


def _run_server(host: str, port: int):
    """Run the FastAPI dashboard in the current thread."""
    import uvicorn
    from hedwig.dashboard.app import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def get_native_icon_path() -> Path | None:
    """Return the bundled native icon path when the asset exists."""
    if NATIVE_ICON_PATH.exists():
        return NATIVE_ICON_PATH
    return None


def _apply_macos_app_icon(icon_path: Path) -> None:
    """Apply the native app icon through AppKit on macOS."""
    if sys.platform != "darwin":
        return

    try:
        import AppKit
    except ImportError:
        logger.info("PyObjC not installed; macOS app bundles should set the icon during packaging")
        return

    image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(icon_path))
    if image is None:
        logger.warning("Unable to load native icon asset from %s", icon_path)
        return

    AppKit.NSApplication.sharedApplication().setApplicationIconImage_(image)


def _notify_update_available(current_version: str, latest_version: str) -> None:
    message = (
        f"Update available: Hedwig v{latest_version} is available "
        f"(current v{current_version})"
    )
    logger.info(message)
    print(f"🦉 {message}")


def _start_update_check(
    notify_update: Callable[[str, str], None] | None = None,
) -> threading.Thread:
    """Check GitHub releases in the background during native startup."""

    def _worker() -> None:
        current_version, latest_version, is_update_available = check_latest_version()
        if is_update_available:
            notifier = notify_update or _notify_update_available
            notifier(current_version, latest_version)

    update_thread = threading.Thread(target=_worker, daemon=True, name="hedwig-update-check")
    update_thread.start()
    return update_thread


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
    url = f"http://{host}:{port}"
    for _ in range(50):  # 5 seconds max
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code in (200, 303):
                break
        except Exception:
            time.sleep(0.1)

    print("🦉 Opening Hedwig native window...")
    icon_path = get_native_icon_path()
    if icon_path is not None:
        _apply_macos_app_icon(icon_path)

    # Create native window
    webview.create_window(
        title="Hedwig — AI Signal Radar",
        url=url,
        width=width,
        height=height,
        resizable=True,
        min_size=(800, 600),
        background_color="#0d0f14",
    )

    _start_update_check()
    webview.start(debug=False)


if __name__ == "__main__":
    run_native()
