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
| [x] Set up CI (GitHub Actions) running `pytest` on every PR | above | `.github/workflows/tests.yml` confirmed green on the first real run (2026-08-19, Python 3.11, 43s): 13 passed, 87% coverage -- byte-identical to the local 3.14 run (152 stmts / 20 miss), which lowers the version-skew concern in the decisions log |
| [x] Fix `testpaths` so per-plugin test suites are collected | above | Fixed 2026-08-25. `testpaths = ["tests", "plugins"]` plus `--import-mode=importlib`. The import mode is required, not cosmetic: root `tests/` and every `plugins/*/tests/` are both packages named `tests`, which collide under pytest's default prepend mode (`ModuleNotFoundError: No module named 'tests.test_plugin'`). Also added `--strict-markers`, and gave `echo_plugin`'s tests a `pytestmark` so `pytest -m <stage>` covers plugin packages too. Bootstrap's separate per-plugin loop is now redundant and was removed |
| [x] Fix plugin-vs-plugin test shadowing | above | **The above fix was incomplete and looked complete with only one plugin installed.** Adding `okta_plugin` revealed that two `plugins/*/tests/` packages both resolve to the module name `tests.test_plugin`, so one silently shadowed the other: collection reported 102 tests when there were 122, and 20 tests stopped running while the suite still went green. Fixed by deleting `__init__.py` from every plugin `tests/` directory — importlib mode then derives a unique module name per file. `tests/unit/framework/test_plugin_test_layout.py` fails the build if one is re-added, and `CONNECTOR_GUIDE.md` §3 warns against it. Worth remembering as a pattern: a collection bug hides itself, because the tests that would fail are the ones not running |
| [x] Make `fetch()` async | ABC | Done 2026-08-25 per the decision below. `base.py`, both echo plugins, and their tests converted; `pytest-asyncio` added with `asyncio_mode = "auto"` |
| [x] Inject credentials via `PluginConfig` instead of per-plugin `os.getenv` | ABC, registry | Done 2026-08-25 per the decision below. New `src/lookup_cli/plugins/config.py`; `discover_plugins(config)` injects; `required_credentials` + `mock_mode` + `configured` on the base class; `plugins list` gained a status column. The registry raises an actionable `PluginLoadError` if a plugin overrides `__init__` without calling `super().__init__(config)` |
| [x] Route connector errors through a scrubbing helper | ABC | Added 2026-08-25. `src/lookup_cli/redaction.py::safe_error()`. Rule 4 of the contract turns every ordinary failure into `ConnectorResult(error=str(exc))`, which `Cache.put()` then writes to SQLite and the CLI prints -- so an httpx exception carrying a URL or auth header became a durable plaintext credential. Redacts `Bearer`/`SSWS`/`Basic` credentials, URL userinfo, secret query params, JWTs, and the literal values of secret-named env vars. The `echo_plugin` template now models the pattern; every connector must follow it |

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
| [x] Write tests for `Settings` config loader | Settings | Done 2026-08-25 -- `tests/unit/config/test_settings.py`, `config.py` 0% -> 100%. Covers defaults, env-var override, `.env` fallback, env-beats-`.env` precedence, `Path` coercion, validation failure, and that unprefixed service creds (`OKTA_*`/`JIRA_*`) are ignored rather than absorbed. Note for future tests: `Settings` reads `.env` relative to **cwd**, so any test touching it must `chdir` to a tmp dir or it silently picks up the repo's real `.env` |
| [x] Cache retention: expiry must delete, not just hide | Cache | Done 2026-08-25. `get()` past TTL previously returned `None` but left the row on disk forever -- the cache holds employee PII (status, serials, ticket history) in plaintext. `get()` now deletes on expiry; added `purge_expired()` and `clear()`, plus `lookup-cli cache path\|clear\|purge`. DB is created `0600` inside a `0700` directory |
| [x] Fix `~` not being expanded in `cache_db_path` | Settings | Found 2026-08-25 while smoke-testing `lookup-cli cache path`. `.env.example` ships `LOOKUP_CLI_CACHE_DB_PATH=~/.lookup-cli/cache.sqlite3`; pydantic coerced that to `Path("~/...")` verbatim, so the cache was created at `./~/.lookup-cli/cache.sqlite3` — a plaintext store of employee PII **inside the git checkout** rather than in `$HOME`. Latent since Stage 1; nothing called `get_settings()` until now. Fixed with a `field_validator` calling `.expanduser()` |
| [ ] Decide & document per-plugin default TTLs (Okta status probably shorter than, say, ABM device assignment) | none yet -- open decision | add to `docs/ARCHITECTURE.md` once decided |

