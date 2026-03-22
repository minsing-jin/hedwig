# Claude Limit Auto Resume Design

**Date:** 2026-03-22

## Goal

Add an optional, project-scoped workflow that helps Claude Code recover from the 5-hour usage limit by waiting for reset and relaunching with session context preserved as much as practical.

## Constraints

- The feature must be opt-in.
- The feature must be scoped to this project only.
- The feature must be usable from Claude Code as a project skill.
- The machine can stay awake and logged in for the wait window.
- Claude Code's official `--resume` and `--continue` flows are available, but reported context loss after usage limits means recovery needs a local handoff layer as well.

## Chosen Approach

Use a project-level Claude skill plus a Python watchdog wrapper:

1. A project skill at `.claude/skills/claude-limit-auto-resume/` exposes `/claude-limit-auto-resume`.
2. The skill manages project-local config with `enable`, `disable`, `status`, and `doctor` actions.
3. A Python wrapper launches `claude` inside a PTY, mirrors terminal I/O, records a bounded transcript, and watches output for usage-limit messages.
4. When a limit hit is detected, the wrapper writes a project-local handoff file, waits for the reset window, then relaunches Claude with `--resume <session-id>` when possible, falling back to `--continue`.
5. On relaunch, the wrapper injects a short recovery prompt that points Claude at the saved handoff file if native resume context is incomplete.

## Why This Approach

It aligns with patterns used by popular process/session tools:

- `tmux-resurrect`: save enough session state to recover practical continuity
- `tmux-continuum`: keep recovery optional but automated once enabled
- `PM2`: supervise a long-running foreground process and apply restart policy
- `Supervisor`: separate runtime process management from application logic

This is a better fit than a detached monitor because a foreground wrapper can keep the same terminal session alive across child restarts. It is also more reliable than relying on Claude's native resume alone.

## Scope

### In scope

- Project-local Claude skill
- Project-local config and state files
- Wrapper command for managed Claude launches
- Usage-limit detection and delayed resume
- Local transcript/handoff persistence
- Unit tests for the critical logic
- README usage documentation

### Out of scope

- Perfect restoration of Claude's internal context
- Global shell alias installation
- macOS LaunchAgent automation
- Automatic takeover of an already-running unmanaged Claude session

## Runtime Model

### Enable flow

- User runs `/claude-limit-auto-resume enable` inside Claude Code or uses the Python CLI directly.
- The command writes `.claude/auto-resume/config.local.json` with `enabled: true` and runtime settings.

### Managed launch flow

- User starts Claude through the project wrapper instead of calling `claude` directly.
- The wrapper starts `claude` in a PTY and tracks:
  - latest matching Claude session id from `~/.claude/sessions/*.json`
  - rolling transcript buffer
  - whether usage-limit output was observed

### Resume flow

- When the child exits after a detected limit hit, the wrapper:
  - writes a handoff markdown file under `.claude/auto-resume/handoffs/`
  - waits for either a parsed reset time or the configured default wait window
  - relaunches Claude with `--resume <session-id>` or `--continue`
  - injects a short recovery note referencing the handoff file

## Files

- Create `.claude/skills/claude-limit-auto-resume/SKILL.md`
- Create `hedwig/claude_auto_resume.py`
- Create `scripts/claude-auto-resume`
- Create `tests/test_claude_auto_resume.py`
- Update `.gitignore`
- Update `README.md`

## Risks

- Claude output format for usage-limit messages may change.
- Native resume may still lose context despite the handoff layer.
- Transcript logging may capture sensitive prompts; docs must call this out.
- PTY behavior can differ across terminals.

## Verification

- Unit tests for config, session discovery, handoff generation, and limit parsing
- Manual smoke check of `enable`, `disable`, and `status`
- Manual wrapper dry-run against a fake limit transcript path if possible
