from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "issue27-ouroboros-completion.md"


def test_issue27_evidence_documents_strict_ouroboros_gap_and_scope():
    doc = DOC.read_text(encoding="utf-8")

    assert "Issue #27 closes the process gap" in doc
    assert "lin_hedwig_issue7_feed_moat_resume_20260514" in doc
    assert "Gen 9 -- Score: 0.25 | REJECTED" in doc
    assert "Per-AC dashboard data: unavailable" in doc
    assert "Issue #1 autoresearch capture work." in doc
    assert "Issue #2 generic recommender-core generalization work." in doc
    assert "Manus API integration." in doc
    assert "LiteLLM adoption." in doc


def test_issue27_evidence_records_all_resume_jobs_and_terminal_blocker():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    for job_id in (
        "job_c89c8b04644d",
        "job_f49542a0d625",
        "job_ddcc46a29746",
    ):
        assert job_id in doc

    assert "cursor stayed unchanged" in doc.lower()
    assert "terminal_blocked" in doc
    assert "claiming PASS or convergence would be incorrect" in normalized_doc
    assert "parallel=false" in doc


def test_issue27_evidence_keeps_product_behavior_unchanged():
    doc = DOC.read_text(encoding="utf-8")

    assert "evaluator-visible evidence artifact only" in doc
    assert "No worktree implementation changes were produced" in doc
    assert "Any product behavior change beyond documenting the completion state." in doc
    assert "723 passed, 1 warning" in doc


def test_issue27_evidence_records_current_origin_main_artifact_evaluation():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Current Artifact Evaluation" in doc
    assert "cd1c7f10444bb16483da3d409f963d71355fcac9" in doc
    for pr_ref in ("PR #18", "PR #5", "PR #21", "PR #22", "PR #23", "PR #24", "PR #26", "PR #28"):
        assert pr_ref in doc
    assert "not as ancestors of the current `origin/main` head" in normalized_doc
    assert "No module named pytest" in doc
    assert "runtime smoke: route_items_after_ranking preserved item order" in doc
    assert "no new product implementation gap found" in normalized_doc


def test_issue27_evidence_extracts_latest_interview_requirements():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Latest Interview-Derived Requirements" in doc
    assert "docs/interviews/2026-04-08-socratic-interview-v2.md" in doc
    assert "seed.yaml` v2.0" in doc
    assert "control belongs to the individual" in normalized_doc
    assert "algorithm sovereignty through direct policy edits" in doc
    assert "Socratic onboarding must crystallize criteria" in doc
    assert "Feedback is boolean upvote/downvote plus optional natural-language direction" in doc
    assert "must not ask unprompted questions" in doc
    assert "Daily and weekly evolution may tune criteria" in doc
    assert "Alert, Daily Brief, Weekly Brief" in doc
    assert "source layer remains plugin-based and user-extensible" in doc
    assert "post-ranking: feed, exploration, media, delivery" in doc
    assert "preserve the accepted ranking outputs and ranking identity" in normalized_doc
    assert "Requirements explicitly not extracted into this issue #27 closure pass" in doc
    assert "Old issue #1 autoresearch implementation work" in normalized_doc
    assert "Old issue #2 generic recommender-core generalization work" in normalized_doc


def test_issue27_evidence_reviews_each_extracted_requirement_status():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Requirement Satisfaction Review" in doc
    assert "Sub-AC 3.1.2 reviewed the current artifact against each extracted requirement" in doc
    assert "Individual-owned self-improving recommendation moat" in doc
    assert "Algorithm sovereignty through direct policy edits" in doc
    assert "Socratic onboarding crystallizes criteria" in doc
    assert "Feedback is boolean upvote/downvote plus optional natural-language direction" in doc
    assert "Daily and weekly evolution may tune criteria" in doc
    assert "Delivery/feed surfaces include Alert, Daily Brief, Weekly Brief" in doc
    assert "Source layer remains plugin-based and user-extensible" in doc
    assert "Artifact boundary is post-ranking" in doc
    assert normalized_doc.count("Satisfied in current artifact") >= 8
    assert "excluded old-scope work remains excluded" in normalized_doc
    assert "no new product implementation gap was found" in normalized_doc
    assert "strict Ouroboros process blocker" in normalized_doc