**Stage 1 is done when:** `pytest -m cache` passes, and cache/model
behavior is exercised by at least one real plugin in Stage 2.

---

## Stage 2 -- Okta Connector (real API, credentials available)
**Status: mocks green** -- `pytest -m okta` 23 passed, 2026-08-25. The
manual smoke test against the real org is still outstanding (blocked on a
real token in `.env`).

| Task | Depends on |
|---|---|
| [x] Write mocked-response tests: active, suspended, deprovisioned, not-found, timeout/5xx | Stage 0 |
| [x] Implement `okta_plugin` package (copy `echo_plugin` template) | tests above |
| [x] Implement real Okta API client (`GET /api/v1/users/{login}`) behind `_call_backend` | tests above |
| [x] `lookup-cli okta status <user>` subcommand | plugin implemented |
| [x] Add `OKTA_ORG_URL` / `OKTA_API_TOKEN` to `.env.example` | plugin implemented |
| [ ] **Confirm a real token works in a manual smoke test** | a real token in `.env` |
| [x] Add `okta` marker to `pyproject.toml` pytest markers | -- |
| [x] `okta status <user> -d/--devices` — devices registered to a user | plugin implemented |

Notes from the implementation:

- **Not-found is a success, not an error.** `GET` returning 404 yields
  `data={"found": False}` with `ok is True`, not `error=`. The guide asks
  each connector to decide this explicitly: for an offboarding lookup "this
  person has no Okta account" is a real answer, whereas an `error=` makes
  `UnifiedUserRecord.field_for("okta")` return None -- indistinguishable
  from "Okta was unreachable".
- **The identifier is URL-encoded** (`quote(safe="")`). It is user input; an
  email's `@` must keep working while `../` must not walk off
  `/api/v1/users`. Covered by a test.
- **Requests are timeout-bounded** (`OKTA_TIMEOUT_SECONDS`, default 10), so a
  hanging service can't hang the whole aggregate.
- **Mock mode works with zero credentials** (`LOOKUP_CLI_MOCK_OKTA=1`), so the
  CLI can be demoed before a token is provisioned.
- **`-d` lists devices** via `GET /api/v1/users/{userId}/devices`, kept out of
  `fetch()` deliberately: Stage 7 runs `fetch()` for every plugin on every
  lookup and must not pay for a second round trip nobody asked for. `status -d`
  reuses the id it already resolved, so it costs two calls, not three. Link-header
  pagination is followed, bounded at 20 pages so a looping `next` can't hang.
  A device-API failure degrades only that section — the account status still
  prints.
  - **Scope caveat to keep repeating to users:** this is Okta's own device
    registry (Okta Verify / device trust), *not* hardware inventory. Someone can
    hold a laptop Okta has never seen. Jamf (Stage 4) and ABM (Stage 5) are the
    authoritative inventory sources, and once they exist the three views will
    disagree — that disagreement is itself useful for offboarding, but the CLI
    should never present Okta's list as "the devices this person has".

