# CLAUDE.md

Context for Claude Code / Claude Cowork working in this repo. Read this
before making changes.

## First session in this repo — do this before anything else

Setup is scripted. Run it and confirm it's green before any feature work:

```bash
./scripts/bootstrap.sh
source .venv/bin/activate
```

That creates `.venv`, installs core + every `plugins/*` package, and
verifies the CLI loads, entry-point discovery works, and all tests pass.
It exits non-zero if any check fails, and it's re-runnable. If a check
fails, **stop and report it rather than patching around it** — that means
the scaffold has a real bug, and `docs/STAGES.md` checkboxes should not
be flipped until it's fixed.

Expected green state as of 2026-08-19 (verified on Python 3.14.0,
macOS/arm64): `lookup-cli plugins list` shows two rows — `echo` (built-in)
and `echo_standalone` (the template package) — and 15 tests pass (13 from
the root `tests/` run + 2 in `plugins/echo_plugin/tests/`, which the root
run does not collect; see Stage 0 in `docs/STAGES.md`). Coverage is 87%,
with `config.py` at 0% because nothing exercises `Settings` yet.

Then:

1. **Fill in `.env`** (bootstrap creates it from `.env.example` if absent)
   with real `OKTA_ORG_URL` / `OKTA_API_TOKEN` and `JIRA_BASE_URL` /
   `JIRA_EMAIL` / `JIRA_API_TOKEN` (both services already have
   credentials per `docs/STAGES.md`). Leave the Jamf/ABM/allwhere
   `LOOKUP_CLI_MOCK_*=1` flags as-is — no credentials for those yet.
2. **Resolve or triage the Open Decisions Log** at the bottom of
   `docs/STAGES.md` before starting Stage 2-3 implementation work —
   at minimum, flag which ones block starting vs. which can wait:
   - Per-plugin cache TTLs
   - Jira: `reporter` vs. `assignee` for "tickets submitted"
   - ABM auth path (Apple direct API vs. MDM vendor proxy) — doesn't
     block Stage 5's mock-first work, but blocks the real-API follow-up
   - Whether per-plugin CLI subcommands stay centralized in `cli.py`
     or move into each plugin package
   - Supported Python versions (CI pins 3.11, local dev is on 3.14)
   - Whether `plugins/*/tests` should be collected by the root `pytest`
3. **Two known gaps worth closing before Stage 2** (both tracked in
   `docs/STAGES.md`): the root `pytest` run doesn't collect
   `plugins/*/tests`, and `config.py`'s `Settings` loader has no tests
   despite Stage 2 being about to depend on it for Okta credentials.
4. **Only after the above**, pick up the next unchecked task in
   `docs/STAGES.md` (Stage 2, Okta, is next — real credentials are
   already available for it) and follow the TDD loop in "When picking
   up a task" below.

## Running commands in this repo (read this before running anything)

**Always use explicit venv paths: `.venv/bin/pytest`, `.venv/bin/pip`,
`.venv/bin/lookup-cli`, `.venv/bin/python`.**

Each Bash tool call starts a fresh shell from the user's profile, so a venv
the developer activated in their own terminal is *not* active here —
`VIRTUAL_ENV` is unset and `.venv/bin` is not on `PATH`. A bare `pytest` will
either fail with "command not found" or, worse, silently run a
globally-installed pytest against an interpreter that has none of this
project's dependencies and report a misleading result. There is no PATH
override in `.claude/settings.json` to paper over this: Claude Code's `env`
block takes literal strings with no variable interpolation, so a committed
`PATH` would have to hardcode one machine's absolute paths and freeze them.
The explicit-path convention is the fix.

`.claude/settings.json` (committed) pre-approves the read-only and
`.venv/bin/*` commands so sessions don't stall on permission prompts, and
denies reading `.env` — it holds real Okta/Jira tokens, which should never
land in a transcript. Personal overrides go in `.claude/settings.local.json`,
which is gitignored.

Two more things worth knowing:

- **Read `docs/STAGES.md` before starting work.** It's the live task board.
  Stage 2 (Okta) is next and has real credentials. "Start the next unchecked
  Stage 2 task" is a well-formed request; the TDD loop below then applies.
- **Nothing mechanically enforces tests-first.** CI runs the suite but won't
  block implementation that arrived without tests. The discipline in "Ground
  rules" below is the only thing holding that line.

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
./scripts/bootstrap.sh                    # install + verify everything (start here)
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

- Stage 0 (plugin framework): **verified green** 2026-08-19 — installed
  and run against real deps on Python 3.14.0. 5 tests pass under
  `-m plugin_framework`; `lookup-cli plugins list` shows `echo` and
  `echo_standalone`. Remaining: CI needs one real PR run, and
  `testpaths` needs fixing to collect per-plugin tests.
- Stage 1 (cache/data model): **verified green** 2026-08-19 — 8 tests
  pass under `-m cache`. `cache.py` 100% covered, `config.py` 0%
  (untested `Settings` loader).
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