def test_issue27_evidence_records_requirement_by_requirement_comparison():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Requirement-by-Requirement Comparison" in doc
    assert "Sub-AC 3.1.3 records the extracted requirement set" in doc
    assert "| Requirement | Status | Brief evidence |" in doc
    assert "limited to the latest feed-moat and personal algorithm steering scope" in normalized_doc
    assert "does not treat old issue #1, old issue #2, Manus, LiteLLM" in normalized_doc

    comparison_requirements = (
        "Individual-owned self-improving recommendation moat",
        "Algorithm sovereignty through direct policy edits",
        "Socratic onboarding crystallizes criteria, urgency, source priority, and context",
        "Boolean feedback with optional natural-language direction",
        "Daily/weekly evolution may tune criteria, source reliability, interpretation style, and exploration",
        "Alert, Daily Brief, Weekly Brief, and ambient/feed surfaces",
        "Source layer remains plugin-based and user-extensible",
        "Post-ranking artifact boundary preserves accepted ranking outputs and ranking identity",
        "Strict Ouroboros closure state for the existing Hedwig lineage",
    )
    for requirement in comparison_requirements:
        assert requirement in doc

    assert normalized_doc.count("| Satisfied |") >= 8
    assert "Unsatisfied - operational blocker" in doc
    assert "next safe action is an isolated serial evolve step" in normalized_doc


def test_issue27_evidence_extracts_seed_goal_and_constraint_checklist():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Seed Goal and Constraint Checklist" in doc
    assert "Sub-AC 3.2.1 extracts the execution seed goal and explicit constraints" in doc
    assert "| Seed item | Checklist comparison |" in doc
    assert "Complete the latest Hedwig feed-moat and personal algorithm steering Ouroboros closure pass" in doc
    assert "already-merged implementation baseline" in doc
    assert "Do not expand beyond the latest interview and seed-derived work" in doc
    assert "Work only in Hedwig project scope" in doc
    assert "Do not implement old issue #1 autoresearch work" in doc
    assert "Do not implement old issue #2 generic recommender-core generalization" in doc
    assert "Do not add or restore Manus integration" in doc
    assert "Do not adopt LiteLLM" in doc
    assert "Preserve the existing merged feed-moat implementation and ranking boundaries" in doc
    assert "Run serially with low resource usage" in doc
    assert "no product behavior changes are part of this pass" in normalized_doc
    assert "next safe resume step is a single serial evolve step" in normalized_doc


def test_issue27_evidence_reviews_each_seed_goal_and_constraint():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Seed Goal and Constraint Artifact Review" in doc
    assert "Sub-AC 3.2.2 reviews the current repository artifact" in doc
    assert "| Seed goal element or constraint | Review status | Artifact evidence |" in doc

    reviewed_seed_items = (
        "Complete the latest Hedwig feed-moat and personal algorithm steering Ouroboros closure pass",
        "Use the already-merged implementation baseline",
        "Do not expand beyond the latest interview and seed-derived work",
        "Work only in Hedwig project scope",
        "Do not implement old issue #1 autoresearch work",
        "Do not implement old issue #2 generic recommender-core generalization",
        "Do not add or restore Manus integration",
        "Do not adopt LiteLLM",
        "Preserve the existing merged feed-moat implementation and ranking boundaries",
        "Run serially with low resource usage",
    )
    for seed_item in reviewed_seed_items:
        assert seed_item in doc

    assert normalized_doc.count("| Satisfied |") >= 8
    assert "Blocked only by strict Ouroboros runtime state" in doc
    assert "Satisfied for this closure attempt; runtime remains blocked" in doc
    assert "Repository search finds Manus only in exclusion/evidence text" in doc
    assert "repository search finds LiteLLM only in exclusion/evidence text" in doc
    assert "not as an adopted dependency or routing layer" in normalized_doc
    assert "requires completed ranking outputs before delivery routing" in doc
    assert "does not start parallel workloads" in doc
    assert "all product-scope seed goal elements and constraints are satisfied" in normalized_doc
    assert "strict Ouroboros runtime blocker" in normalized_doc


