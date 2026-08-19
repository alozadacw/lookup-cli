"""
Stage 1 acceptance tests: cache & data model.

Run just this stage:  pytest -m cache
"""

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from lookup_cli.cache import Cache
from lookup_cli.models import UnifiedUserRecord
from lookup_cli.plugins.base import ConnectorResult

pytestmark = pytest.mark.cache


@pytest.fixture
def cache(tmp_path):
    return Cache(tmp_path / "test_cache.sqlite3", default_ttl=timedelta(hours=1))


def _result(plugin="okta", identifier="jdoe", **kwargs) -> ConnectorResult:
    return ConnectorResult(plugin_name=plugin, identifier=identifier, **kwargs)


def test_put_then_get_round_trip(cache):
    cache.put(_result(data={"status": "active"}))
    fetched = cache.get("okta", "jdoe")
    assert fetched is not None
    assert fetched.data == {"status": "active"}


def test_get_missing_key_returns_none(cache):
    assert cache.get("okta", "nobody") is None


def test_entry_expires_after_ttl(cache):
    with freeze_time("2026-01-01T00:00:00+00:00"):
        cache.put(_result(data={"status": "active"}))

    with freeze_time("2026-01-01T02:00:00+00:00"):  # 2h later, ttl=1h
        assert cache.get("okta", "jdoe") is None


def test_entry_within_ttl_is_returned(cache):
    with freeze_time("2026-01-01T00:00:00+00:00"):
        cache.put(_result(data={"status": "active"}))

    with freeze_time("2026-01-01T00:30:00+00:00"):  # 30m later, ttl=1h
        assert cache.get("okta", "jdoe") is not None


def test_invalidate_removes_entry(cache):
    cache.put(_result(data={"status": "active"}))
    cache.invalidate("okta", "jdoe")
    assert cache.get("okta", "jdoe") is None


def test_different_plugins_same_identifier_cached_independently(cache):
    cache.put(_result(plugin="okta", identifier="jdoe", data={"status": "active"}))
    cache.put(_result(plugin="jira", identifier="jdoe", data={"tickets": []}))
    assert cache.get("okta", "jdoe").data == {"status": "active"}
    assert cache.get("jira", "jdoe").data == {"tickets": []}


def test_unified_record_merges_multiple_plugin_results():
    okta_result = _result(plugin="okta", data={"status": "active"})
    jamf_result = _result(plugin="jamf", data={}, error="timeout")

    record = UnifiedUserRecord.from_results("jdoe", [okta_result, jamf_result])

    assert record.field_for("okta") == {"status": "active"}
    assert record.field_for("jamf") is None  # errored -> degrades gracefully
    assert record.errors() == {"jamf": "timeout"}


def test_unified_record_missing_plugin_returns_none_not_exception():
    record = UnifiedUserRecord.from_results("jdoe", [])
    assert record.field_for("okta") is None
    assert record.errors() == {}
