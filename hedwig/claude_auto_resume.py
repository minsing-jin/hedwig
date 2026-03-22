from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
import subprocess
import sys
import termios
import time
import tty
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_WAIT_SECONDS = 5 * 60 * 60
DEFAULT_TRANSCRIPT_LINES = 400
SESSION_DIR = Path.home() / ".claude" / "sessions"
LIMIT_EPOCH_RE = re.compile(r"usage limit reached\|(?P<ts>\d{10,})", re.IGNORECASE)


@dataclass(eq=True)
class AutoResumeConfig:
    enabled: bool = False
    wait_seconds: int = DEFAULT_WAIT_SECONDS
    transcript_lines: int = DEFAULT_TRANSCRIPT_LINES


@dataclass
class LimitEvent:
    raw_message: str
    reset_at: datetime | None
    wait_seconds: int


@dataclass
class RunResult:
    exit_code: int
    session_id: str | None
    limit_event: LimitEvent | None


def project_auto_resume_dir(project_dir: Path) -> Path:
    return project_dir / ".claude" / "auto-resume"


def config_path(project_dir: Path) -> Path:
    return project_auto_resume_dir(project_dir) / "config.local.json"


def handoff_dir(project_dir: Path) -> Path:
    return project_auto_resume_dir(project_dir) / "handoffs"


def ensure_runtime_dirs(project_dir: Path) -> None:
    project_auto_resume_dir(project_dir).mkdir(parents=True, exist_ok=True)
    handoff_dir(project_dir).mkdir(parents=True, exist_ok=True)


def load_config(project_dir: Path) -> AutoResumeConfig:
    path = config_path(project_dir)
    if not path.exists():
        return AutoResumeConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AutoResumeConfig(
        enabled=bool(data.get("enabled", False)),
        wait_seconds=int(data.get("wait_seconds", DEFAULT_WAIT_SECONDS)),
        transcript_lines=int(data.get("transcript_lines", DEFAULT_TRANSCRIPT_LINES)),
    )


def save_config(project_dir: Path, config: AutoResumeConfig) -> Path:
    ensure_runtime_dirs(project_dir)
    path = config_path(project_dir)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def set_enabled(
    project_dir: Path,
    enabled: bool,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
    transcript_lines: int = DEFAULT_TRANSCRIPT_LINES,
) -> AutoResumeConfig:
    current = load_config(project_dir)
    config = AutoResumeConfig(
        enabled=enabled,
        wait_seconds=wait_seconds if enabled else current.wait_seconds,
        transcript_lines=transcript_lines if enabled else current.transcript_lines,
    )
    save_config(project_dir, config)
    return config


def parse_usage_limit_event(
    text: str,
    now: datetime | None = None,
    default_wait_seconds: int = DEFAULT_WAIT_SECONDS,
) -> LimitEvent | None:
    lower = text.lower()
    if "usage limit reached" not in lower:
        return None

    now = now or datetime.now(timezone.utc)
    epoch_match = LIMIT_EPOCH_RE.search(text)
    if epoch_match:
        reset_at = datetime.fromtimestamp(int(epoch_match.group("ts")), tz=timezone.utc)
        wait_seconds = max(0, int((reset_at - now).total_seconds()))
        return LimitEvent(raw_message=text.strip(), reset_at=reset_at, wait_seconds=wait_seconds)

    return LimitEvent(raw_message=text.strip(), reset_at=None, wait_seconds=default_wait_seconds)


def find_latest_session_id(project_dir: Path, sessions_dir: Path = SESSION_DIR) -> str | None:
    project_dir = project_dir.resolve()
    newest_started_at = -1
    newest_session_id: str | None = None

    if not sessions_dir.exists():
        return None

    for path in sessions_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw_cwd = data.get("cwd")
        session_id = data.get("sessionId")
        if not raw_cwd or not session_id:
            continue
        try:
            cwd = Path(raw_cwd).resolve()
        except OSError:
            continue
        if cwd != project_dir:
            continue
        started_at = int(data.get("startedAt", 0))
        if started_at > newest_started_at:
            newest_started_at = started_at
            newest_session_id = str(session_id)

    return newest_session_id


