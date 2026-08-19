# CLAUDE.md

Context for Claude Code / Claude Cowork working in this repo. Read this
before making changes.

## First session in this repo — do this before anything else

This repo was scaffolded (Stage 0 + Stage 1) in a sandboxed environment
with no network access, so the code was verified with `py_compile`
only — it has **never actually been run against installed
dependencies**. That's the very first thing to fix. Do these in order
and don't skip ahead to feature work until step 4 is green:

1. **Create/activate a virtualenv, then install everything:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   pip install -e plugins/echo_plugin
   ```
2. **Sanity-check the CLI loads:**
   ```bash
   lookup-cli plugins list
   ```
   Expect a table with one row: `echo`. If this fails, the plugin
   framework itself is broken — fix that before anything else, and
   don't touch `docs/STAGES.md` checkboxes until it's confirmed.
3. **Run the two stages that claim to be done and confirm they
   actually are:**
   ```bash
   pytest -m plugin_framework -v
   pytest -m cache -v
   pytest --cov=src/lookup_cli --cov-report=term-missing
   ```
   If anything fails, that's real signal the scaffold has a bug the
   no-network sandbox couldn't catch — fix it, and only then flip
   `docs/STAGES.md`'s "not yet run against installed deps" language to
   confirmed-green.
4. **Copy `.env.example` to `.env`** and fill in real `OKTA_ORG_URL` /
   `OKTA_API_TOKEN` and `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN`
   (both services already have credentials per `docs/STAGES.md`).
   Leave the Jamf/ABM/allwhere `LOOKUP_CLI_MOCK_*=1` flags as-is — no
   credentials for those yet.
5. **Resolve or triage the Open Decisions Log** at the bottom of
   `docs/STAGES.md` before starting Stage 2-3 implementation work —
   at minimum, flag which ones block starting vs. which can wait:
   - Per-plugin cache TTLs
   - Jira: `reporter` vs. `assignee` for "tickets submitted"
   - ABM auth path (Apple direct API vs. MDM vendor proxy) — doesn't
     block Stage 5's mock-first work, but blocks the real-API follow-up
   - Whether per-plugin CLI subcommands stay centralized in `cli.py`
     or move into each plugin package
6. **Only after 1-5 are done**, pick up the next unchecked task in
   `docs/STAGES.md` (Stage 2, Okta, is next — real credentials are
   already available for it) and follow the TDD loop in "When picking
   up a task" below.

If any of steps 1-3 fail, stop and report the failure rather than
patching around it silently — the whole point of this checklist is to
catch anything the offline scaffolding pass couldn't verify.

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
