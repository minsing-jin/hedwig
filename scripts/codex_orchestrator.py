"""
Codex Orchestrator — Claude Code manages, Codex implements + reviews.

Architecture:
  Claude Code (this conversation)
    │
    ├─ scripts/codex_orchestrator.py  ← runs in subprocess
    │    │
    │    ├─ codex exec [handoff packet]      # implementation Codex
    │    │       └─ writes code, runs tests, commits
    │    │
    │    └─ codex review --uncommitted        # fresh review Codex
    │            └─ independent code review
    │
    └─ verifies final results

Each AC goes through: implement → self-review → fresh review → verify.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

REPO = Path("/Users/jinminseong/Desktop/hedwig")
HANDOFF_DIR = REPO / ".handoff"
HANDOFF_DIR.mkdir(exist_ok=True)
RESULTS_DIR = HANDOFF_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def run_codex_exec(prompt: str, timeout: int = 1800, model: str | None = None) -> tuple[int, str, str]:
    """Run codex exec with given prompt. Returns (exit_code, stdout, stderr).

    Uses Popen + communicate to ensure the child process is killed on timeout.
    """
    cmd = ["codex", "exec"]
    if model:
        cmd += ["-m", model]
    cmd += ["--skip-git-repo-check", prompt]

    logger.info(f"Running codex exec (timeout={timeout}s)")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        logger.warning(f"Codex exec killed after {timeout}s timeout (PID {proc.pid})")
        return 124, "", f"Codex exec timed out after {timeout}s"


def run_codex_review(prompt: str, timeout: int = 600) -> tuple[int, str, str]:
    """Run codex review on uncommitted changes. Fresh instance.

    Uses Popen + communicate to ensure cleanup on timeout.
    """
    cmd = ["codex", "exec", "--skip-git-repo-check", prompt]
    logger.info(f"Running codex review (fresh instance via exec, timeout={timeout}s)")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        logger.warning(f"Codex review killed after {timeout}s timeout (PID {proc.pid})")
        return 124, "", f"Codex review timed out after {timeout}s"


def build_implementation_prompt(handoff_path: Path, ac_index: int, ac_text: str) -> str:
    """Build the prompt for the implementation Codex."""
    return f"""\
You are Codex receiving a handoff from Claude Code.

EXPLICIT AUTHORIZATION: This is an orchestrated Ralph loop run by Claude Code.
You are explicitly authorized to work directly on the `main` branch for this
task. You do NOT need to create a GitHub issue or branch. Ignore the
issue-first workflow in AGENTS.md for this orchestrator session — Claude
Code is the manager and has approved direct edits.

Read the handoff packet first to understand the project:
```
cat {handoff_path}
```

Your task right now: implement Acceptance Criterion #{ac_index}:

> {ac_text}

Steps:
1. Read the handoff packet to understand context
2. Glob/Read existing relevant files (especially in tests/ and hedwig/saas/)
3. Plan the minimal change needed
4. Write tests first if applicable
5. Implement the change
6. Run tests: .venv/bin/python -m pytest tests/ -v --tb=short
7. If tests pass, stage the changes (git add tests/<file>)
8. Self-review: re-read your diff with git diff --cached
9. If self-review passes, output a status block

DO NOT commit yet — orchestrator will commit after independent review passes.

Output format (must include this exact block at the end):
```
[AC {ac_index}] STATUS: pass|fail
Files changed: <list>
Tests run: <count> passed, <count> failed
Self-review notes: <observations>
```
"""


def build_review_prompt(ac_index: int, ac_text: str) -> str:
    """Build the prompt for the FRESH review Codex.

    This Codex has no memory of implementation — completely independent.
    """
    return f"""\
You are a fresh Codex instance performing INDEPENDENT code review.
You have NO memory of any previous implementation. Treat this as a code
review for a PR submitted by another developer.

EXPLICIT AUTHORIZATION: This is an orchestrated review run by Claude Code.
Ignore AGENTS.md issue-first workflow — this is a review-only operation,
no commits will be made by you. Claude Code will commit if you approve.

Context: This is the Hedwig v3.0 SaaS project. The previous developer
just implemented Acceptance Criterion #{ac_index}:

> {ac_text}

Your review job:
1. Read the staged diff:
   git diff --cached
2. Check for:
   - Correctness (does it actually meet the AC?)
   - Code quality (style, naming, structure)
   - Test coverage (are there tests for the change?)
   - Security issues
   - Edge cases not handled
   - Regressions in existing tests
3. Run tests:
   .venv/bin/python -m pytest tests/ -v --tb=short
4. Output a verdict

Output format (must include this exact block at the end):
```
[REVIEW AC {ac_index}] VERDICT: approve|request_changes|reject
Strengths: <list>
Issues: <list>
Required changes: <list, or "none">
Test status: <pass/fail/N tests run>
```

