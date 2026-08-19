"""
Plugin discovery via Python entry points.

Any installed package that registers a class under the
`lookup_cli.plugins` entry-point group is automatically picked up --
no import list to maintain in core code.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Iterator

from lookup_cli.plugins.base import ConnectorPlugin

ENTRY_POINT_GROUP = "lookup_cli.plugins"


class PluginLoadError(RuntimeError):
    """Raised when a registered entry point doesn't satisfy the plugin contract."""


def discover_plugins() -> dict[str, ConnectorPlugin]:
    """Load and instantiate every registered plugin.

    Returns a dict keyed by plugin `.name`. Raises PluginLoadError with
    a clear message if an entry point doesn't resolve to a valid
    ConnectorPlugin subclass -- fail loud at startup, not silently at
    lookup time.
    """
    plugins: dict[str, ConnectorPlugin] = {}
    for ep in _iter_entry_points():
        try:
            plugin_cls = ep.load()
        except Exception as exc:  # noqa: BLE001 - re-raised with context below
            raise PluginLoadError(
                f"Failed to load plugin entry point '{ep.name}' ({ep.value}): {exc}"
            ) from exc

        if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, ConnectorPlugin)):
            raise PluginLoadError(
                f"Entry point '{ep.name}' ({ep.value}) does not resolve to a "
                f"ConnectorPlugin subclass."
            )

        instance = plugin_cls()
        if not getattr(instance, "name", None):
            raise PluginLoadError(
                f"Plugin loaded from entry point '{ep.name}' has no `name` attribute."
            )
        plugins[instance.name] = instance

    return plugins


def _iter_entry_points() -> Iterator:
    eps = entry_points()
    # importlib.metadata's select() API (3.10+) vs. dict-like fallback
    if hasattr(eps, "select"):
        return iter(eps.select(group=ENTRY_POINT_GROUP))
    return iter(eps.get(ENTRY_POINT_GROUP, []))  # type: ignore[union-attr]
