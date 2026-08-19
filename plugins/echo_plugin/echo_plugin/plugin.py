"""
Template connector plugin.

To build a real connector (e.g. Jamf):
    1. Copy this whole `plugins/echo_plugin/` directory to `plugins/jamf_plugin/`.
    2. Rename the package dir `echo_plugin/` -> `jamf_plugin/`.
    3. Rewrite `fetch()` below to call the real API, with your own client
       class so it's easy to swap a mock client for a real one (see
       docs/CONNECTOR_GUIDE.md for the recommended shape).
    4. Update pyproject.toml: project name, entry-point name/target.
    5. Write tests FIRST (tests/test_plugin.py) against a mocked HTTP
       client before writing the real fetch() logic -- this is a
       TDD project.
    6. `pip install -e plugins/jamf_plugin`.
"""

from __future__ import annotations

from lookup_cli.plugins.base import ConnectorPlugin, ConnectorResult


class EchoStandalonePlugin(ConnectorPlugin):
    name = "echo_standalone"

    def fetch(self, identifier: str) -> ConnectorResult:
        try:
            data = self._call_backend(identifier)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: never crash aggregation
            return ConnectorResult(plugin_name=self.name, identifier=identifier, error=str(exc))

        return ConnectorResult(
            plugin_name=self.name,
            identifier=identifier,
            data=data,
            tags=["template-plugin"],
        )

    def _call_backend(self, identifier: str) -> dict:
        # Replace this with a real API call. Keep it as its own method
        # so tests can monkeypatch/mock it cleanly.
        return {"echoed": identifier}
