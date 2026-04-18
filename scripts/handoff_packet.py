"""
Handoff Packet Builder — package all Claude Code context for Codex.

Bundles seeds, recent commits, file tree, current state, and AC list
into a single markdown packet that a fresh Codex instance can read
and execute against.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path("/Users/jinminseong/Desktop/hedwig")
HANDOFF_DIR = REPO / ".handoff"
HANDOFF_DIR.mkdir(exist_ok=True)


def git(cmd: list[str]) -> str:
    return subprocess.run(["git", *cmd], cwd=REPO, capture_output=True, text=True).stdout.strip()


def build_handoff_packet(seed_path: Path, packet_id: str | None = None) -> Path:
    """Build a complete handoff packet for Codex."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    packet_id = packet_id or f"handoff_{timestamp}"
    out_path = HANDOFF_DIR / f"{packet_id}.md"

    seed = yaml.safe_load(seed_path.read_text())

    parts = [
        f"# Hedwig Handoff Packet — {packet_id}",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "## Mission",
        "",
        "You are Codex, receiving a handoff from Claude Code.",
        "Claude Code has been managing this Hedwig v3.0 SaaS project and is now",
        "delegating implementation work to you. Your job: execute the acceptance",
        "criteria below, then perform self-review on your work.",
        "",
        "After you finish, a SEPARATE fresh Codex instance will independently",
        "review your changes. Be thorough.",
        "",
        "## Project Context",
        "",
        "**Hedwig v3.0** — Self-evolving personal AI signal radar with SaaS conversion.",
        "Core moats: Socratic onboarding, self-evolving algorithm, boolean feedback,",
        "long-horizon memory, algorithm sovereignty, Devil's Advocate.",
        "",
        f"**Repo**: `{REPO}`",
        f"**Branch**: `{git(['rev-parse', '--abbrev-ref', 'HEAD'])}`",
        f"**Latest commit**: `{git(['log', '-1', '--oneline'])}`",
        "",
        "## Recent Commits (last 10)",
        "",
        "```",
        git(["log", "--oneline", "-10"]),
        "```",
        "",
        "## File Tree (hedwig/)",
        "",
        "```",
        subprocess.run(
            ["find", "hedwig", "-type", "f", "-name", "*.py"],
            cwd=REPO, capture_output=True, text=True,
        ).stdout.strip(),
        "```",
        "",
        "## Goal",
        "",
        seed.get("goal", "(no goal)"),
        "",
        "## Constraints",
        "",
    ]

    for c in seed.get("constraints", []):
        parts.append(f"- {c}")

    parts += ["", "## Acceptance Criteria", ""]
    for i, ac in enumerate(seed.get("acceptance_criteria", []), 1):
        parts.append(f"{i}. {ac}")

    parts += [
        "",
        "## Evaluation Principles",
        "",
    ]
    for p in seed.get("evaluation_principles", []):
        if isinstance(p, dict):
            parts.append(f"- **{p.get('name')}** ({p.get('weight', 'N/A')}): {p.get('description')}")

    parts += [
        "",
        "## Exit Conditions",
        "",
    ]
    for e in seed.get("exit_conditions", []):
        if isinstance(e, dict):
            parts.append(f"- **{e.get('name')}**: {e.get('criteria')}")

    parts += [
        "",
        "## Workflow",
        "",
        "1. **Read each AC** carefully",
        "2. **Plan** which files to create/modify",
        "3. **Execute** — write code, run tests",
        "4. **Self-review** — re-read your changes, check for issues",
        "5. **Commit** each AC's changes separately with clear messages",
        "6. **Report** what you did and what's blocking (if anything)",
        "",
        "## Available Commands",
        "",
        "```bash",
        ".venv/bin/python -m pytest tests/ -v       # run all tests",
        ".venv/bin/python -m hedwig --sources       # list source plugins",
        ".venv/bin/python -m hedwig --dashboard --saas --port 8765  # SaaS mode",
        "```",
        "",
        "## Current Pending Tests Status",
        "",
        "Run `.venv/bin/python -m pytest tests/ -v --tb=no -q` to see baseline.",
        "All 171 tests should pass before you start.",
        "",
        "## Reporting Format",
        "",
        "After each AC, write a status block:",
        "```",
        "[AC N] STATUS: pass|fail|skip",
        "Files changed: ...",
        "Tests run: ...",
        "Notes: ...",
        "```",
    ]

    out_path.write_text("\n".join(parts))
    print(f"✅ Handoff packet written: {out_path}")
    print(f"   Size: {out_path.stat().st_size:,} bytes")
    return out_path


if __name__ == "__main__":
    import sys
    seed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "seed.ralph.yaml"
    build_handoff_packet(seed_path)