Be strict. If tests fail or the AC is not actually met, REJECT.
DO NOT make any code changes — review only.
"""


def parse_verdict(review_output: str) -> str:
    """Parse verdict from review Codex output. Looks for explicit VERDICT line first."""
    text = review_output.lower()
    # Explicit verdict block format: "VERDICT: approve"
    for line in text.split("\n"):
        if "verdict:" in line:
            if "approve" in line:
                return "approve"
            if "request_changes" in line or "request changes" in line:
                return "request_changes"
            if "reject" in line:
                return "reject"
    # Fallback substring
    if "verdict: approve" in text or "[review ac" in text and "approve" in text and "request" not in text and "reject" not in text:
        return "approve"
    if "request_changes" in text:
        return "request_changes"
    if "reject" in text:
        return "reject"
    return "unknown"


def execute_ac(ac_index: int, ac_text: str, handoff_path: Path, max_retries: int = 2) -> dict:
    """Execute a single AC: implement → review → commit. Retries on request_changes."""
    result_file = RESULTS_DIR / f"ac_{ac_index:03d}.json"
    started = time.time()

    record = {
        "ac_index": ac_index,
        "ac_text": ac_text,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "attempts": [],
    }

    review_feedback = ""

    for attempt in range(1, max_retries + 1):
        attempt_record = {"attempt": attempt}

        # Phase 1: Implementation (include feedback from previous review if any)
        impl_prompt = build_implementation_prompt(handoff_path, ac_index, ac_text)
        if review_feedback:
            impl_prompt += f"\n\n## Previous Review Feedback (FIX THESE)\n\n{review_feedback}\n"

        impl_code, impl_out, impl_err = run_codex_exec(impl_prompt, timeout=1200)
        attempt_record["impl_exit_code"] = impl_code
        attempt_record["impl_stdout_tail"] = impl_out[-1500:]

        if impl_code != 0:
            attempt_record["result"] = "impl_failed"
            record["attempts"].append(attempt_record)
            continue

        # Phase 2: Independent Review (fresh codex)
        review_prompt = build_review_prompt(ac_index, ac_text)
        review_code, review_out, review_err = run_codex_review(review_prompt, timeout=600)
        attempt_record["review_exit_code"] = review_code
        attempt_record["review_stdout_tail"] = review_out[-1500:]

        verdict = parse_verdict(review_out)
        attempt_record["verdict"] = verdict
        record["attempts"].append(attempt_record)

        if verdict == "approve":
            commit_msg = f"feat(ralph-codex): AC {ac_index} — {ac_text[:60]}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO, capture_output=True)
            record["status"] = "passed"
            record["final_verdict"] = "approve"
            break
        else:
            # Reset staged, capture feedback for next attempt
            subprocess.run(["git", "reset", "HEAD"], cwd=REPO, capture_output=True)
            review_feedback = review_out[-2000:]
            if attempt == max_retries:
                record["status"] = "max_retries_exceeded"
                record["final_verdict"] = verdict

    record["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    record["duration_sec"] = round(time.time() - started, 1)
    result_file.write_text(json.dumps(record, indent=2))
    logger.info(
        f"AC {ac_index} → {record.get('status', 'unknown')} "
        f"(verdict: {record.get('final_verdict', 'unknown')}, "
        f"attempts: {len(record['attempts'])})"
    )
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="seed.ralph.yaml", help="Path to seed file")
    parser.add_argument("--max-ac", type=int, default=None, help="Max number of ACs to process")
    parser.add_argument("--start-from", type=int, default=1, help="Start from AC number")
    args = parser.parse_args()

    import yaml
    seed_path = REPO / args.seed
    seed = yaml.safe_load(seed_path.read_text())
    acs = seed.get("acceptance_criteria", [])

    logger.info(f"Loaded {len(acs)} acceptance criteria from {seed_path}")

    # Build handoff packet
    sys.path.insert(0, str(REPO / "scripts"))
    from handoff_packet import build_handoff_packet
    handoff_path = build_handoff_packet(seed_path)

    end_at = (args.start_from - 1) + (args.max_ac or len(acs))
    target_acs = list(enumerate(acs, 1))[args.start_from - 1: end_at]

    logger.info(f"Executing ACs {args.start_from}..{end_at}")

    summary = {"total": len(target_acs), "passed": 0, "failed": 0, "results": []}

    for ac_index, ac_text in target_acs:
        record = execute_ac(ac_index, ac_text, handoff_path)
        summary["results"].append({
            "ac": ac_index,
            "status": record.get("status"),
            "verdict": record.get("verdict"),
            "duration": record.get("duration_sec"),
        })
        if record.get("status") == "passed":
            summary["passed"] += 1
        else:
            summary["failed"] += 1

    summary_path = RESULTS_DIR / f"summary_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    logger.info(f"\n=== Orchestrator Complete ===")
    logger.info(f"Passed: {summary['passed']}/{summary['total']}")
    logger.info(f"Failed: {summary['failed']}/{summary['total']}")
    logger.info(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
