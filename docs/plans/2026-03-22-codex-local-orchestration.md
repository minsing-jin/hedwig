# Hedwig Codex Local Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add repo-local bootstrap and wrappers so `oh-my-codex` and `ouroboros` run inside this repository without depending on user-home config.

**Architecture:** Keep installed packages under `./.tools`, keep Ouroboros home-scoped state under `./.local-home`, and use official OMX project scope for `./.codex`, `./.agents`, `./.omx`, and `./AGENTS.md`. Thin wrappers in `./bin` enforce the local paths and give stable entrypoints.

**Tech Stack:** POSIX shell, npm, uv, project Python 3.13, Codex CLI, oh-my-codex, ouroboros-ai

---

### Task 1: Ignore local tool state

**Files:**
- Modify: `.gitignore`

**Step 1: Add ignore rules**

Add ignore entries for repo-local tool installs and runtime state:

```gitignore
.tools/
.local-home/
.codex/
.agents/
.omx/
AGENTS.md
```

**Step 2: Verify ignore behavior**

Run: `git check-ignore -v .tools .local-home .codex .agents .omx AGENTS.md`
Expected: each path is matched by `.gitignore`

### Task 2: Add repo-local wrapper entrypoints

**Files:**
- Create: `bin/omx`
- Create: `bin/ooo`

**Step 1: Write wrapper scripts**

`bin/omx` should:

- resolve repo root
- require `./.tools/omx/node_modules/.bin/omx`
- export `CODEX_HOME="$ROOT/.codex"`
- export `OMX_MCP_WORKDIR_ROOTS="$ROOT"`
- exec the local OMX binary

`bin/ooo` should:

- resolve repo root
- require `./.tools/ouroboros-venv/bin/ouroboros`
- export `HOME="$ROOT/.local-home"`
- export `OUROBOROS_CLI_PATH="$ROOT/bin/omx"`
- exec the local Ouroboros binary

**Step 2: Verify wrappers are executable**

Run: `test -x bin/omx && test -x bin/ooo`
Expected: exit 0

### Task 3: Add bootstrap and doctor scripts

**Files:**
- Create: `scripts/setup-codex-local.sh`
- Create: `scripts/doctor-codex-local.sh`

**Step 1: Write bootstrap script**

Bootstrap should:

- assert `npm`, `node`, `uv`, `codex`, and `.venv/bin/python` exist
- install `oh-my-codex@0.9.0` into `./.tools/omx`
- install `ouroboros-ai==0.26.0b3` into `./.tools/ouroboros-venv`
- run local `omx setup --scope project`
- run local `ouroboros config init` under `HOME=./.local-home` if config is absent

**Step 2: Write doctor script**

Doctor should:

- check repo-local binary presence
- print versions from local OMX and Ouroboros
- verify expected repo-local directories exist

**Step 3: Verify script syntax**

Run: `bash -n scripts/setup-codex-local.sh && bash -n scripts/doctor-codex-local.sh`
Expected: exit 0

### Task 4: Run bootstrap and validate local setup

**Files:**
- Runtime only: `./.tools/`, `./.local-home/`, `./.codex/`, `./.agents/`, `./.omx/`, `./AGENTS.md`

**Step 1: Run bootstrap**

Run: `bash scripts/setup-codex-local.sh`
Expected: local installs complete and OMX project setup is applied

**Step 2: Run doctor**

Run: `bash scripts/doctor-codex-local.sh`
Expected: exit 0 and versions/path checks succeed

**Step 3: Smoke test wrappers**

Run: `bin/omx version`
Expected: local `oh-my-codex` version prints

Run: `bin/ooo --version`
Expected: local Ouroboros version prints

### Task 5: Summarize usage

**Files:**
- Modify: `README.md`

**Step 1: Add short local workflow section**

Document:

- `bash scripts/setup-codex-local.sh`
- `bin/omx`
- `bin/ooo init start "..."`
- `bash scripts/doctor-codex-local.sh`

**Step 2: Verify docs mention the exact local commands**

Run: `rg -n "setup-codex-local|doctor-codex-local|bin/omx|bin/ooo" README.md`
Expected: all commands are present
