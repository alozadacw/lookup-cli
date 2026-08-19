# lookup-cli

Unified, plugin-based CLI for looking up a person's identity/asset footprint
across Okta, Jira, Jamf, ABM (Apple Business Manager), and allwhere -- with
room to add more services without touching core code.

```
lookup-cli lookup jdoe               # aggregate across all installed plugins
lookup-cli okta status jdoe          # single-service subcommand
lookup-cli jira tickets jdoe
lookup-cli plugins list              # see what's installed
```

## Status

Actively built stage-by-stage, TDD-first. See [`docs/STAGES.md`](docs/STAGES.md)
for the full project plan, current stage, and task breakdown. Currently:
**Stage 0 (plugin framework) and Stage 1 (cache/data model) scaffolded.**

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install -e plugins/echo_plugin       # template/reference plugin
cp .env.example .env                      # fill in real creds as you get them

pytest -m plugin_framework                # Stage 0
pytest -m cache                           # Stage 1
lookup-cli plugins list
```

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) -- how the plugin system, cache, and CLI fit together
- [`docs/CONNECTOR_GUIDE.md`](docs/CONNECTOR_GUIDE.md) -- step-by-step guide to adding a new service connector
- [`docs/STAGES.md`](docs/STAGES.md) -- staged project plan, one epic per stage, task-board-ready
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) -- dev workflow, TDD conventions, branching/PR conventions
- [`CLAUDE.md`](CLAUDE.md) -- context file for Claude Code / Claude Cowork
