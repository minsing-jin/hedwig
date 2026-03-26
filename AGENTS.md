# Codex Workflow Policy

This repository uses an issue-first, PR-first workflow for all Codex-driven work.

## Required flow

1. Confirm an open GitHub issue exists before making changes.
2. Work on a branch tied to that issue, not on `main`.
3. Open a pull request for every Codex-delivered change.
4. Link the PR to the issue with closing syntax such as `Closes #123`.

## Branching

- Preferred branch format: `issue/<number>-<short-slug>`
- Direct commits to `main` are not part of the normal Codex workflow.

## Session behavior

- If the user starts work without an issue number, stop and ask for one or propose creating one first.
- If the current branch is `main`, create or switch to an issue branch before editing unless the user explicitly authorizes an exception.
- Before completion, push the branch and prepare a PR summary tied to the issue.

## PR expectations

- Keep the PR scoped to one issue.
- Include verification steps and results.
- Note any follow-up work that should become a separate issue.