**Done when:** `pytest -m okta` green on mocks *(done)*, and one manual
`lookup-cli okta status <realuser>` against real Okta returns a sane result
*(pending)*.

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
- [x] ~~`fetch()` sync vs. async~~ **Resolved 2026-08-25: async.** Done before
      the first real connector, while the cost was one template plugin rather
      than five. `ConnectorPlugin.fetch()` is `async def`; Stage 7 will gather
      with `asyncio.gather`, so a lookup costs the slowest service rather than
      the sum of all five. `pytest-asyncio` with `asyncio_mode = "auto"` means
      connector authors write plain `async def test_...` with no decorator.
      A regression test asserts `inspect.iscoroutinefunction(plugin.fetch)`.
- [x] ~~How plugins receive credentials~~ **Resolved 2026-08-25: inject a
      `PluginConfig`.** See `src/lookup_cli/plugins/config.py`. Core builds one
      config (merging `.env` and the process environment, environment winning)
      and passes it to every plugin at discovery. Plugins declare
      `required_credentials`; `plugins list` now shows configured / mock /
      missing-and-which. `mock_mode` is built into the base class following the
      existing `LOOKUP_CLI_MOCK_<PLUGIN>` convention. Non-obvious payoff:
      `bootstrap.sh` writes credentials to `.env` and nothing exports them, so
      plugins reading only `os.environ` would have seen nothing after a
      developer followed the README.
- [ ] **Okta token: personal read-only token vs. dedicated service account
      (Stage 2).** Decided 2026-08-25 to start with a personal read-only API
      token to unblock development. Okta SSWS tokens act as the creating user
      and inherit their permissions, and they expire after ~30 days of
      inactivity -- so before this tool goes to more than one operator, swap
      to a dedicated service account with a read-only admin role and a named
      rotation owner. Revisit at Stage 8, and do not skip it at rollout.
- [ ] **Audit logging (Stage 7).** Nothing records who looked up whom. A tool
      that queries HR/IT systems about named employees will likely need that
      for compliance, and the aggregator is the natural choke point -- much
      cheaper to add while Stage 7 is being written than afterwards.
- [ ] **Authorization model (out of scope for v1?).** The CLI has whatever its
      tokens have: anyone who can run it can read every user in Okta/Jira.
      Probably acceptable for a small IT team, but state it as an explicit
      scope boundary rather than leaving it implicit.
- [x] ~~Whether CLI subcommands for each plugin live in that plugin's own
      package or stay centralized in `src/lookup_cli/cli.py`~~ **Resolved
      2026-08-25: in the plugin package.** Forced by Stage 2 -- adding
      `lookup-cli okta status` to core `cli.py` would have broken ground rule
      2 for every future connector, and falsified the Stage 8 claim before
      Stage 8 ran. `ConnectorPlugin.cli()` returns an optional `typer.Typer`
      and `build_app()` mounts it under the plugin's name. One generic core
      change, made deliberately and flagged, so no connector edits core again.
      `okta_plugin` was built with **zero** edits to `src/lookup_cli/` beyond
      that hook.
- [x] ~~Supported Python versions (Stage 0)~~ **Resolved 2026-08-25:** CI now
      runs a `["3.11", "3.13"]` matrix, so the floor declared by
      `requires-python` and the version developers actually use are both
      covered. 3.13 chosen over 3.14 as the local standard because it is
      available as a stock Homebrew formula. Evidence the skew was benign:
      the 3.13 run reported the same `152 stmts / 20 miss` as the earlier
      3.14 run.
- [x] ~~Whether `plugins/*/tests` should be collected by the root `pytest`
      run (Stage 0)~~ **Resolved 2026-08-25:** yes, via
      `testpaths = ["tests", "plugins"]` + `--import-mode=importlib`. See the
      Stage 0 task row for why the import mode is mandatory.
- [ ] Which stage marker cross-cutting core utilities belong to.
      `test_redaction.py` was filed under `plugin_framework` because error
      handling is part of the plugin contract in `base.py`, but it is not
      registry/discovery. If more core utilities land, consider a
      `core`/`security` marker instead of stretching `plugin_framework`.
