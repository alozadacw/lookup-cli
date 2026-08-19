# Adding a new connector plugin

Follow this for Jamf/ABM/allwhere, and for any future service. This
project is TDD: write the test file before the implementation file for
every step below that produces code.

## 1. Copy the template

```bash
cp -r plugins/echo_plugin plugins/<service>_plugin
mv plugins/<service>_plugin/echo_plugin plugins/<service>_plugin/<service>_plugin
```

## 2. Update `pyproject.toml` in the new package

- `project.name` -> `lookup-cli-<service>-plugin`
- entry point -> `<service> = "<service>_plugin.plugin:<Service>Plugin"`

The entry point group name (`lookup_cli.plugins`) must stay identical --
that's the contract the registry scans for.

## 3. Write tests first

In `plugins/<service>_plugin/tests/test_plugin.py`, write cases for:

- a normal successful lookup (assert on `.data` shape)
- "identifier not found" (should this be `error=` or empty `data`? decide
  per-service and document it in the plugin's own docstring)
- an auth/HTTP error (assert `.error` is set, `.ok is False`, and that
  `fetch()` did NOT raise)
- (if the service paginates) a multi-page result assembles correctly

Mock the HTTP layer -- don't hit the real API in unit tests. Use
`respx` for `httpx`-based clients.

## 4. Implement `fetch()`

Keep the actual HTTP/SDK call in its own method (see `_call_backend` in
the template) so:
- tests can monkeypatch just that method when a full HTTP mock isn't
  needed, and
- swapping in mock-mode vs. real-mode implementations later is a
  one-method change.

`fetch()` itself must never raise for ordinary failure modes -- catch
and return `ConnectorResult(error=...)` instead. Let unexpected bugs
propagate (don't swallow everything with a bare `except: pass`).

## 5. Support mock mode if credentials aren't ready yet

```python
import os

class JamfPlugin(ConnectorPlugin):
    name = "jamf"

    def __init__(self):
        self._mock = os.getenv("LOOKUP_CLI_MOCK_JAMF") == "1"

    def _call_backend(self, identifier: str) -> dict:
        if self._mock:
            return self._mock_fixture(identifier)
        return self._real_api_call(identifier)
```

Keep fixtures in `plugins/<service>_plugin/<service>_plugin/fixtures/`
as small, realistic JSON files -- these double as the shape documentation
for whoever eventually wires up the real API.

## 6. Register optional fields via `properties`/`tags`

Don't grow `ConnectorResult.data`'s schema for one-off extra fields --
put them in `properties` (structured) or `tags` (labels). This is what
the original spec's "leave room for optionals" requirement maps to.

## 7. Wire the CLI subcommand

Add a `typer.Typer()` sub-app in the plugin package (or in
`src/lookup_cli/cli.py` if you'd rather keep CLI wiring central --
team's call per plugin) following the `plugins list` pattern in
`cli.py`.

## 8. Install and verify

```bash
pip install -e plugins/<service>_plugin
pytest -m <service>          # add the marker to pyproject.toml first
lookup-cli plugins list      # confirm it shows up
lookup-cli <service> <cmd> <identifier>
```

## 9. Document service-specific env vars

Add them to `.env.example` with a comment, following the existing
pattern for Okta/Jira/Jamf/ABM/allwhere.

---

**Proof this works:** Stage 8 of the project plan requires building a
throwaway 6th plugin using *only* this guide, with zero edits to
`src/lookup_cli/`. If that stage requires a core-code change, this
guide (or the plugin contract) has a gap that needs fixing before the
project is considered "done" architecturally.
