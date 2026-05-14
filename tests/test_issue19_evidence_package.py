from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DOC = ROOT / "docs" / "issue19-evidence-package.md"
EVIDENCE_ENTRYPOINT = ROOT / "scripts" / "verify_issue19_evidence.sh"

ACCEPTED_CHECKPOINT_SHORT_SHA = "471e9e6"
ACCEPTED_CHECKPOINT_FULL_SHA = "471e9e654e73097dcf620b1c1e4f0f0b26156051"

ISSUE_7_CRITERIA = [
    "Raw events and derived rewards are stored separately.",
    "Existing feedback and `behavior_events` paths continue to work.",
    "Grid overview is the default feed mode, Detail Swipe opens from cards, Dense Reader remains available.",
    "Impressions, viewed cards/session, dwell, saves, opens, skips, swipes, and feed mode are instrumented.",
    "Left swipe defaults to save/later; right/next defaults to weak skip/near-neutral; explicit not-interested is strong negative.",
    "Risky natural-language changes shadow-test before applying.",
    "`algorithm.yaml`/policy changes have versioned rollback.",
    "Exploration/anomaly exposure defaults around 10% within 5-15% and is subtly labeled.",
    "Delivery policy chooses surface/channel/timing/repeat after ranking.",
]

REFERENCED_FILES = [
    "algorithm.yaml",
    "hedwig/dashboard/app.py",
    "hedwig/dashboard/templates/feed.html",
    "hedwig/onboarding/nl_algo_editor.py",
    "hedwig/personal_algorithm.py",
    "hedwig/storage/local.py",
    "hedwig/storage/supabase.py",
    "migrations/002_personal_algorithm_engine.sql",
    "tests/test_personal_algorithm_engine.py",
]

ACCEPTED_CHECKPOINT_FILES = [
    "algorithm.yaml",
    "hedwig/dashboard/app.py",
    "hedwig/dashboard/templates/feed.html",
    "hedwig/onboarding/nl_algo_editor.py",
    "hedwig/personal_algorithm.py",
    "hedwig/storage/local.py",
    "hedwig/storage/supabase.py",
    "migrations/002_personal_algorithm_engine.sql",
    "sovereignty.yaml",
    "tests/test_personal_algorithm_engine.py",
]

REFERENCED_TESTS = [
    "test_raw_events_and_rewards_are_separate",
    "test_swipe_defaults_and_policy_parser",
    "test_feed_modes_exploration_delivery_and_metrics",
    "test_shadow_fitness_media_and_rollback",
]

PY_COMPILE_COMMAND = (
    "python -m py_compile hedwig/personal_algorithm.py hedwig/dashboard/app.py "
    "hedwig/onboarding/nl_algo_editor.py hedwig/storage/local.py "
    "hedwig/storage/supabase.py tests/test_personal_algorithm_engine.py "
    "tests/test_issue19_evidence_package.py"
)

PERSONAL_ALGORITHM_TEST_COMMAND = "pytest tests/test_personal_algorithm_engine.py -q"
PERSONAL_ALGORITHM_CLEAN_TEST_COMMAND = (
    "pytest -p no:rerunfailures tests/test_personal_algorithm_engine.py -q"
)
FULL_PYTEST_COMMAND = "pytest tests/ -q"
GIT_DIFF_CHECK_COMMAND = "git diff --check"

REPO_PATH_ROOTS = {
    "algorithm.yaml",
    "docs",
    "hedwig",
    "migrations",
    "sovereignty.yaml",
    "tests",
}

REPO_PATH_PATTERN = re.compile(r"`([^`\n]+)`")
ISSUE_7_MAPPING_HEADING = "## Issue #7 Acceptance-Criteria Mapping"
NEXT_HEADING_PATTERN = re.compile(r"\n## ")


def _authoritative_issue7_acceptance_criteria() -> set[str]:
    """Return the issue #7 AC source used to validate evidence references."""
    return {
        _normalize_acceptance_criterion_reference(criterion)
        for criterion in ISSUE_7_CRITERIA
    }


def _normalize_acceptance_criterion_reference(reference: str) -> str:
    reference = re.sub(r"\s+", " ", reference.strip())
    return reference.rstrip()


def _extract_issue7_acceptance_criterion_references(markdown: str) -> set[str]:
    section_start = markdown.index(ISSUE_7_MAPPING_HEADING)
    section = markdown[section_start + len(ISSUE_7_MAPPING_HEADING):]
    next_heading = NEXT_HEADING_PATTERN.search(section)
    if next_heading:
        section = section[:next_heading.start()]

    references: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if not columns:
            continue
        criterion = columns[0]
        if criterion in {"Issue #7 criterion", "---"}:
            continue
        references.add(_normalize_acceptance_criterion_reference(criterion))

    return references


