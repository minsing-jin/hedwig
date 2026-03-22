# Claude Limit Auto Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a project-scoped Claude Code skill and watchdog wrapper that optionally waits through usage limits and relaunches Claude with a saved handoff.

**Architecture:** A project skill calls a Python module that manages opt-in config and runtime inspection. Managed Claude sessions run through a PTY wrapper that captures a bounded transcript, finds the active Claude session id, detects usage-limit output, writes a recovery handoff, waits, and relaunches Claude with resume semantics.

**Tech Stack:** Python 3.10+, pytest, Claude Code project skills

---

### Task 1: Planning Docs

**Files:**
- Create: `docs/plans/2026-03-22-claude-limit-auto-resume-design.md`
- Create: `docs/plans/2026-03-22-claude-limit-auto-resume.md`

**Step 1: Write the planning docs**

Save the approved design and implementation plan.

**Step 2: Verify the files exist**

Run: `ls docs/plans`
Expected: both plan files are listed

### Task 2: Red Tests For Core Logic

**Files:**
- Create: `tests/test_claude_auto_resume.py`
- Modify: `hedwig/claude_auto_resume.py`

**Step 1: Write failing tests**

Cover:
- config enable/disable round-trip
- parsing limit-reset messages
- discovering matching Claude session ids from `~/.claude/sessions`
- building a recovery handoff file

**Step 2: Run the test file to verify it fails**

Run: `pytest tests/test_claude_auto_resume.py -q`
Expected: import or attribute failures because the module does not exist yet

### Task 3: Minimal Runtime Implementation

**Files:**
- Create: `hedwig/claude_auto_resume.py`

**Step 1: Implement config helpers**

Add project-local config and state path helpers.

**Step 2: Implement parsing/session discovery helpers**

Add functions for limit detection, reset wait calculation, and session file lookup.

**Step 3: Implement handoff writer**

Create a bounded recovery markdown file in `.claude/auto-resume/handoffs/`.

**Step 4: Implement CLI commands**

Support `enable`, `disable`, `status`, `doctor`, and `wrap`.

**Step 5: Re-run tests**

Run: `pytest tests/test_claude_auto_resume.py -q`
Expected: tests pass

### Task 4: Skill And Wrapper

**Files:**
- Create: `.claude/skills/claude-limit-auto-resume/SKILL.md`
- Create: `scripts/claude-auto-resume`
- Modify: `.gitignore`

**Step 1: Add the project skill**

Expose `/claude-limit-auto-resume` as a manual task skill with argument routing.

**Step 2: Add the shell wrapper**

Delegate to `python -m hedwig.claude_auto_resume`.

**Step 3: Ignore local runtime state**

Ignore `.claude/auto-resume/` while keeping `.claude/skills/` tracked.

**Step 4: Verify wrapper help**

Run: `./scripts/claude-auto-resume status`
Expected: prints disabled/enabled status without crashing

### Task 5: Documentation

**Files:**
- Modify: `README.md`

**Step 1: Document the workflow**

Explain:
- this is project-only
- feature is opt-in
- current sessions are not retroactively wrapped
- use the wrapper for future managed sessions

**Step 2: Verify docs mention the skill**

Run: `rg -n "claude-limit-auto-resume|claude-auto-resume" README.md .claude/skills/claude-limit-auto-resume/SKILL.md`
Expected: both references exist

### Task 6: Final Verification

**Files:**
- Verify all touched files

**Step 1: Run focused tests**

Run: `pytest tests/test_claude_auto_resume.py -q`
Expected: pass

**Step 2: Run smoke commands**

Run:
- `python -m hedwig.claude_auto_resume enable`
- `python -m hedwig.claude_auto_resume status`
- `python -m hedwig.claude_auto_resume disable`
- `python -m hedwig.claude_auto_resume status`

Expected:
- enable writes config
- status reflects enabled state
- disable flips state back off

**Step 3: Commit**

```bash
git add docs/plans/2026-03-22-claude-limit-auto-resume-design.md docs/plans/2026-03-22-claude-limit-auto-resume.md tests/test_claude_auto_resume.py hedwig/claude_auto_resume.py .claude/skills/claude-limit-auto-resume/SKILL.md scripts/claude-auto-resume .gitignore README.md
git commit -m "feat: add project-scoped claude auto resume skill"
```