def test_issue27_evidence_documents_gap_mismatches_and_unsupported_assumptions():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Goal-Alignment Gap Ledger" in doc
    assert "Sub-AC 3.2.3 documents the concrete gaps" in doc
    assert "| Finding type | Status | Evidence and next action |" in doc
    assert "Goal-alignment gap: strict Ouroboros closure state" in doc
    assert "Open operational gap" in doc
    assert "lineage `lin_hedwig_issue7_feed_moat_resume_20260514` remains `active`/rejected" in doc
    assert "retry one isolated `parallel=false` evolve step" in doc
    assert "Goal-alignment gap: product implementation completeness" in doc
    assert "No gap found" in doc
    assert "No feed-moat, delivery, feedback, onboarding, or ranking-boundary implementation change is required" in doc
    assert "Constraint mismatch: old issue #1 autoresearch scope" in doc
    assert "Constraint mismatch: old issue #2 recommender-core generalization scope" in doc
    assert "Constraint mismatch: Manus or LiteLLM adoption" in doc
    assert "Constraint mismatch: ranking boundary preservation" in doc
    assert normalized_doc.count("None found") >= 4
    assert "Unsupported assumption: process PASS/convergence can be inferred from merged code" in doc
    assert "Unsupported and rejected" in doc
    assert "This document records `terminal_blocked` instead of claiming completion" in doc
    assert "Unsupported assumption: further retries should broaden scope" in doc
    assert "would violate the seed constraints" in normalized_doc
    assert "the only remaining goal-alignment gap is operational Ouroboros closure" in normalized_doc
    assert "No constraint mismatch or unsupported product assumption justifies code changes" in normalized_doc


def test_issue27_evidence_summarizes_remaining_gaps_after_comparisons():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Remaining Gaps Summary" in doc
    assert "Sub-AC 3.3 summarizes the closure decision after both comparisons" in doc
    assert "Latest interview requirements versus current artifact: pass for product scope" in normalized_doc
    assert "no feed-moat or personal algorithm steering implementation gap remains" in normalized_doc
    assert "Seed goal and explicit constraints versus current artifact: pass" in normalized_doc
    assert "no old issue #1, old issue #2, Manus, LiteLLM" in normalized_doc
    assert "ranking-boundary mismatch remains" in normalized_doc
    assert "Remaining gap: strict Ouroboros process closure" in doc
    assert "serial Ralph/evolve attempts did not advance the lineage after OOM recovery" in normalized_doc
    assert "no product gaps remain after the requirement and seed-constraint comparisons" in normalized_doc
    assert "only remaining gap is operational `terminal_blocked` state" in normalized_doc
    assert "retry one isolated serial `parallel=false` evolve step" in doc
    assert "record the job ID, lineage status, AC dashboard, and repository verification result" in normalized_doc


def test_issue27_evidence_verifies_scope_limited_changes():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Issue 27 Scope-Limited Change Verification" in doc
    assert "Sub-AC 4.1 verifies that this closure pass remains limited to issue #27 scope" in doc
    assert "docs/issue27-ouroboros-completion.md" in doc
    assert "tests/test_issue27_ouroboros_completion.py" in doc
    assert "No `hedwig/`, `migrations/`, `scripts/`, runtime configuration" in doc
    assert "source adapter, ranking, feed, delivery, onboarding, or feedback implementation files" in normalized_doc
    assert "modified in this pass" in doc
    assert "do not add product behavior" in normalized_doc
    assert "reopen old issue #1 autoresearch work" in normalized_doc
    assert "reopen old issue #2 generic recommender-core generalization" in normalized_doc
    assert "restore Manus integration" in doc
    assert "adopt LiteLLM" in doc
    assert "change ranking boundaries" in normalized_doc
    assert "required changes are limited to issue #27 closure evidence" in normalized_doc
    assert "No out-of-scope implementation change is required or present" in normalized_doc