def _validate_acceptance_criterion_references(
    parsed_references: set[str],
    authoritative_references: set[str],
) -> dict[str, list[str]]:
    return {
        "missing": sorted(authoritative_references - parsed_references),
        "nonexistent": sorted(parsed_references - authoritative_references),
    }


def _extract_referenced_repository_files(markdown: str) -> set[str]:
    referenced_files: set[str] = set()

    for inline_reference in REPO_PATH_PATTERN.findall(markdown):
        candidates = re.split(r"[;,]|\s+and\s+|\s+or\s+", inline_reference)
        for candidate in candidates:
            path = candidate.strip().strip(".,:;()[]")
            if "::" in path:
                path = path.split("::", 1)[0]
            if not path or path.startswith("/"):
                continue
            if path.split("/", 1)[0] in REPO_PATH_ROOTS:
                referenced_files.add(path)

    return referenced_files


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def _accepted_checkpoint_tree_files() -> set[str]:
    return set(
        _git("ls-tree", "-r", "--name-only", ACCEPTED_CHECKPOINT_SHORT_SHA).splitlines()
    )


def _accepted_checkpoint_test_functions(test_path: str) -> set[str]:
    source = _git("show", f"{ACCEPTED_CHECKPOINT_SHORT_SHA}:{test_path}")
    return set(re.findall(r"^def (test_[A-Za-z0-9_]+)\(", source, re.MULTILINE))


def test_issue19_evidence_maps_each_issue7_criterion_to_verification():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "Accepted checkpoint: Ouroboros Gen 9 / PR #18." in doc
    assert "Accepted commit: `471e9e6`" in doc
    assert ACCEPTED_CHECKPOINT_FULL_SHA in doc
    assert "Ralph Gen 10 through Gen 13 are explicitly rejected" in doc
    assert "grade_regressing" in doc

    for criterion in ISSUE_7_CRITERIA:
        assert criterion in doc

    assert "| Issue #7 criterion | Runtime evidence artifact or observation | Automated verification | Manual evaluator check |" in doc
    assert doc.count("Runtime evidence artifact or observation") == 1
    assert doc.count("pytest tests/test_personal_algorithm_engine.py::") >= len(ISSUE_7_CRITERIA)
    assert doc.count("| `pytest tests/test_personal_algorithm_engine.py::") >= len(ISSUE_7_CRITERIA)

    runtime_evidence_terms = [
        "POST `/events/beacon`",
        "GET `/feed`",
        "GET `/feed/metrics`",
        "get_personal_algorithm_policy()",
        "interpret_behavior_event(...)",
        "confirm_edit(...)",
        "restore_algorithm_version(1)",
        "GET `/feed/api?limit=20`",
        "`delivery_policy.does_not_mutate_ensemble == true`",
    ]
    for term in runtime_evidence_terms:
        assert term in doc


def test_issue19_evidence_parses_acceptance_criteria_references_into_normalized_set():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    references = _extract_issue7_acceptance_criterion_references(doc)
    expected_references = _authoritative_issue7_acceptance_criteria()
    validation = _validate_acceptance_criterion_references(
        references,
        expected_references,
    )

    assert validation == {"missing": [], "nonexistent": []}
    assert len(references) == len(ISSUE_7_CRITERIA)


def test_issue19_evidence_flags_nonexistent_acceptance_criteria_references():
    authoritative_references = _authoritative_issue7_acceptance_criteria()
    parsed_references = set(authoritative_references)
    parsed_references.add("Nonexistent issue #7 criterion that should fail validation.")

    validation = _validate_acceptance_criterion_references(
        parsed_references,
        authoritative_references,
    )

    assert validation["missing"] == []
    assert validation["nonexistent"] == [
        "Nonexistent issue #7 criterion that should fail validation."
    ]


def test_issue19_evidence_flags_stale_acceptance_criteria_references():
    authoritative_references = _authoritative_issue7_acceptance_criteria()
    stale_reference = _normalize_acceptance_criterion_reference(
        "Delivery policy chooses surface/channel/timing/repeat after ranking."
    )
    parsed_references = set(authoritative_references)
    parsed_references.remove(stale_reference)

    validation = _validate_acceptance_criterion_references(
        parsed_references,
        authoritative_references,
    )

    assert validation["missing"] == [stale_reference]
    assert validation["nonexistent"] == []


