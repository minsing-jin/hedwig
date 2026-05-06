"""Cron auto-install — write the standard 3 jobs to user's crontab.

Idempotent: re-running replaces the Hedwig block, doesn't duplicate
entries. The block is delimited by markers so we can safely remove it
later via ``uninstall_cron()``.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

START_MARKER = "# >>> hedwig cron jobs (auto-installed) >>>"
END_MARKER = "# <<< hedwig cron jobs <<<"


def _hedwig_python() -> str:
    """Path to the python that is currently running this Hedwig install."""
    return sys.executable


def _hedwig_dir() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _build_block(daily: str = "0 9 * * *", weekly: str = "0 10 * * 1",
                 critical: bool = True) -> str:
    py = _hedwig_python()
    cwd = _hedwig_dir()
    lines = [START_MARKER]
    lines.append(f'{daily}  cd {cwd} && {py} -m hedwig')
    lines.append(f'{weekly}  cd {cwd} && {py} -m hedwig --weekly')
    if critical:
        lines.append(f'@reboot   cd {cwd} && {py} -m hedwig --critical-loop')
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def _read_crontab() -> str:
    if not shutil.which("crontab"):
        return ""
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _write_crontab(content: str) -> tuple[bool, str]:
    if not shutil.which("crontab"):
        return False, "`crontab` command not found on PATH"
    try:
        proc = subprocess.run(
            ["crontab", "-"], input=content, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return False, proc.stderr.strip() or "crontab write failed"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def _strip_existing_block(content: str) -> str:
    """Remove the previous Hedwig block (between START/END markers)."""
    if START_MARKER not in content or END_MARKER not in content:
        return content
    before, _, rest = content.partition(START_MARKER)
    _, _, after = rest.partition(END_MARKER)
    # Clean up surrounding blank lines
    return (before.rstrip() + "\n" + after.lstrip("\n")).strip() + "\n" if (before or after) else ""


def install_cron(
    daily: str = "0 9 * * *",
    weekly: str = "0 10 * * 1",
    critical: bool = True,
) -> dict:
    """Install or replace the Hedwig cron block. Returns status dict."""
    if not shutil.which("crontab"):
        return {
            "ok": False,
            "error": "`crontab` not on PATH (Windows? Use Task Scheduler manually)",
            "block": _build_block(daily, weekly, critical),
        }
    current = _read_crontab()
    stripped = _strip_existing_block(current)
    new_content = (stripped.rstrip() + "\n\n" + _build_block(daily, weekly, critical)).lstrip()
    ok, msg = _write_crontab(new_content)
    return {"ok": ok, "message": msg,
            "installed_block": _build_block(daily, weekly, critical)}


def uninstall_cron() -> dict:
    if not shutil.which("crontab"):
        return {"ok": False, "error": "`crontab` not on PATH"}
    current = _read_crontab()
    if START_MARKER not in current:
        return {"ok": True, "message": "no Hedwig block found", "removed": False}
    stripped = _strip_existing_block(current)
    ok, msg = _write_crontab(stripped)
    return {"ok": ok, "message": msg, "removed": True}


def cron_status() -> dict:
    """Inspect — is Hedwig already in crontab?"""
    current = _read_crontab()
    installed = START_MARKER in current and END_MARKER in current
    block = ""
    if installed:
        _, _, rest = current.partition(START_MARKER)
        block_body, _, _ = rest.partition(END_MARKER)
        block = (START_MARKER + block_body + END_MARKER).strip()
    return {
        "installed": installed,
        "crontab_available": bool(shutil.which("crontab")),
        "block": block,
        "preview": _build_block(),
    }
