from echo_plugin.plugin import EchoStandalonePlugin


def test_fetch_returns_ok_result():
    plugin = EchoStandalonePlugin()
    result = plugin.fetch("jdoe")
    assert result.ok
    assert result.data == {"echoed": "jdoe"}


def test_fetch_wraps_backend_errors_into_error_field(monkeypatch):
    plugin = EchoStandalonePlugin()
    monkeypatch.setattr(
        plugin, "_call_backend", lambda identifier: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    result = plugin.fetch("jdoe")
    assert not result.ok
    assert result.error == "boom"