def test_issue27_evidence_documents_closure_pass_verification_steps():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Closure Pass Verification Steps" in doc
    assert "Sub-AC 4.2.1 documents the verification steps used for this closure pass" in doc
    assert "already-merged feed-moat and personal algorithm steering baseline" in doc
    assert "git status --short --branch" in doc
    assert "only issue #27 evidence files are modified" in doc
    assert "docs/issue27-ouroboros-completion.md" in doc
    assert "tests/test_issue27_ouroboros_completion.py" in doc
    assert "excludes old issue #1, old issue #2, Manus, and LiteLLM" in doc
    assert "preserves the existing ranking boundaries" in normalized_doc
    assert "python3 -m pytest -q tests/test_issue27_ouroboros_completion.py" in doc
    assert "No module named pytest" in doc
    assert "Run each function in `tests/test_issue27_ouroboros_completion.py` directly" in doc
    assert "low-resource fallback" in doc
    assert "git diff --check" in doc
    assert "direct invocation of all issue #27 guard-test functions passes" in normalized_doc
    assert "pytest command remains explicitly recorded as unavailable" in normalized_doc


def test_issue27_evidence_documents_verification_results_and_outcomes():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Verification Results and Outcomes" in doc
    assert "Sub-AC 4.2.2 records the verification outcomes from this closure pass" in doc
    assert "repository-local, low-resource checks" in doc
    assert "do not alter Hedwig product behavior" in doc
    assert "| Check | Outcome | Evidence |" in doc
    assert "Worktree scope check" in doc
    assert "branch `ooo/orch_9f3397eece9b`" in doc
    assert "only `docs/issue27-ouroboros-completion.md` and `tests/test_issue27_ouroboros_completion.py` modified" in doc
    assert "Pytest guard-test command" in doc
    assert "Blocked by missing runner" in doc
    assert "No module named pytest" in doc
    assert "Direct guard-test fallback" in doc
    assert "Every `test_issue27_*` function" in doc
    assert "Diff hygiene" in doc
    assert "git diff --check" in doc
    assert "Product regression state" in doc
    assert "723 passed, 1 warning" in doc
    assert "Closure outcome" in doc
    assert "Terminal blocked, not product-failed" in doc
    assert "Product-scope feed-moat requirements and seed constraints are satisfied" in doc
    assert "Outcome decision for Sub-AC 4.2.2" in doc
    assert "repository verification for the evidence update passed" in normalized_doc
    assert "direct guard-test fallback and diff hygiene check" in normalized_doc
    assert "The process result remains `terminal_blocked`, not PASS or convergence" in doc
    assert "isolated `parallel=false` evolve step" in doc


def test_issue27_evidence_includes_pr_ready_issue_linkage():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "PR-Ready Issue 27 Linkage" in doc
    assert "Sub-AC 4.2.3 records the issue linkage" in doc
    assert "pull request evidence for this closure pass" in normalized_doc
    assert "scoped to issue #27 only" in doc
    assert "Closes #27" in doc
    assert "PR-ready summary" in doc
    assert "latest Hedwig feed-moat and personal algorithm steering Ouroboros pass" in normalized_doc
    assert "current `origin/main` artifact evaluation through PR #28" in doc
    assert "no product implementation gap remains for issue #27" in doc
    assert "Preserves the already-merged feed-moat implementation and ranking boundaries" in doc
    assert "no `hedwig/`, migration, source adapter, delivery, feedback, onboarding" in normalized_doc
    assert "old issue #1 autoresearch work" in doc
    assert "old issue #2 generic recommender-core generalization" in doc
    assert "Manus integration" in doc
    assert "LiteLLM adoption" in doc
    assert "honest terminal state as `terminal_blocked`" in doc
    assert "strict Ouroboros lineage closure still requires one isolated serial" in normalized_doc
    assert "PR-ready verification" in doc
    assert "No module named pytest" in doc
    assert "Direct `python3` invocation of every `test_issue27_*` guard-test function passed" in normalized_doc
    assert "`git diff --check` passed" in doc
    assert "723 passed, 1 warning" in doc
    assert "PR-ready follow-up note" in doc
    assert "remaining action is not product implementation" in normalized_doc
    assert "append the resulting job ID, lineage status, AC dashboard, and repository verification result" in normalized_doc


