# Hedwig Codex Local Orchestration Design

**Date:** 2026-03-22

## Goal

Make `ouroboros` and `oh-my-codex` usable for Codex workflows inside this repository only, without relying on persistent global shell configuration or writing tool state into the user's home directory.

## Constraints

- Keep existing user changes intact.
- Do not require global `npm install -g` or global `uv tool install` for day-to-day use in this repo.
- Allow repo-local runtime state and caches, but keep them out of git by default.
- Reuse official `oh-my-codex` project-scope setup because it already supports `./.codex`, `./.agents`, `./.omx`, and `./AGENTS.md`.
- Wrap `ouroboros` because its current CLI uses `~/.ouroboros` via `Path.home()`.

## Recommended Approach

Use a repo-local bootstrap script plus thin wrapper entrypoints:

- Install `oh-my-codex` into `./.tools/omx/` with npm.
- Run `omx setup --scope project` so Codex surfaces are generated under the repository.
- Install `ouroboros-ai==0.26.0b3` into `./.tools/ouroboros-venv/`.
- Run `ouroboros` through a wrapper that temporarily sets `HOME=$REPO/.local-home` so `~/.ouroboros` resolves inside the repo.
- Point `OUROBOROS_CLI_PATH` at the repo-local `bin/omx` wrapper so any orchestrator CLI handoff prefers the local Codex/OMX entrypoint.

## Files

- `scripts/setup-codex-local.sh`
  Bootstraps local installs and initializes project-scope config.
- `scripts/doctor-codex-local.sh`
  Runs repo-local health checks.
- `bin/omx`
  Repo-local OMX launcher.
- `bin/ooo`
  Repo-local Ouroboros launcher.
- `.gitignore`
  Ignores local tool caches and runtime state.

## Runtime Layout

- `./.tools/omx/`
  Local npm install root for `oh-my-codex`.
- `./.tools/ouroboros-venv/`
  Local Python environment for `ouroboros`.
- `./.local-home/.ouroboros/`
  Repo-local Ouroboros config, DB, and logs via wrapper-scoped `HOME`.
- `./.codex/`, `./.agents/`, `./.omx/`, `./AGENTS.md`
  OMX-generated project-scope Codex surfaces.

## Error Handling

- Bootstrap script should fail fast on missing prerequisites.
- Wrapper scripts should print a direct recovery command if local installs are missing.
- Setup should be idempotent: rerunning bootstrap refreshes local installs and re-applies project-scope OMX setup.

## Verification

- Confirm local binaries resolve from repo paths.
- Confirm `omx setup --scope project` generates repo-local Codex surfaces.
- Confirm `ouroboros config init` writes under `./.local-home/.ouroboros/`.
- Confirm doctor script exits successfully when local setup is healthy.