def write_handoff(
    project_dir: Path,
    session_id: str | None,
    transcript_lines: list[str],
    reason: str,
) -> Path:
    ensure_runtime_dirs(project_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = handoff_dir(project_dir) / f"{timestamp}-{reason}.md"
    excerpt = "\n".join(transcript_lines[-DEFAULT_TRANSCRIPT_LINES:])
    content = (
        "# Claude Auto Resume Handoff\n\n"
        f"- Generated: {datetime.now(timezone.utc).isoformat()}\n"
        f"- Project: `{project_dir}`\n"
        f"- Session ID: `{session_id or 'unknown'}`\n"
        f"- Reason: `{reason}`\n\n"
        "## Recovery Instructions\n\n"
        "Native Claude resume may lose some context after a usage limit.\n"
        "Use the current resumed session first. If context seems degraded, read this file and continue from the recent transcript excerpt below.\n\n"
        "## Recent Transcript Excerpt\n\n"
        "```text\n"
        f"{excerpt}\n"
        "```\n"
    )
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def build_resume_command(command: str, session_id: str | None) -> list[str]:
    if session_id:
        return [command, "--resume", session_id]
    return [command, "--continue"]


def wait_seconds_for_limit_event(event: LimitEvent, config: AutoResumeConfig) -> int:
    if event.reset_at is not None:
        return max(0, event.wait_seconds)
    return max(0, config.wait_seconds)


def append_transcript(transcript: deque[str], chunk: bytes) -> None:
    text = chunk.decode("utf-8", errors="replace").replace("\r", "")
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped:
            transcript.append(stripped)


def build_resume_note(handoff_path: Path) -> bytes:
    message = (
        "Auto-resume note: this session was restarted after a Claude usage limit. "
        f"If native resume context is incomplete, read `{handoff_path}` and continue from there."
    )
    return (message + "\n").encode("utf-8")


def run_pipe_command(
    argv: list[str],
    project_dir: Path,
    transcript: deque[str],
    default_wait_seconds: int,
    resume_note: bytes | None = None,
) -> RunResult:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if resume_note and process.stdin:
        process.stdin.write(resume_note)
        process.stdin.flush()

    session_id = None
    recent_output = ""
    limit_event = None

    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.readline(), b""):
        if not chunk:
            break
        os.write(sys.stdout.fileno(), chunk)
        append_transcript(transcript, chunk)
        recent_output = (recent_output + chunk.decode("utf-8", errors="replace"))[-8000:]
        if session_id is None:
            session_id = find_latest_session_id(project_dir)
        if limit_event is None:
            limit_event = parse_usage_limit_event(recent_output, default_wait_seconds=default_wait_seconds)

    returncode = process.wait()
    return RunResult(exit_code=returncode, session_id=session_id, limit_event=limit_event)


def run_pty_command(
    argv: list[str],
    project_dir: Path,
    transcript: deque[str],
    default_wait_seconds: int,
    resume_note: bytes | None = None,
) -> RunResult:
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    old_attrs = None
    session_id = None
    recent_output = ""
    limit_event = None
    pid, master_fd = pty.fork()

    if pid == 0:
        os.execvp(argv[0], argv)

    if os.isatty(stdin_fd):
        old_attrs = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

    try:
        injected_note = False
        while True:
            read_fds = [master_fd]
            if os.isatty(stdin_fd):
                read_fds.append(stdin_fd)

            ready, _, _ = select.select(read_fds, [], [], 0.1)

            if master_fd in ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                os.write(stdout_fd, chunk)
                append_transcript(transcript, chunk)
                recent_output = (recent_output + chunk.decode("utf-8", errors="replace"))[-8000:]
                if session_id is None:
                    session_id = find_latest_session_id(project_dir)
                if limit_event is None:
                    limit_event = parse_usage_limit_event(recent_output, default_wait_seconds=default_wait_seconds)

            if resume_note and not injected_note:
                time.sleep(0.2)
                os.write(master_fd, resume_note)
                injected_note = True

            if stdin_fd in ready:
                try:
                    user_chunk = os.read(stdin_fd, 1024)
                except OSError:
                    user_chunk = b""
                if user_chunk:
                    os.write(master_fd, user_chunk)

            waited_pid, status = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                exit_code = os.waitstatus_to_exitcode(status)
                return RunResult(exit_code=exit_code, session_id=session_id, limit_event=limit_event)

    finally:
        if old_attrs is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_attrs)
        try:
            os.close(master_fd)
        except OSError:
            pass

    _, status = os.waitpid(pid, 0)
    return RunResult(
        exit_code=os.waitstatus_to_exitcode(status),
        session_id=session_id,
        limit_event=limit_event,
    )


