import pytest
from typer.testing import CliRunner

from lookup_cli.cli import app

pytestmark = pytest.mark.plugin_framework

runner = CliRunner()


def test_plugins_list_shows_echo_plugin():
    result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "echo" in result.stdout
