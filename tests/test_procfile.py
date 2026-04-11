"""Test that Procfile exists and is valid for Railway deployment."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_procfile_exists():
    """Procfile must exist at project root."""
    procfile = ROOT / "Procfile"
    assert procfile.exists(), "Procfile is missing from project root"


def test_procfile_has_web_process():
    """Procfile must define a 'web:' process type for Railway."""
    procfile = ROOT / "Procfile"
    content = procfile.read_text()
    assert content.strip(), "Procfile is empty"
    assert content.startswith("web:"), "Procfile must define a 'web:' process type"


def test_procfile_uses_port_env():
    """Procfile must reference $PORT so Railway can assign the port."""
    content = (ROOT / "Procfile").read_text()
    assert "$PORT" in content, "Procfile must use $PORT environment variable"


def test_procfile_launches_hedwig():
    """Procfile web process must launch hedwig."""
    content = (ROOT / "Procfile").read_text()
    assert "hedwig" in content, "Procfile must launch hedwig"


def test_procfile_enables_saas_mode():
    """Procfile must enable --saas and --dashboard flags for SaaS deployment."""
    content = (ROOT / "Procfile").read_text()
    assert "--saas" in content, "Procfile must include --saas flag"
    assert "--dashboard" in content, "Procfile must include --dashboard flag"
