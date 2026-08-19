# Project plan: stages, tasks, and ownership

Each stage is an epic. Each task below is sized to be picked up
independently by one developer and closed with a passing test run
under that stage's `pytest` marker. Copy tasks into GitHub Issues (or
your tracker of choice) 1:1 -- the checkboxes here double as a
lightweight board if you'd rather not stand up tooling yet.

Suggested labels: `stage:0`..`stage:8`, `plugin:okta`/`jira`/`jamf`/`abm`/`allwhere`,
`type:test`, `type:impl`, `type:docs`.

Legend: **[ ]** not started **[~]** in progress **[x]** done

---

## Stage 0 -- Plugin Framework
**Status: verified green** -- installed and run 2026-08-19 on Python 3.14.0
(macOS/arm64): `pytest -m plugin_framework` 5 passed, `lookup-cli plugins
list` shows both `echo` and `echo_standalone`. Reproduce with
`./scripts/bootstrap.sh`.

| Task | Depends on | Notes |
|---|---|---|
| [x] Define `ConnectorPlugin` ABC + `ConnectorResult` dataclass | -- | `src/lookup_cli/plugins/base.py` |
| [x] Implement entry-point-based `discover_plugins()` | ABC | `src/lookup_cli/plugins/registry.py` |
| [x] Built-in `echo` plugin proving discovery works | registry | `src/lookup_cli/plugins/echo_builtin.py` |
| [x] Standalone installable `echo_plugin` template package | registry | `plugins/echo_plugin/` -- copy this for every real connector |
| [x] `lookup-cli plugins list` command | registry, CLI skeleton | `src/lookup_cli/cli.py` |
| [x] **Run `pytest -m plugin_framework` in a real environment and confirm green** | all above | 5 passed on Python 3.14.0, 2026-08-19 |
| [x] Scripted one-command bootstrap so this is reproducible for every dev | above | `scripts/bootstrap.sh` -- installs core + all `plugins/*` packages, verifies CLI/discovery/tests, exits non-zero on failure. Referenced as the first step in `README.md` |
| [~] Set up CI (GitHub Actions) running `pytest` on every PR | above | `.github/workflows/tests.yml` exists and matches the verified local commands; still needs one real PR run to confirm green in CI. Flip to [x] after that |
| [ ] Fix `testpaths` so per-plugin test suites are collected | above | `pyproject.toml` sets `testpaths = ["tests"]`, so the 2 tests in `plugins/echo_plugin/tests/` are collected by neither a bare `pytest` nor CI (root run collects 13, not 15). They pass when run explicitly. Every real connector inherits this blind spot, so fix before Stage 2. Either add `plugins` to `testpaths` or add a per-plugin pytest step to CI -- touches core config, so decide deliberately |

**Stage 0 is done when:** a developer can install the package, run
`pytest -m plugin_framework`, see it pass, run `lookup-cli plugins list`,
and see `echo` in the output.

---

## Stage 1 -- Cache & Data Model
**Status: verified green** -- `pytest -m cache` 8 passed, 2026-08-19.
`cache.py` at 100% line coverage, `models.py` at 95%. `config.py` is at 0% --
no test exercises `Settings` yet (see task below).

| Task | Depends on | Notes |
|---|---|---|
| [x] `Cache` class (SQLite, per plugin+identifier, TTL) | -- | `src/lookup_cli/cache.py` |
| [x] `UnifiedUserRecord` merge/error model | -- | `src/lookup_cli/models.py` |
| [x] `Settings` config loader (env vars / `.env`) | -- | `src/lookup_cli/config.py` |
| [x] **Run `pytest -m cache` and confirm green** | Cache, model | 8 passed on Python 3.14.0, 2026-08-19 |
| [ ] Write tests for `Settings` config loader | Settings | `src/lookup_cli/config.py` is at 0% coverage -- nothing loads it yet. Cover env-var precedence, `.env` fallback, and missing-required-var behavior before Stage 2 depends on it for Okta creds |
| [ ] Decide & document per-plugin default TTLs (Okta status probably shorter than, say, ABM device assignment) | none yet -- open decision | add to `docs/ARCHITECTURE.md` once decided |

**Stage 1 is done when:** `pytest -m cache` passes, and cache/model
behavior is exercised by at least one real plugin in Stage 2.

---

## Stage 2 -- Okta Connector (real API, credentials available)

| Task | Depends on |
|---|---|
| [ ] Write mocked-response tests: active, suspended, deprovisioned, not-found, timeout/5xx | Stage 0 |
| [ ] Implement `okta_plugin` package (copy `echo_plugin` template) | tests above |
| [ ] Implement real Okta API client (`GET /api/v1/users/{login}`) behind `_call_backend` | tests above |
| [ ] `lookup-cli okta status <user>` subcommand | plugin implemented |
| [ ] Add `OKTA_ORG_URL` / `OKTA_API_TOKEN` to `.env.example` (already stubbed) and confirm real token works in a manual smoke test | plugin implemented |
| [ ] Add `okta` marker to `pyproject.toml` pytest markers | -- |

**Done when:** `pytest -m okta` green on mocks, and one manual
`lookup-cli okta status <realuser>` against real Okta returns a sane result.

---

## Stage 3 -- Jira Connector (real API, credentials available)

