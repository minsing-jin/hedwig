"""
Menubar tray icon for Hedwig — macOS-style.

Uses rumps for macOS menubar integration.
Click the tray icon for quick actions: open dashboard, run daily, quit.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)


def run_tray():
    """Start Hedwig as a menubar tray app."""
    try:
        import rumps
    except ImportError:
        print("\n❌ rumps not installed (macOS only). Install with:")
        print("   uv pip install rumps\n")
        raise SystemExit(1)

    # Start backend server in a thread
    from hedwig.native.app import _run_server

    DASHBOARD_URL = "http://127.0.0.1:8765"
    server_thread = threading.Thread(
        target=_run_server,
        args=("127.0.0.1", 8765),
        daemon=True,
    )
    server_thread.start()

    class HedwigTrayApp(rumps.App):
        def __init__(self):
            super().__init__("🦉", title="🦉", quit_button=None)
            self.menu = [
                "Open Dashboard",
                "Run Daily Pipeline",
                "Run Dry (collect only)",
                "Run Weekly",
                None,  # separator
                "Socratic Onboarding",
                "View Signals",
                "Edit Criteria",
                None,
                "Quit Hedwig",
            ]

        @rumps.clicked("Open Dashboard")
        def open_dashboard(self, _):
            webbrowser.open(DASHBOARD_URL)

        @rumps.clicked("Run Daily Pipeline")
        def run_daily(self, _):
            subprocess.Popen([sys.executable, "-m", "hedwig"], cwd=str(Path.cwd()))
            rumps.notification("Hedwig", "Daily Pipeline", "Started in background")

        @rumps.clicked("Run Dry (collect only)")
        def run_dry(self, _):
            subprocess.Popen([sys.executable, "-m", "hedwig", "--dry-run"], cwd=str(Path.cwd()))
            rumps.notification("Hedwig", "Dry Run", "Collecting...")

        @rumps.clicked("Run Weekly")
        def run_weekly(self, _):
            subprocess.Popen([sys.executable, "-m", "hedwig", "--weekly"], cwd=str(Path.cwd()))
            rumps.notification("Hedwig", "Weekly Pipeline", "Started")

        @rumps.clicked("Socratic Onboarding")
        def onboarding(self, _):
            webbrowser.open(f"{DASHBOARD_URL}/onboarding")

        @rumps.clicked("View Signals")
        def signals(self, _):
            webbrowser.open(f"{DASHBOARD_URL}/signals")

        @rumps.clicked("Edit Criteria")
        def criteria(self, _):
            webbrowser.open(f"{DASHBOARD_URL}/criteria")

        @rumps.clicked("Quit Hedwig")
        def quit_app(self, _):
            rumps.quit_application()

    HedwigTrayApp().run()


if __name__ == "__main__":
    run_tray()
