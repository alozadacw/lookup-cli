"""
The plugin contract.

Every connector (Okta, Jira, Jamf, ABM, allwhere, or any future service)
implements `ConnectorPlugin` and returns a `ConnectorResult`. The core
CLI, cache, and aggregation logic depend ONLY on this interface -- never
on any specific service's API shape. This is what makes new connectors
pluggable without touching core code.

To add a new service:
    1. Create a package (see plugins/echo_plugin for the reference shape).
    2. Implement ConnectorPlugin.fetch().
    3. Register it under the `lookup_cli.plugins` entry-point group in
       that package's pyproject.toml.
    4. `pip install -e .` the plugin package. Done -- no core changes.

See docs/CONNECTOR_GUIDE.md for the full walkthrough.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ConnectorResult:
    """Uniform shape returned by every plugin, regardless of backend.

    `data` holds the fields the plugin's docs promise (e.g. Okta's
    `status`). `properties` and `tags` are open-ended extension points --
    a plugin can attach arbitrary extra fields there without requiring
    any change to this dataclass or to core aggregation logic.
    """

    plugin_name: str
    identifier: str
    data: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ConnectorPlugin(ABC):
    """Base class every connector plugin must subclass."""

    #: Short, stable, lowercase identifier used in cache keys, CLI
    #: subcommands, and entry-point registration (e.g. "okta").
    name: str

    @abstractmethod
    def fetch(self, identifier: str) -> ConnectorResult:
        """Look up `identifier` (e.g. username or email) in this service.

        Must NOT raise on ordinary failure conditions (not found, auth
        error, timeout, etc.) -- catch those and return a ConnectorResult
        with `error` set instead, so one failing plugin never breaks
        aggregation across the other plugins. Only truly unexpected
        programming errors should propagate.
        """
        raise NotImplementedError
