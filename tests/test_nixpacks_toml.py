"""Tests for Railway Nixpacks builder configuration."""

from __future__ import annotations

import pathlib

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = pathlib.Path(__file__).resolve().parent.parent
NIXPACKS = ROOT / "nixpacks.toml"


def _load_nixpacks() -> dict:
    return tomllib.loads(NIXPACKS.read_text(encoding="utf-8"))


def test_nixpacks_toml_exists():
    """nixpacks.toml must exist at project root for Railway Nixpacks builds."""
    assert NIXPACKS.is_file(), "nixpacks.toml must exist for Railway nixpacks builder"


def test_nixpacks_toml_has_valid_top_level_sections():
    """nixpacks.toml must define phases and a start command."""
    data = _load_nixpacks()
    assert "phases" in data, "nixpacks.toml must define build phases"
    assert "start" in data, "nixpacks.toml must define a [start] section"


def test_nixpacks_toml_has_python_setup_phase():
    """Setup phase must provision Python through nixPkgs."""
    data = _load_nixpacks()
    setup = data.get("phases", {}).get("setup", {})
    nix_pkgs = setup.get("nixPkgs")
    assert nix_pkgs, "setup phase must specify nixPkgs"
    assert any("python" in pkg for pkg in nix_pkgs), "nixPkgs must include python"


def test_nixpacks_toml_has_install_commands():
    """Install phase must define commands to install project dependencies."""
    data = _load_nixpacks()
    install = data.get("phases", {}).get("install", {})
    cmds = install.get("cmds")
    assert cmds, "install phase must have cmds"
    assert any("pip install" in cmd for cmd in cmds), "install cmds must install dependencies"


def test_nixpacks_toml_starts_dashboard_in_saas_mode():
    """Start command must launch the SaaS dashboard using Railway's assigned port."""
    data = _load_nixpacks()
    start_cmd = data.get("start", {}).get("cmd", "")
    assert start_cmd, "[start] must have cmd"
    assert "python -m hedwig" in start_cmd, "start cmd must launch hedwig"
    assert "--dashboard" in start_cmd, "start cmd must enable dashboard mode"
    assert "--saas" in start_cmd, "start cmd must enable SaaS mode"
    assert "$PORT" in start_cmd, "start cmd must reference $PORT for Railway"