def test_issue27_evidence_records_targeted_feed_moat_verification_results():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Targeted Feed-Moat Verification Results" in doc
    assert "Sub-AC 5.1 runs and records targeted verification" in doc
    assert "repository-local" in doc
    assert "do not modify product code or expand beyond issue #27" in doc
    assert "python3 -m pytest -q tests/test_issue27_ouroboros_completion.py" in doc
    assert "python3 -m pytest -q tests/test_personal_algorithm_engine.py" in doc
    assert "No module named pytest" in doc
    assert "Direct issue #27 guard-test fallback" in doc
    assert "passed all current `test_issue27_*` functions" in doc
    assert "Direct feed-moat runtime smoke" in doc
    assert "hedwig.personal_algorithm.route_items_after_ranking" in doc
    assert "preserved item order" in doc
    assert "ensemble_score" in doc
    assert "final_score" in doc
    assert "rank identity" in doc
    assert "post-ranking delivery boundaries" in doc
    assert "git diff --check" in doc
    assert "Targeted verification decision for Sub-AC 5.1" in doc
    assert "runnable low-resource checks passed" in normalized_doc
    assert "blocked only by missing local test dependencies" in normalized_doc
    assert "No feed-moat or personal algorithm steering regression was found" in normalized_doc
    assert "terminal_blocked" in doc
    assert "parallel=false" in doc


def test_issue27_evidence_records_test_suite_outcome_constraints():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Test Suite Outcome Record" in doc
    assert "Sub-AC 5.2.2 records the test suite outcome" in doc
    assert "including the pass/fail result and the execution constraint" in normalized_doc
    assert "| Suite or check | Outcome | Evidence |" in doc
    assert "Full repository pytest suite" in doc
    assert "Blocked before collection" in doc
    assert "`python3 -m pytest -q` exits with `No module named pytest`" in doc
    assert "no tests are collected or executed in this environment" in doc
    assert "Issue #27 pytest guard suite" in doc
    assert "python3 -m pytest -q tests/test_issue27_ouroboros_completion.py" in doc
    assert "no pytest-managed pass/fail result is available here" in doc
    assert "Issue #27 direct guard fallback" in doc
    assert "completed all current `test_issue27_*` functions successfully" in doc
    assert "Diff hygiene" in doc
    assert "git diff --check" in doc
    assert "Historical clean baseline suite" in doc
    assert "723 passed, 1 warning in 22.92s" in doc
    assert "not claimed as a fresh Sub-AC 5.2.2 run" in doc
    assert "fresh full-suite pytest result cannot be produced" in normalized_doc
    assert "pytest runner is unavailable" in doc
    assert "repository-local fallback checks" in doc
    assert "missing local test dependencies rather than a feed-moat" in normalized_doc


def test_issue27_evidence_records_failing_test_commands_and_errors():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Failing Test Command Ledger" in doc
    assert "Sub-AC 5.3.1 collects the failing or blocked test targets" in doc
    assert "| Test target or name | Command run | Outcome | Relevant error output |" in doc
    assert "Full repository pytest suite" in doc
    assert "`python3 -m pytest -q`" in doc
    assert "Issue #27 evidence pytest suite" in doc
    assert "`python3 -m pytest -q tests/test_issue27_ouroboros_completion.py`" in doc
    assert "Feed-moat personal algorithm pytest suite" in doc
    assert "`python3 -m pytest -q tests/test_personal_algorithm_engine.py`" in doc
    assert normalized_doc.count("Failed before collection; exit code 1") >= 3
    assert normalized_doc.count("No module named pytest") >= 3
    assert "no individual pytest test function names are available from the runner" in normalized_doc
    assert "Blocked test names/targets recorded for Sub-AC 5.3.1" in doc
    assert "tests/test_issue27_ouroboros_completion.py" in doc
    assert "tests/test_personal_algorithm_engine.py" in doc
    assert "full repository pytest suite represented by `python3 -m pytest -q`" in normalized_doc
    assert "does not indicate a feed-moat product regression" in normalized_doc
    assert "does not justify expanding beyond issue #27" in normalized_doc


