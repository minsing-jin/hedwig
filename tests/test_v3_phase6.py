"""Phase 6 tests — engine library extraction boundaries.

Verifies that hedwig.engine / hedwig.evolution / hedwig.qa do not import
from the parts of Hedwig meant to stay behind during extraction
(dashboard, saas, delivery, native).
"""
from __future__ import annotations

import ast
import pathlib


ENGINE_DIRS = [
    "hedwig/engine",
    "hedwig/evolution",
    "hedwig/qa",
]

FORBIDDEN_PREFIXES = (
    "hedwig.dashboard",
    "hedwig.saas",
    "hedwig.delivery",
    "hedwig.native",
)


def _collect_imports(py_path: pathlib.Path) -> set[str]:
    try:
        tree = ast.parse(py_path.read_text())
    except Exception:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_engine_does_not_import_forbidden_packages():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for d in ENGINE_DIRS:
        base = repo_root / d
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if py.name == "__pycache__":
                continue
            imports = _collect_imports(py)
            for imp in imports:
                if any(imp.startswith(p) for p in FORBIDDEN_PREFIXES):
                    violations.append(f"{py.relative_to(repo_root)} imports {imp}")
    assert not violations, "Engine boundary violation:\n" + "\n".join(violations)


def test_engine_public_api_importable():
    from hedwig.engine import pre_score, pre_filter, normalize_batch, normalize_content  # noqa
    import hedwig.engine as eng
    assert callable(eng.pre_score)
    assert callable(eng.pre_filter)


def test_engine_lazy_exports_resolve():
    import hedwig.engine as eng

    # These are lazy-loaded on first attribute access
    assert callable(getattr(eng, "run_two_stage"))
    assert callable(getattr(eng, "rank_with_ensemble"))
    assert callable(getattr(eng, "trace_signal"))
    assert callable(getattr(eng, "enrich_score"))
    assert callable(getattr(eng, "filter_critical"))


def test_engine_dir_lists_public_surface():
    import hedwig.engine as eng
    exposed = dir(eng)
    for name in ("pre_score", "pre_filter", "run_two_stage", "trace_signal"):
        assert name in exposed


def test_engine_unknown_attribute_raises():
    import hedwig.engine as eng
    try:
        _ = eng.totally_not_a_thing
    except AttributeError:
        return
    raise AssertionError("expected AttributeError for unknown engine symbol")
