---
name: claude-limit-auto-resume
description: Use when enabling, disabling, checking, or troubleshooting this project's optional Claude Code usage-limit auto-resume workflow.
argument-hint: <enable|disable|status|doctor>
disable-model-invocation: true
allowed-tools: Bash, Read
---

This skill is project-scoped. It only manages Hedwig's local Claude Code auto-resume workflow.

When invoked:

1. Parse `$ARGUMENTS` as one of `enable`, `disable`, `status`, or `doctor`.
2. Run `./scripts/claude-auto-resume <command>`.
3. Summarize the result briefly.
4. If the command is `enable`, remind the user that only future Claude sessions started through the wrapper are supervised:

```bash
./scripts/claude-auto-resume wrap -- claude
```

Operational rules:

- Do not edit `~/.claude` global files for this workflow.
- Keep all runtime state under `.claude/auto-resume/` in this project.
- If asked to inspect current health, prefer `status` first and `doctor` second.
- If the user wants to stop the workflow, run `disable`.
- Mention that managed sessions may still lose some native Claude context after a usage limit, so the wrapper also writes a local handoff file.