def test_issue27_evidence_compares_failures_to_regression_candidates():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Regression Candidate Comparison" in doc
    assert "Sub-AC 5.3.2 compares the blocked verification failures" in doc
    assert "against the current implementation changes" in normalized_doc
    assert "already-merged feed-moat implementation boundary" in normalized_doc
    assert "does not treat old issue #1, old issue #2, Manus, LiteLLM" in normalized_doc
    assert "| Observed failure or risk | Current implementation comparison | Likely regression candidate |" in doc
    assert "`python3 -m pytest -q` fails before collection with `No module named pytest`" in doc
    assert "current diff changes only issue #27 evidence files" in doc
    assert "Local test-runner dependency is missing" in doc
    assert "`python3 -m pytest -q tests/test_issue27_ouroboros_completion.py`" in doc
    assert "direct Python fallback executes the same guard-test functions successfully" in doc
    assert "evidence text drifting from guard-test expectations" in doc
    assert "`python3 -m pytest -q tests/test_personal_algorithm_engine.py`" in doc
    assert "No `hedwig/` product implementation file is modified in this pass" in doc
    assert "route_items_after_ranking" in doc
    assert "preserves order, `ensemble_score`, `final_score`, and rank identity" in doc
    assert "feed-moat regression is not supported by current evidence" in doc
    assert "Strict Ouroboros lineage remains `terminal_blocked`" in doc
    assert "Operational Ouroboros runtime closure gap" in doc
    assert "retry one isolated serial `parallel=false` evolve step" in doc
    assert "Regression-candidate decision for Sub-AC 5.3.2" in doc
    assert "likely regression candidate is the local verification environment" in normalized_doc
    assert "secondary candidate is future evidence-document drift" in normalized_doc
    assert "No current failure maps to the merged feed-moat implementation" in normalized_doc
    assert "ranking-boundary preservation" in doc
    assert "issue #1/#2 scope" in doc


def test_issue27_evidence_classifies_failures_as_environment_related():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Pre-existing or Environment-Related Failure Evidence" in doc
    assert "Sub-AC 5.3.3 checks whether the blocked verification results" in doc
    assert "pre-existing or environment-related rather than new regressions" in normalized_doc
    assert "| Evidence check | Observed result | Failure classification |" in doc
    assert "Full pytest command" in doc
    assert "`python3 -m pytest -q` exits before collection" in doc
    assert "/Users/jinminseong/.local/share/uv/tools/ouroboros-ai/bin/python3: No module named pytest" in doc
    assert "Targeted issue #27 pytest command" in doc
    assert "same `No module named pytest` error" in doc
    assert "direct Python fallback passes all current guard-test functions" in doc
    assert "Targeted feed-moat pytest command" in doc
    assert "no feed-moat assertions or Hedwig product modules are reached by pytest" in doc
    assert "Local virtual environment check" in doc
    assert "`.venv` is absent in this worktree" in doc
    assert "Project test configuration" in doc
    assert "`pyproject.toml` contains `[tool.pytest.ini_options]`" in doc
    assert "active runner lacks the dependency" in doc
    assert "Baseline regression evidence" in doc
    assert "723 passed, 1 warning in 22.92s" in doc
    assert "Baseline instability is not supported by current evidence" in doc
    assert "Current worktree scope" in doc
    assert "only the issue #27 evidence doc and guard test modified" in doc
    assert "Runnable fallback checks" in doc
    assert "Direct invocation of every `test_issue27_*` guard-test function passed" in doc
    assert "`git diff --check` passed" in doc
    assert "Environment-related failure decision for Sub-AC 5.3.3" in doc
    assert "local test-runner dependency/configuration gap" in normalized_doc
    assert "not a new feed-moat or personal algorithm steering regression" in normalized_doc
    assert "missing `pytest` module and absent `.venv` are observed before test collection" in normalized_doc
    assert "restore the baseline test environment" in normalized_doc
    assert "does not require expanding issue #27 scope" in normalized_doc
    assert "changing ranking boundaries" in doc
    assert "adopting LiteLLM" in normalized_doc
    assert "restoring Manus" in normalized_doc
    assert "reopening old issue #1/#2 work" in normalized_doc