def test_issue19_evidence_documents_pr18_implemented_behaviors_for_issue7():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "## PR #18 Implemented Behaviors Available for Issue #7 Verification" in doc
    assert "This section describes evidence surfaces only; it does not add or change product behavior." in doc

    implemented_behaviors = [
        "Bounded post-ranking personal algorithm layer",
        "Feed mode UI and instrumentation",
        "Raw behavior events and derived rewards separation",
        "Swipe defaults and natural-language edit guardrails",
        "Policy rollback and shadow fitness evidence",
        "Sovereignty and future-work boundaries",
    ]
    for behavior in implemented_behaviors:
        assert behavior in doc

    evidence_surfaces = [
        "`/feed/api` item metadata",
        "`/feed` renders Grid, Detail Swipe, and Dense Reader controls",
        "`/events/beacon` persists raw behavior events and derived reward rows separately",
        "`get_personal_algorithm_policy()`",
        "`restore_algorithm_version(1)`",
        "`algorithm.yaml` and `sovereignty.yaml`",
    ]
    for surface in evidence_surfaces:
        assert surface in doc


def test_issue19_evidence_references_existing_files_and_tests():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    for relative_path in REFERENCED_FILES:
        assert relative_path in doc
        assert (ROOT / relative_path).exists()

    test_source = (ROOT / "tests" / "test_personal_algorithm_engine.py").read_text(encoding="utf-8")
    for test_name in REFERENCED_TESTS:
        assert test_name in doc
        assert f"def {test_name}" in test_source


def test_issue19_evidence_lists_canonical_personal_algorithm_test_command():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")
    normalized_doc = re.sub(r"\s+", " ", doc)

    assert "Canonical verification for this evidence package and current behavior:" in doc
    assert f"```bash\n{PERSONAL_ALGORITHM_TEST_COMMAND}\n```" in doc
    assert "Latest clean personal algorithm test result on 2026-05-14:" in doc
    assert "The canonical command above was attempted in this local sandbox" in doc
    assert "blocked before test collection" in normalized_doc
    assert "PermissionError: [Errno 1] Operation not permitted" in normalized_doc
    assert "clean result corresponding to the same canonical test target" in normalized_doc
    assert f"```bash\n{PERSONAL_ALGORITHM_CLEAN_TEST_COMMAND}\n```" in doc
    assert "Result: exited `0` with `4 passed" in doc


def test_issue19_evidence_lists_canonical_full_pytest_without_rerunfailures():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")
    normalized_doc = re.sub(r"\s+", " ", doc)

    assert "Canonical full-suite pytest verification for PR #18 / issue #7 regression coverage:" in doc
    assert f"```bash\n{FULL_PYTEST_COMMAND}\n```" in doc
    assert "This canonical full pytest command does not use `pytest-rerunfailures`" in doc
    assert "`--reruns`, or any rerun plugin flag" in doc
    assert "is not the canonical verifier command" in normalized_doc


def test_issue19_evidence_scans_referenced_repository_files_exist():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    referenced_files = _extract_referenced_repository_files(doc)

    assert set(REFERENCED_FILES).issubset(referenced_files)

    stale_current_files = [
        relative_path
        for relative_path in referenced_files
        if not (ROOT / relative_path).exists()
    ]
    assert stale_current_files == []


def test_issue19_evidence_checkpoint_metadata_matches_git_commit():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert _git("rev-parse", "--verify", f"{ACCEPTED_CHECKPOINT_SHORT_SHA}^{{commit}}") == (
        ACCEPTED_CHECKPOINT_FULL_SHA
    )
    assert "Accepted checkpoint metadata for stale-reference validation:" in doc
    for relative_path in ACCEPTED_CHECKPOINT_FILES:
        assert f"- `{relative_path}`" in doc

    accepted_tree_files = _accepted_checkpoint_tree_files()
    stale_metadata_files = [
        relative_path
        for relative_path in ACCEPTED_CHECKPOINT_FILES
        if relative_path not in accepted_tree_files
    ]
    assert stale_metadata_files == []


def test_issue19_evidence_rejects_references_absent_from_accepted_checkpoint():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    referenced_files = _extract_referenced_repository_files(doc)
    accepted_checkpoint_files = _accepted_checkpoint_tree_files()
    evidence_only_files = {
        "docs/issue19-evidence-package.md",
        "docs/issue19-pr-summary.md",
        "tests/test_issue19_evidence_package.py",
    }
    stale_checkpoint_files = sorted(
        referenced_files - accepted_checkpoint_files - evidence_only_files
    )

    assert stale_checkpoint_files == []


