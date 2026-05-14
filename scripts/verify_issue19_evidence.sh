#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

python3 -m py_compile \
  hedwig/personal_algorithm.py \
  hedwig/dashboard/app.py \
  hedwig/onboarding/nl_algo_editor.py \
  hedwig/storage/local.py \
  hedwig/storage/supabase.py \
  tests/test_personal_algorithm_engine.py \
  tests/test_issue19_evidence_package.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  tests/test_issue19_evidence_package.py::test_issue19_evidence_parses_acceptance_criteria_references_into_normalized_set \
  tests/test_issue19_evidence_package.py::test_issue19_evidence_scans_referenced_repository_files_exist \
  tests/test_issue19_evidence_package.py::test_issue19_evidence_checkpoint_metadata_matches_git_commit \
  tests/test_issue19_evidence_package.py::test_issue19_evidence_rejects_references_absent_from_accepted_checkpoint \
  tests/test_issue19_evidence_package.py::test_issue19_evidence_rejects_test_references_absent_from_accepted_checkpoint \
  -q