def run_claude_with_auto_resume(project_dir: Path, argv: list[str], config: AutoResumeConfig) -> int:
    transcript: deque[str] = deque(maxlen=max(50, config.transcript_lines))
    current_argv = argv
    resume_note: bytes | None = None

    while True:
        if os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno()):
            result = run_pty_command(
                current_argv,
                project_dir,
                transcript,
                default_wait_seconds=config.wait_seconds,
                resume_note=resume_note,
            )
        else:
            result = run_pipe_command(
                current_argv,
                project_dir,
                transcript,
                default_wait_seconds=config.wait_seconds,
                resume_note=resume_note,
            )

        if not config.enabled or result.limit_event is None:
            return result.exit_code

        session_id = result.session_id or find_latest_session_id(project_dir)
        handoff_path = write_handoff(
            project_dir,
            session_id=session_id,
            transcript_lines=list(transcript),
            reason="usage-limit",
        )
        wait_seconds = wait_seconds_for_limit_event(result.limit_event, config)
        print(
            f"\n[claude-auto-resume] Usage limit detected. Waiting {wait_seconds} seconds before relaunch.",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)
        current_argv = build_resume_command(argv[0], session_id)
        resume_note = build_resume_note(handoff_path)


def status_payload(project_dir: Path) -> dict[str, object]:
    config = load_config(project_dir)
    latest_session_id = find_latest_session_id(project_dir)
    return {
        "project_dir": str(project_dir),
        "enabled": config.enabled,
        "wait_seconds": config.wait_seconds,
        "transcript_lines": config.transcript_lines,
        "config_path": str(config_path(project_dir)),
        "latest_session_id": latest_session_id,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project-scoped Claude Code auto-resume helper")
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project root that owns the .claude/auto-resume state",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    enable = subparsers.add_parser("enable", help="Enable project-local Claude limit auto-resume")
    enable.add_argument("--wait-seconds", type=int, default=DEFAULT_WAIT_SECONDS)
    enable.add_argument("--transcript-lines", type=int, default=DEFAULT_TRANSCRIPT_LINES)

    subparsers.add_parser("disable", help="Disable project-local Claude limit auto-resume")
    subparsers.add_parser("status", help="Show project-local Claude limit auto-resume status")
    subparsers.add_parser("doctor", help="Show project-local Claude limit auto-resume diagnostics")

    wrap = subparsers.add_parser("wrap", help="Run Claude under the project watchdog")
    wrap.add_argument("claude_args", nargs=argparse.REMAINDER)

    return parser


def handle_enable(args: argparse.Namespace, project_dir: Path) -> int:
    config = set_enabled(
        project_dir,
        True,
        wait_seconds=args.wait_seconds,
        transcript_lines=args.transcript_lines,
    )
    path = config_path(project_dir)
    print(f"Enabled project-local Claude auto-resume at {path}")
    print(f"Future managed sessions: ./scripts/claude-auto-resume wrap -- claude")
    print(json.dumps(asdict(config), indent=2))
    return 0


def handle_disable(project_dir: Path) -> int:
    config = set_enabled(project_dir, False)
    print(f"Disabled project-local Claude auto-resume at {config_path(project_dir)}")
    print(json.dumps(asdict(config), indent=2))
    return 0


def handle_status(project_dir: Path) -> int:
    print(json.dumps(status_payload(project_dir), indent=2))
    return 0


def handle_doctor(project_dir: Path) -> int:
    payload = status_payload(project_dir)
    payload["sessions_dir"] = str(SESSION_DIR)
    payload["sessions_dir_exists"] = SESSION_DIR.exists()
    payload["handoff_dir"] = str(handoff_dir(project_dir))
    print(json.dumps(payload, indent=2))
    return 0


def handle_wrap(args: argparse.Namespace, project_dir: Path) -> int:
    claude_args = list(args.claude_args)
    if claude_args and claude_args[0] == "--":
        claude_args = claude_args[1:]
    argv = claude_args or ["claude"]
    config = load_config(project_dir)
    return run_claude_with_auto_resume(project_dir, argv, config)


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    project_dir = Path(args.project_dir).resolve()

    if args.command == "enable":
        return handle_enable(args, project_dir)
    if args.command == "disable":
        return handle_disable(project_dir)
    if args.command == "status":
        return handle_status(project_dir)
    if args.command == "doctor":
        return handle_doctor(project_dir)
    if args.command == "wrap":
        return handle_wrap(args, project_dir)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