def test_issue19_evidence_rejects_test_references_absent_from_accepted_checkpoint():
    accepted_test_functions = _accepted_checkpoint_test_functions(
        "tests/test_personal_algorithm_engine.py",
    )

    stale_test_references = sorted(set(REFERENCED_TESTS) - accepted_test_functions)

    assert stale_test_references == []


def test_issue19_evidence_documents_known_limitations_without_expanding_scope():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "## Known Limitations" in doc
    assert "does not claim" in doc
    assert "does not prove a new production ranking algorithm" in doc
    assert "does not validate full multimodal ingestion" in doc
    assert "The SOTA/VLM learning loop is not implemented by PR #18." in doc
    assert "does not train, tune, or evaluate a vision-language model" in doc
    assert "does not claim new retention policy" in doc
    assert "does not claim ranking semantics" in doc
    assert "Ambient delivery UX is not implemented by PR #18." in doc
    assert "post-ranking delivery metadata only" in doc
    assert "arbitrary user prompts can safely mutate production ranking" in doc
    assert "Ralph Gen 10-13 are excluded" in doc
    assert "`grade_regressing`" in doc


def test_issue19_evidence_keeps_ambient_delivery_ux_as_follow_up_gap():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "## Follow-Up Gaps" in doc
    assert "Ambient delivery UX" in doc
    assert "future follow-up work" in doc
    assert "notification/tray reminders" in doc
    assert "post-ranking metadata evidenced for PR #18" in doc


def test_issue19_evidence_keeps_sota_vlm_learning_loop_as_follow_up_gap():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "## Follow-Up Gaps" in doc
    assert "SOTA/VLM learning-loop work" in doc
    assert "vision-language model evaluation" in doc
    assert "multimodal model training" in doc
    assert "SOTA recommender experiments" in doc
    assert "change production ranking behavior" in doc


def test_issue19_evidence_keeps_composite_fitness_as_follow_up_gap():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")
    normalized_doc = re.sub(r"\s+", " ", doc)

    assert "## Known Limitations" in doc
    assert "Composite Fitness is limited to evaluator-visible shadow-test evidence in PR #18." in normalized_doc
    assert "Production Composite Fitness optimization" in doc
    assert "remain future follow-up work" in doc

    assert "## Follow-Up Gaps" in doc
    assert "Composite Fitness production optimization" in doc
    assert "using Composite Fitness to select policies automatically" in normalized_doc
    assert "changing adoption thresholds" in doc
    assert "treating `composite_fitness(...)` shadow-test output as production ranking behavior" in normalized_doc


def test_issue19_evidence_lists_py_compile_command_and_latest_clean_result():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "Canonical syntax verification for the evidence-related Python surface:" in doc
    assert PY_COMPILE_COMMAND in doc
    assert "Latest clean `py_compile` result on 2026-05-14: exited `0` with no output." in doc


def test_issue19_evidence_has_lightweight_validation_entrypoint():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")
    normalized_doc = re.sub(r"\s+", " ", doc)
    entrypoint = EVIDENCE_ENTRYPOINT.read_text(encoding="utf-8")

    assert "Lightweight entrypoint for evaluator-visible evidence validation:" in doc
    assert "sh scripts/verify_issue19_evidence.sh" in doc
    assert "both required evidence-package validation categories" in doc
    assert "issue #7 acceptance-criteria reference validation" in normalized_doc
    assert "repository/checkpoint reference validation" in normalized_doc

    assert "python3 -m py_compile" in entrypoint
    assert (
        "test_issue19_evidence_parses_acceptance_criteria_references_into_normalized_set"
        in entrypoint
    )
    assert "test_issue19_evidence_scans_referenced_repository_files_exist" in entrypoint
    assert "test_issue19_evidence_checkpoint_metadata_matches_git_commit" in entrypoint
    assert "test_issue19_evidence_rejects_references_absent_from_accepted_checkpoint" in entrypoint
    assert "test_issue19_evidence_rejects_test_references_absent_from_accepted_checkpoint" in entrypoint


def test_issue19_evidence_lists_git_diff_check_command_and_latest_clean_result():
    doc = EVIDENCE_DOC.read_text(encoding="utf-8")

    assert "Canonical git diff whitespace verification for the evidence package:" in doc
    assert f"```bash\n{GIT_DIFF_CHECK_COMMAND}\n```" in doc
    assert "Latest clean `git diff --check` result on 2026-05-14: exited `0` with no" in doc
    assert "output." in doc
