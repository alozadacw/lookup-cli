from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from lookup_cli.plugins.registry import PluginLoadError, discover_plugins

app = typer.Typer(help="Unified lookup across Okta, Jira, Jamf, ABM, allwhere, and more.")
plugins_app = typer.Typer(help="Inspect installed connector plugins.")
app.add_typer(plugins_app, name="plugins")

console = Console()


@plugins_app.command("list")
def list_plugins() -> None:
    """List every connector plugin currently discoverable via entry points."""
    try:
        plugins = discover_plugins()
    except PluginLoadError as exc:
        console.print(f"[red]Plugin load error:[/red] {exc}")
        raise typer.Exit(code=1)

    table = Table(title="Installed connector plugins")
    table.add_column("name")
    table.add_column("class")
    for name, plugin in sorted(plugins.items()):
        table.add_row(name, type(plugin).__qualname__)
    console.print(table)


if __name__ == "__main__":
    app()
