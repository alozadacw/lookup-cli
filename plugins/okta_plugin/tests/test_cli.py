"""
Stage 2: the `lookup-cli okta <identifier> [flags]` CLI surface.

Shape decided 2026-09-02: `<service> <person> [what you want]`, with no
noun subcommands. `okta status jdoe` / `okta devices jdoe` were removed --
they cannot coexist with `okta jdoe`, because a person whose login is
literally "status" or "devices" would silently resolve to the subcommand.
Stages 4-6 adopt the same shape.

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
DEVICES_URL = f"{USERS_URL}/{USER_ID}/devices"

CONFIG = PluginConfig({"OKTA_ORG_URL": ORG_URL, "OKTA_API_TOKEN": "not-a-real-token"})
MOCK_CONFIG = PluginConfig({"LOOKUP_CLI_MOCK_OKTA": "1"})

# Pin the terminal width: rich sizes tables to the terminal, so assertions on
# cell contents would otherwise depend on whoever's shell runs the suite.
runner = CliRunner(env={"COLUMNS": "200"})


def _app(config: PluginConfig = CONFIG):
    return build_app({"okta": OktaPlugin(config)})


def _user_payload(status: str = "ACTIVE") -> dict:
    return {
        "id": USER_ID,
        "status": status,
        "statusChanged": "2025-11-02T09:00:00.000Z",
        "lastLogin": "2026-08-20T14:31:00.000Z",
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


def _mock_user(status: str = "ACTIVE"):
    return respx.get(f"{USERS_URL}/jdoe").mock(
        return_value=httpx.Response(200, json=_user_payload(status))
    )


# --- Bare invocation: identifier alone is enough --------------------------------


@respx.mock
def test_identifier_alone_shows_status():
    _mock_user()

    result = runner.invoke(_app(), ["okta", "jdoe"])

    assert result.exit_code == 0
    assert "ACTIVE" in result.stdout


@respx.mock
def test_identifier_alone_does_not_call_the_devices_endpoint():
    _mock_user()
    devices_route = respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[]))

    runner.invoke(_app(), ["okta", "jdoe"])

    assert not devices_route.called


def test_no_identifier_is_a_usage_error():
    result = runner.invoke(_app(), ["okta"])
    assert result.exit_code == 2


@respx.mock
def test_an_email_identifier_works():
    respx.get(f"{USERS_URL}/jdoe%40example.com").mock(
        return_value=httpx.Response(200, json=_user_payload())
    )

    result = runner.invoke(_app(), ["okta", "jdoe@example.com"])

    assert result.exit_code == 0


# --- -s / --status ---------------------------------------------------------------


@respx.mock
def test_explicit_status_flag_matches_the_default():
    _mock_user()
    result = runner.invoke(_app(), ["okta", "jdoe", "-s"])
    assert result.exit_code == 0
    assert "ACTIVE" in result.stdout


@respx.mock
def test_long_status_flag_works():
    _mock_user()
    assert runner.invoke(_app(), ["okta", "jdoe", "--status"]).exit_code == 0


@respx.mock
def test_deactivated_user_is_called_out_in_plain_language():
    """DEPROVISIONED is what the Okta admin UI calls "deactivated"; the raw
    enum alone makes an operator translate it in their head."""
    _mock_user("DEPROVISIONED")

    result = runner.invoke(_app(), ["okta", "jdoe", "-s"])

    assert result.exit_code == 0
    assert "DEPROVISIONED" in result.stdout
    assert "deactivated" in result.stdout.lower()


@respx.mock
def test_suspended_is_distinguished_from_deactivated():
    """Both block login but they are different states, and conflating them
    would mislead someone verifying an offboarding actually completed."""
    _mock_user("SUSPENDED")

    result = runner.invoke(_app(), ["okta", "jdoe", "-s"])

    assert "SUSPENDED" in result.stdout
    assert "deactivated" not in result.stdout.lower()


@respx.mock
def test_active_user_is_not_labelled_deactivated():
    _mock_user("ACTIVE")
    result = runner.invoke(_app(), ["okta", "jdoe"])
    assert "deactivated" not in result.stdout.lower()


@pytest.mark.parametrize("status", ["LOCKED_OUT", "PASSWORD_EXPIRED", "STAGED", "PROVISIONED"])
@respx.mock
def test_other_statuses_are_reported_verbatim(status):
    _mock_user(status)
    result = runner.invoke(_app(), ["okta", "jdoe"])
    assert status in result.stdout


# --- -d / --devices ----------------------------------------------------------------


@respx.mock
def test_devices_flag_shows_devices():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "jdoe", "-d"])

    assert result.exit_code == 0
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_long_devices_flag_works():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "jdoe", "--devices"])

    assert result.exit_code == 0
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_devices_flag_alone_omits_the_status_table():
    """Flags select sections: `-d` means "devices", not "status and devices"."""
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "jdoe", "-d"])

    assert "last_login" not in result.stdout


@respx.mock
def test_no_devices_message():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[]))

    result = runner.invoke(_app(), ["okta", "jdoe", "-d"])

    assert result.exit_code == 0
    assert "No devices" in result.stdout


# --- Combining flags -----------------------------------------------------------------


@respx.mock
def test_both_flags_show_both_sections():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "jdoe", "-s", "-d"])

    assert "last_login" in result.stdout
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_bundled_short_flags_work():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "jdoe", "-sd"])

    assert "last_login" in result.stdout
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_flags_may_precede_the_identifier():
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    result = runner.invoke(_app(), ["okta", "-d", "jdoe"])

    assert result.exit_code == 0
    assert "C02XYZ123ABC" in result.stdout


@respx.mock
def test_both_flags_resolve_the_user_only_once():
    user_route = _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(200, json=[_device_link()]))

    runner.invoke(_app(), ["okta", "jdoe", "-sd"])

    assert user_route.call_count == 1


# --- Failure modes ----------------------------------------------------------------------


@respx.mock
def test_unknown_user_exits_zero_and_makes_no_device_call():
    respx.get(f"{USERS_URL}/ghost").mock(return_value=httpx.Response(404))
    devices_route = respx.get(url__startswith=USERS_URL).mock(return_value=httpx.Response(200, json=[]))

    result = runner.invoke(_app(), ["okta", "ghost", "-d"])

    assert result.exit_code == 0
    assert "No Okta account" in result.stdout
    assert not devices_route.called


@respx.mock
def test_status_failure_exits_non_zero():
    respx.get(f"{USERS_URL}/jdoe").mock(return_value=httpx.Response(503))

    result = runner.invoke(_app(), ["okta", "jdoe"])

    assert result.exit_code == 1


@respx.mock
def test_a_devices_failure_alongside_status_still_shows_the_status():
    """With `-sd` the status is a real answer already on screen; a device-API
    problem degrades that section rather than discarding both."""
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(404))

    result = runner.invoke(_app(), ["okta", "jdoe", "-sd"])

    assert "ACTIVE" in result.stdout
    assert "unavailable" in result.stdout.lower()


@respx.mock
def test_a_devices_failure_alone_exits_non_zero():
    """With only `-d`, devices are the whole answer, so scripts must be able
    to trust the exit code."""
    _mock_user()
    respx.get(DEVICES_URL).mock(return_value=httpx.Response(404))

    result = runner.invoke(_app(), ["okta", "jdoe", "-d"])

    assert result.exit_code == 1


def test_missing_credentials_exit_non_zero_with_an_actionable_message():
    result = runner.invoke(build_app({"okta": OktaPlugin(PluginConfig({}))}), ["okta", "x"])

    assert result.exit_code == 1
    assert "OKTA_ORG_URL" in result.stdout


# --- Help and mock mode ---------------------------------------------------------------------


def test_help_documents_both_flags():
    result = runner.invoke(_app(), ["okta", "--help"])

    for expected in ("-s", "--status", "-d", "--devices"):
        assert expected in result.stdout


def test_help_shows_the_identifier_as_a_direct_argument():
    result = runner.invoke(_app(), ["okta", "--help"])
    assert "identifier" in result.stdout


def test_removed_subcommands_are_gone():
    """`okta status jdoe` used to work. It must now read "status" as the
    identifier, not silently dispatch -- proving the ambiguity is gone."""
    result = runner.invoke(_app(MOCK_CONFIG), ["okta", "status"])

    assert result.exit_code == 0
    assert "status" in result.stdout  # treated as a username


def test_mock_mode_end_to_end():
    result = runner.invoke(_app(MOCK_CONFIG), ["okta", "jdoe", "-sd"])

    assert result.exit_code == 0
    assert "ACTIVE" in result.stdout
    assert "C02MOCK00001" in result.stdout
