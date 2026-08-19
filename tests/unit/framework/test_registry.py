"""
Stage 0 acceptance tests: the plugin framework.

Run just this stage:  pytest -m plugin_framework
"""

import pytest

from lookup_cli.plugins.base import ConnectorPlugin, ConnectorResult
from lookup_cli.plugins.registry import PluginLoadError, discover_plugins

pytestmark = pytest.mark.plugin_framework


def test_builtin_echo_plugin_is_discovered():
    plugins = discover_plugins()
    assert "echo" in plugins
    assert isinstance(plugins["echo"], ConnectorPlugin)


def test_echo_plugin_fetch_returns_connector_result():
    plugins = discover_plugins()
    result = plugins["echo"].fetch("jdoe")
    assert isinstance(result, ConnectorResult)
    assert result.plugin_name == "echo"
    assert result.identifier == "jdoe"
    assert result.data == {"echoed": "jdoe"}
    assert result.ok is True


def test_invalid_plugin_class_raises_plugin_load_error(monkeypatch):
    """An entry point that doesn't resolve to a ConnectorPlugin subclass
    must fail loudly at load time, not silently at lookup time."""

    class FakeEntryPoint:
        name = "broken"
        value = "not.a.real.module:NotAPlugin"

        def load(self):
            class NotAPlugin:  # does not subclass ConnectorPlugin
                pass

            return NotAPlugin

    monkeypatch.setattr(
        "lookup_cli.plugins.registry._iter_entry_points",
        lambda: iter([FakeEntryPoint()]),
    )

    with pytest.raises(PluginLoadError):
        discover_plugins()


def test_plugin_missing_name_attribute_raises_plugin_load_error(monkeypatch):
    class FakeEntryPoint:
        name = "nameless"
        value = "not.a.real.module:Nameless"

        def load(self):
            class Nameless(ConnectorPlugin):
                name = ""  # falsy -> should be rejected

                def fetch(self, identifier: str) -> ConnectorResult:
                    return ConnectorResult(plugin_name="nameless", identifier=identifier)

            return Nameless

    monkeypatch.setattr(
        "lookup_cli.plugins.registry._iter_entry_points",
        lambda: iter([FakeEntryPoint()]),
    )

    with pytest.raises(PluginLoadError):
        discover_plugins()
