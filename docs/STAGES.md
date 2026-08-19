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
**Status: scaffolded, tests written, not yet run against installed deps**

| Task | Depends on | Notes |
|---|---|---|
| [x] Define `ConnectorPlugin` ABC + `ConnectorResult` dataclass | -- | `src/lookup_cli/plugins/base.py` |
| [x] Implement entry-point-based `discover_plugins()` | ABC | `src/lookup_cli/plugins/registry.py` |
| [x] Built-in `echo` plugin proving discovery works | registry | `src/lookup_cli/plugins/echo_builtin.py` |
| [x] Standalone installable `echo_plugin` template package | registry | `plugins/echo_plugin/` -- copy this for every real connector |
| [x] `lookup-cli plugins list` command | registry, CLI skeleton | `src/lookup_cli/cli.py` |
| [ ] **Run `pytest -m plugin_framework` in a real environment and confirm green** | all above | first team member to pick this up: `pip install -e ".[dev]"` then `pip install -e plugins/echo_plugin` |
| [ ] Set up CI (GitHub Actions) running `pytest` on every PR | above | template workflow not yet added -- open task |

**Stage 0 is done when:** a developer can install the package, run
`pytest -m plugin_framework`, see it pass, run `lookup-cli plugins list`,
and see `echo` in the output.

---

## Stage 1 -- Cache & Data Model
**Status: scaffolded, tests written, not yet run**

| Task | Depends on | Notes |
|---|---|---|
| [x] `Cache` class (SQLite, per plugin+identifier, TTL) | -- | `src/lookup_cli/cache.py` |
| [x] `UnifiedUserRecord` merge/error model | -- | `src/lookup_cli/models.py` |
| [x] `Settings` config loader (env vars / `.env`) | -- | `src/lookup_cli/config.py` |
| [ ] **Run `pytest -m cache` and confirm green** | Cache, model | |
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
