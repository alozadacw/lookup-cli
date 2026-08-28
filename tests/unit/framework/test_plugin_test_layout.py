"""
Guards the plugin test-collection layout.

History: `testpaths` originally excluded `plugins`, so connector tests ran
nowhere. Adding `plugins` to `testpaths` needed `--import-mode=importlib`,
because root `tests/` and `plugins/*/tests/` are both packages named
`tests`. That fix looked complete with one plugin installed -- and broke
again the moment a second connector arrived: two `plugins/*/tests/`
packages both resolve to the module name `tests.test_plugin`, so one
silently shadowed the other and 20 tests stopped running while the suite
still reported green.

The fix is that a plugin's `tests/` directory must NOT be a package.
Without `__init__.py`, importlib mode derives a unique module name from
each file's path. This test fails loudly if anyone re-adds one.

Run just this stage:  pytest -m plugin_framework
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.plugin_framework

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLUGINS_DIR = _REPO_ROOT / "plugins"


def _plugin_test_dirs() -> list[Path]:
    return sorted(p for p in _PLUGINS_DIR.glob("*/tests") if p.is_dir())


def test_the_plugins_directory_is_where_we_think_it_is():
    """Keeps the guard below honest if the repo is ever restructured."""
    assert _PLUGINS_DIR.is_dir()
    assert _plugin_test_dirs(), "expected at least one plugin package with tests"


@pytest.mark.parametrize("tests_dir", _plugin_test_dirs(), ids=lambda p: p.parent.name)
def test_plugin_tests_directory_is_not_a_package(tests_dir: Path):
    init_file = tests_dir / "__init__.py"
    assert not init_file.exists(), (
        f"{init_file.relative_to(_REPO_ROOT)} makes this directory a package named "
        f"'tests', colliding with every other plugin's tests package under "
        f"--import-mode=importlib. Delete it; pytest does not need it."
    )