def test_issue27_evidence_documents_failure_classification_rationale_and_followup():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Failure Classification and Follow-Up Rationale" in doc
    assert "Sub-AC 5.3.4 documents the classification and rationale" in doc
    assert "recommended follow-up" in doc
    assert "does not turn local tooling gaps into feed-moat product work" in normalized_doc
    assert "| Failure | Classification | Rationale | Recommended follow-up |" in doc

    assert "Full repository pytest suite: `python3 -m pytest -q`" in doc
    assert "Environment/setup blocker" in doc
    assert "no repository tests, Hedwig modules, or feed-moat assertions run" in normalized_doc
    assert "Restore the baseline Python test environment" in doc
    assert "record the fresh full-suite result" in doc

    assert "Issue #27 evidence pytest suite" in doc
    assert "Environment/setup blocker with passing fallback" in doc
    assert "direct `python3` invocation of every current `test_issue27_*` function passes" in doc
    assert "runner availability rather than evidence-document assertion failure" in normalized_doc
    assert "update only the issue #27 evidence text or guard expectations that drifted" in doc

    assert "Feed-moat personal algorithm pytest suite" in doc
    assert "not product regression evidence" in doc
    assert "fails before importing the feed-moat test module" in doc
    assert "preserved order, `ensemble_score`, `final_score`, rank identity" in doc
    assert "Investigate product code only if pytest reaches the assertions" in doc

    assert "Strict Ouroboros lineage closure remains `terminal_blocked`" in doc
    assert "Operational process blocker" in doc
    assert "serial Ralph/evolve attempts did not advance lineage" in doc
    assert "run one isolated serial `parallel=false` evolve step" in doc
    assert "append the job ID, lineage status, AC dashboard, and repository verification result" in doc

    assert "Failure-classification decision for Sub-AC 5.3.4" in doc
    assert "local environment/setup blocker or an operational Ouroboros process blocker" in normalized_doc
    assert "None is classified as a current feed-moat" in doc
    assert "personal algorithm steering, ranking-boundary" in normalized_doc
    assert "Manus/LiteLLM" in doc
    assert "old issue #1/#2 regression" in normalized_doc
    assert "restoring the test environment and retrying the existing serial lineage closure path" in normalized_doc


def test_issue27_evidence_records_latest_local_verification_after_import():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Local Verification After Run Artifact Import" in doc
    assert "/private/tmp/hedwig-issue27-ouroboros-run2" in doc
    assert "python3 -m pytest -q tests/test_issue27_ouroboros_completion.py" in doc
    assert "23 passed in 0.13s" in doc
    assert "tests/test_personal_algorithm_engine.py tests/test_ambient_delivery_surfaces.py" in doc
    assert "174 passed in 10.85s" in doc
    assert ".venv/bin/python -m pytest -q" in doc
    assert "746 passed, 1 warning in 22.35s" in doc
    assert "test_run_weekly_sends_email_briefing_when_smtp_is_standalone" in doc
    assert "passes issue #27 guard tests, targeted feed-moat evidence tests" in normalized_doc
    assert "full repository suite" in doc
    assert "limited to strict Ouroboros lineage closure state" in normalized_doc


def test_issue27_evidence_records_run_and_qa_pass():
    doc = DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert "Ouroboros Run And QA Result" in doc
    assert "job_ab816fb4bb95" in doc
    assert "orch_9f3397eece9b" in doc
    assert "exec_3bcfde466626" in doc
    assert "seed_cb5df84a60b5" in doc
    assert "Status: `completed`" in doc
    assert "AC `5/5`, Sub-AC `23/23`" in doc
    assert "Session: qa-ba23fbfb" in doc
    assert "Score: 0.95 / 1.00 [PASS]" in doc
    assert "Verdict: pass" in doc
    assert "Threshold: 0.90" in doc
    assert "QA loop action: `done`" in doc
    assert "meet the narrowed completion seed" in normalized_doc
    assert "does not rewrite history for the original lineage" in normalized_doc
    assert "lin_hedwig_issue7_feed_moat_resume_20260514" in doc
