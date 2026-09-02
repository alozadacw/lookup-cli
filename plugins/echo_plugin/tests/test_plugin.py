import pytest
from echo_plugin.plugin import EchoStandalonePlugin

# Every plugin package's tests carry their stage marker, so `pytest -m <stage>`
# covers the plugin as well as core. Copy this line into new connectors.
pytestmark = pytest.mark.plugin_framework


async def test_fetch_returns_ok_result():
    plugin = EchoStandalonePlugin()
    result = await plugin.fetch("jdoe")
    assert result.ok
    assert result.data == {"echoed": "jdoe"}


async def test_fetch_wraps_backend_errors_into_error_field(monkeypatch):
    plugin = EchoStandalonePlugin()

    async def boom(identifier):
        raise RuntimeError("boom")

    monkeypatch.setattr(plugin, "_call_backend", boom)
    result = await plugin.fetch("jdoe")
    assert not result.ok
    assert result.error == "boom"


async def test_fetch_scrubs_secrets_out_of_error_strings(monkeypatch):
    """The template must model safe_error(), not str(exc) -- errors are cached."""
    plugin = EchoStandalonePlugin()

    async def leaky(identifier):
        raise RuntimeError("401 for https://acme.example.com/api?token=supersecretvalue")

    monkeypatch.setattr(plugin, "_call_backend", leaky)
    result = await plugin.fetch("jdoe")
    assert "supersecretvalue" not in result.error
    assert "acme.example.com" in result.error
