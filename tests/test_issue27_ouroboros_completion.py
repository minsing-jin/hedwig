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