| Task | Depends on |
|---|---|
| [ ] Write mocked-response tests: tickets found, zero results, pagination, auth error | Stage 0 |
| [ ] Implement `jira_plugin` package | tests above |
| [ ] JQL query `reporter = "<user>"` (confirm: reporter vs. assignee -- decide with team, document choice) | tests above |
| [ ] `lookup-cli jira tickets <user>` subcommand | plugin implemented |
| [ ] Leave room in `properties` for future status/project filters (don't build the filter UI yet, just don't block it) | plugin implemented |

**Done when:** `pytest -m jira` green on mocks, manual smoke test against real Jira confirmed.

---

## Stage 4 -- Jamf Connector (mock-first, no credentials yet)

| Task | Depends on |
|---|---|
| [ ] Write tests against fixture data: devices found, zero devices, malformed fixture | Stage 0 |
| [ ] Build realistic fixture JSON (device name, serial, model, last check-in, assigned user) | -- |
| [ ] Implement `jamf_plugin` package with `LOOKUP_CLI_MOCK_JAMF` toggle | tests, fixtures |
| [ ] `lookup-cli jamf devices <user>` subcommand | plugin implemented |
| [ ] **Blocked/parallel track:** once credentials exist, implement real `_call_backend` (Jamf Pro API) -- no test/CLI changes needed | credentials provisioned |

**Done when:** `pytest -m jamf` green against fixtures; real-API swap is a
separate, low-risk follow-up task once creds land.

---

## Stage 5 -- ABM Connector (mock-first, no credentials yet)

| Task | Depends on |
|---|---|
| [ ] **Decision needed:** confirm ABM auth path -- Apple's official Business Manager API (server-to-server, JWT via private key) vs. going through your MDM vendor's ABM proxy endpoints. This changes the real client's shape; doesn't block mock work. | -- |
| [ ] Write tests against fixture data: devices found, zero devices | Stage 0 |
| [ ] Build realistic fixture JSON (device serial, model, enrollment status, MDM server assignment) | -- |
| [ ] Implement `abm_plugin` package with `LOOKUP_CLI_MOCK_ABM` toggle | tests, fixtures |
| [ ] `lookup-cli abm devices <user>` subcommand | plugin implemented |

**Done when:** `pytest -m abm` green against fixtures. Flag the auth
decision above to whoever owns Apple/MDM vendor relationship before
starting the real-API follow-up.

---

## Stage 6 -- allwhere Connector (mock-first, no credentials yet)

| Task | Depends on |
|---|---|
| [ ] Write tests against fixture data: shipments found, zero shipments, in-transit vs. delivered states | Stage 0 |
| [ ] Build realistic fixture JSON | -- |
| [ ] Implement `allwhere_plugin` package with `LOOKUP_CLI_MOCK_ALLWHERE` toggle | tests, fixtures |
| [ ] `lookup-cli allwhere shipments <user>` subcommand | plugin implemented |

**Done when:** `pytest -m allwhere` green against fixtures.

---

## Stage 7 -- Aggregation & Output

| Task | Depends on |
|---|---|
| [ ] `lookup-cli lookup <user>` -- runs every discovered plugin, merges via `UnifiedUserRecord` | Stages 2-6 (or however many are done) |
| [ ] One plugin erroring must not fail the whole command -- test with a deliberately broken mock plugin | above |
| [ ] `--format table\|json` output flag (default table via `rich`) | above |
| [ ] Cache integration: check cache before calling `fetch()`, write through after | Stage 1 cache |
| [ ] Snapshot/golden-file tests for table and JSON output | above |
| [ ] (Nice-to-have, not required for Stage 7 done-ness) concurrent fetch across plugins | above |

**Done when:** `pytest -m cli` green, and `lookup-cli lookup <user>`
against a mix of real + mocked plugins produces a readable combined result.

---

## Stage 8 -- Extensibility Proof & Docs Finalization

| Task | Depends on |
|---|---|
| [ ] A team member who did **not** write the plugin framework builds a throwaway 6th plugin using only `docs/CONNECTOR_GUIDE.md` | Stages 0-7 |
| [ ] Confirm zero edits were needed inside `src/lookup_cli/` | above |
| [ ] Fold any friction points found into `docs/CONNECTOR_GUIDE.md` | above |
| [ ] Final pass on `README.md`, `docs/ARCHITECTURE.md` for accuracy vs. what actually got built | above |

**Done when:** the extensibility claim in the README is empirically true, not aspirational.

---

## Open decisions log

Track anything raised above that needs a team/product decision before
the relevant stage can finish, so it doesn't get lost in a task list:

- [ ] Per-plugin cache TTLs (Stage 1)
- [ ] Jira: reporter vs. assignee for "tickets submitted" (Stage 3)
- [ ] ABM auth path: Apple direct API vs. MDM vendor proxy (Stage 5)
- [ ] Whether CLI subcommands for each plugin live in that plugin's own
      package or stay centralized in `src/lookup_cli/cli.py` (currently
      centralized; revisit if plugin count grows)
- [ ] Supported Python versions (Stage 0). `requires-python = ">=3.11"`, CI
      pins 3.11, but local dev is happening on 3.14 -- so CI is not testing
      what developers run. Decide whether to add a version matrix to
      `.github/workflows/tests.yml` or standardize on one local version.
      All deps (pydantic 2.13, typer 0.27, httpx 0.28, respx, freezegun)
      install and pass cleanly on 3.14 today.
- [ ] Whether `plugins/*/tests` should be collected by the root `pytest` run
      (Stage 0). Tracked as a task above; noting here because it changes core
      `pyproject.toml` config and affects every future connector package.
