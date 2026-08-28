"""
Stage 2: the `lookup-cli okta ...` CLI surface.

Driven through the real core app via `build_app`, so these also prove the
plugin's sub-app is mounted the way a user would actually reach it.

Run just this stage:  pytest -m okta
"""

from __future__ import annotations

import httpx
import pytest
import respx
from okta_plugin.plugin import OktaPlugin
from typer.testing import CliRunner

from lookup_cli.cli import build_app
from lookup_cli.plugins.config import PluginConfig

pytestmark = pytest.mark.okta

ORG_URL = "https://acme.okta.com"
USERS_URL = f"{ORG_URL}/api/v1/users"
USER_ID = "00u1abcdefGHIJKLmno7"

CONFIG = PluginConfig({"OKTA_ORG_URL": ORG_URL, "OKTA_API_TOKEN": "not-a-real-token"})
MOCK_CONFIG = PluginConfig({"LOOKUP_CLI_MOCK_OKTA": "1"})

# Pin the terminal width: rich sizes tables to the terminal, so assertions on
# cell contents would otherwise depend on whoever's shell is running the suite.
runner = CliRunner(env={"COLUMNS": "200"})


def _app(config: PluginConfig = CONFIG):
    return build_app({"okta": OktaPlugin(config)})


def _user_payload() -> dict:
    return {
        "id": USER_ID,
        "status": "ACTIVE",
        "profile": {"login": "jdoe", "email": "jdoe@example.com", "firstName": "Jane"},
    }


def _device_link(serial: str = "C02XYZ123ABC", name: str = "Jane's MacBook Pro") -> dict:
    return {
        "id": "guo1",
        "managementStatus": "MANAGED",
        "device": {
            "id": "guo1",
            "status": "ACTIVE",
            "profile": {
                "displayName": name,
                "platform": "MACOS",
                "model": "MacBookPro18,3",
                "osVersion": "15.6.0",
                "serialNumber": serial,
            },
        },
    }


# --- status (no flag) ------------------------------------------------------------


@respx.mock
def test_status_without_the_flag_shows_no_devices_section():
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(200, json=_user_payload()))
    devices_route = respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(
        return_value=httpx.Response(200, json=[])
    )

    result = runner.invoke(_app(), ["okta", "status", "jdoe"])

    assert result.exit_code == 0
    assert not devices_route.called
    assert "Devices" not in result.stdout


# --- status -d / --devices --------------------------------------------------------


@respx.mock
def test_short_flag_lists_devices():
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(200, json=_user_payload()))
    respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(
        return_value=httpx.Response(200, json=[_device_link()])
    )

    result = runner.invoke(_app(), ["okta", "status", "jdoe", "-d"])

    assert result.exit_code == 0
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_long_flag_is_equivalent():
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(200, json=_user_payload()))
    respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(
        return_value=httpx.Response(200, json=[_device_link()])
    )

    result = runner.invoke(_app(), ["okta", "status", "jdoe", "--devices"])

    assert result.exit_code == 0
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_devices_flag_reuses_the_id_from_the_status_lookup():
    """One user lookup, not two."""
    user_route = respx.get(f"{USERS_URL}/jdoe").mock(
        return_value=httpx.Response(200, json=_user_payload())
    )
    respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(
        return_value=httpx.Response(200, json=[_device_link()])
    )

    runner.invoke(_app(), ["okta", "status", "jdoe", "-d"])

    assert user_route.call_count == 1


@respx.mock
def test_user_with_no_devices_says_so_and_still_exits_zero():
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(200, json=_user_payload()))
    respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(return_value=httpx.Response(200, json=[]))

    result = runner.invoke(_app(), ["okta", "status", "jdoe", "-d"])

    assert result.exit_code == 0
    assert "No devices" in result.stdout


@respx.mock
def test_a_devices_failure_does_not_discard_the_account_status():
    """The status is the primary answer; a device-API problem degrades that
    one section rather than failing the whole command."""
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(200, json=_user_payload()))
    respx.get(f"{USERS_URL}/{USER_ID}/devices").mock(return_value=httpx.Response(404))

    result = runner.invoke(_app(), ["okta", "status", "jdoe", "-d"])

    assert "ACTIVE" in result.stdout, "account status must still be shown"
    assert "devices" in result.stdout.lower()


@respx.mock
def test_unknown_user_with_devices_flag_exits_zero_without_a_device_call():
    respx.get(f"{USERS_URL}/ghost").mock(return_value=httpx.Response(404))

    result = runner.invoke(_app(), ["okta", "status", "ghost", "-d"])

    assert result.exit_code == 0
    assert "No Okta account" in result.stdout


def test_missing_credentials_exit_non_zero_with_an_actionable_message():
    result = runner.invoke(build_app({"okta": OktaPlugin(PluginConfig({}))}), ["okta", "status", "x"])

    assert result.exit_code == 1
    assert "OKTA_ORG_URL" in result.stdout


def test_mock_mode_end_to_end_with_devices():
    result = runner.invoke(_app(MOCK_CONFIG), ["okta", "status", "jdoe", "-d"])

    assert result.exit_code == 0
    assert "ACTIVE" in result.stdout


def test_help_documents_the_devices_flag():
    result = runner.invoke(_app(), ["okta", "status", "--help"])

    assert "-d" in result.stdout
    assert "--devices" in result.stdout
