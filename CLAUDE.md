# CLAUDE.md

Context for Claude Code / Claude Cowork working in this repo. Read this
before making changes.

## What this project is

A Python CLI (`lookup-cli`) that looks up a person by name/username and
returns their status/assets across Okta, Jira, Jamf, ABM, and allwhere,
aggregated into one record. Built plugin-first: every service is a
`ConnectorPlugin` discovered via Python entry points, so adding a new
service never requires touching core code. Full rationale in
`docs/ARCHITECTURE.md`.

## Ground rules for working in this repo

1. **TDD is not optional here.** For any new behavior: write the failing
   test under the right `pytest` marker first, then implement. See
   `docs/CONTRIBUTING.md`. If asked to "add feature X," write
   `tests/.../test_x.py` (or the plugin's own `tests/test_plugin.py`)
   before touching implementation files, and say so explicitly.
2. **Core vs. plugin boundary is load-bearing.** Files under
   `src/lookup_cli/plugins/base.py`, `registry.py`, `cache.py`,
   `models.py`, and `cli.py` are core. A task about "add Jamf support"
   should almost never touch these -- if it seems to require touching
   them, stop and flag it rather than assuming it's fine (see
   `docs/STAGES.md` Stage 8, which exists specifically to catch this).
3. **New connector plugin -> follow `docs/CONNECTOR_GUIDE.md` exactly.**
   Copy `plugins/echo_plugin/` as the starting point, don't write one
   from scratch.
4. **`fetch()` must never raise for ordinary failures** (not found,
   auth error, timeout, 5xx). Catch and return `ConnectorResult(error=...)`.
   Only let genuine bugs propagate.
5. **Secrets stay in `.env` / env vars, never in code, tests, git
   history, or fixtures.** Fixtures use obviously-fake values.
6. **Check `docs/STAGES.md` before starting work.** It's the live task
   board -- update checkboxes as you complete tasks, and add newly
   discovered tasks/decisions to the "Open decisions log" at the bottom
   rather than silently deciding them yourself.

## Repo map

```
src/lookup_cli/            core (registry, cache, models, cli, base contract)
plugins/echo_plugin/       template plugin package -- copy for new connectors
tests/unit/framework/      Stage 0 tests
tests/unit/cache/          Stage 1 tests
tests/cli/                 aggregation/CLI tests (Stage 7)
docs/ARCHITECTURE.md       why the system is shaped this way
docs/CONNECTOR_GUIDE.md    how to add a new service, step by step
docs/STAGES.md             the project plan / task board
docs/CONTRIBUTING.md       TDD workflow, branching, PR checklist
```

## Commands Claude should know

```bash
pip install -e ".[dev]"
pip install -e plugins/echo_plugin        # and any other plugin packages
pytest -m plugin_framework                # Stage 0
pytest -m cache                           # Stage 1
pytest -m okta / jira / jamf / abm / allwhere / cli   # per-stage/plugin
pytest --cov=src/lookup_cli               # full suite with coverage
lookup-cli plugins list
lookup-cli lookup <identifier>            # once Stage 7 lands
```

## Current state (update this section as stages complete)

- Stage 0 (plugin framework): scaffolded, tests written, needs a real
  `pip install` + `pytest` run in an environment with network access
  to confirm green (sandboxed dev environments without network access
  can only confirm the code compiles, not that tests pass).
- Stage 1 (cache/data model): scaffolded, same caveat as above.
- Stages 2-8: not started. See `docs/STAGES.md` for the full breakdown.
- Okta and Jira have real credentials available now; Jamf, ABM, and
  allwhere are mock-first until credentials are provisioned.

## When picking up a task from docs/STAGES.md

1. Find the task row, note its "Depends on."
2. Write the test(s) for it first.
3. Implement.
4. Run that stage's marker, then the full suite.
5. Update the checkbox in `docs/STAGES.md` in the same commit/PR.
6. If you hit a decision not already covered (naming, TTL values, auth
   approach, etc.), add it to the Open Decisions Log rather than
   guessing silently.
