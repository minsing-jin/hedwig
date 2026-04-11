"""Verify railway.toml exists with healthcheck path for Railway deployment."""

import pathlib

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_railway_toml_exists():
    """railway.toml must exist at project root."""
    assert (ROOT / "railway.toml").is_file()


def test_railway_toml_has_healthcheck_path():
    """railway.toml must define a healthcheckPath under [deploy]."""
    data = tomllib.loads((ROOT / "railway.toml").read_text())
    deploy = data.get("deploy", {})
    healthcheck = deploy.get("healthcheckPath")
    assert healthcheck is not None, "healthcheckPath not set in [deploy]"
    assert healthcheck.startswith("/"), "healthcheckPath should be an absolute path"


def test_railway_toml_has_start_command():
    """railway.toml must define a startCommand under [deploy]."""
    data = tomllib.loads((ROOT / "railway.toml").read_text())
    deploy = data.get("deploy", {})
    assert deploy.get("startCommand"), "startCommand not set in [deploy]"


def test_railway_toml_has_build_section():
    """railway.toml must define a [build] section."""
    data = tomllib.loads((ROOT / "railway.toml").read_text())
    assert "build" in data, "[build] section missing from railway.toml"


@pytest.mark.asyncio
async def test_railway_healthcheck_path_is_live_saas_route():
    """Configured Railway healthcheck path must return HTTP 200 in SaaS mode."""
    from httpx import ASGITransport, AsyncClient

    from hedwig.dashboard.app import create_app

    data = tomllib.loads((ROOT / "railway.toml").read_text())
    healthcheck = data["deploy"]["healthcheckPath"]
    app = create_app(saas_mode=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(healthcheck)

    assert resp.status_code == 200, (
        f"healthcheckPath {healthcheck!r} returned {resp.status_code}"
    )
