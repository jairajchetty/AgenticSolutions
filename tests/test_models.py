import json
import runpy

import pytest
from starlette.requests import Request

from agentic_solutions.web import models
from agentic_solutions.web.config import Settings
from agentic_solutions.web.models import (
    DEFAULT_ENTRIES, OFFLINE, ModelEntry, credential_set, entry_for, listed_entries,
    load_entries, may_choose_model)


def make_scope(client="127.0.0.1", host="127.0.0.1:8000", origin=None, method="GET",
               server=("127.0.0.1", 8000), extra=()):
    headers = []
    if host is not None:
        headers.append((b"host", host.encode()))
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    headers += [(k.encode(), v.encode()) for k, v in extra]
    return {"type": "http", "method": method, "headers": headers, "path": "/", "query_string": b"",
            "client": (client, 5000) if client else None, "server": server}


def make_request(**kwargs):
    return Request(make_scope(**kwargs))


def test_defaults_and_env_override():
    assert load_entries(None) == DEFAULT_ENTRIES
    assert load_entries("") == DEFAULT_ENTRIES
    assert [e.id for e in DEFAULT_ENTRIES] == ["claude-haiku", "deepseek"]
    assert DEFAULT_ENTRIES[0] == ModelEntry("claude-haiku", "Claude Haiku 5.5", "anthropic", "claude-haiku-5-5")
    assert OFFLINE == ModelEntry("offline", "Offline (scripted)", "offline", "")
    raw = json.dumps([{"id": "x", "label": "X", "provider": "openrouter", "model": "a/b"}])
    assert load_entries(raw) == (ModelEntry("x", "X", "openrouter", "a/b"),)
    s = Settings.from_env()
    assert (s.host, s.port, s.openrouter_zdr, s.studio_models) == ("127.0.0.1", 8000, False, None)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("OPENROUTER_ZDR", "Yes")
    monkeypatch.setenv("STUDIO_MODELS", "[]")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.test")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "Studio")
    s = Settings.from_env()
    assert (s.host, s.port, s.openrouter_zdr, s.studio_models) == ("0.0.0.0", 9001, True, "[]")
    assert (s.openrouter_site_url, s.openrouter_app_title) == ("https://example.test", "Studio")
    monkeypatch.setenv("OPENROUTER_ZDR", "0")
    assert Settings.from_env().openrouter_zdr is False


GOOD = {"id": "x", "label": "X", "provider": "anthropic", "model": "m"}


@pytest.mark.parametrize("raw", [
    "{not json",
    json.dumps([{"id": "x", "label": "X", "provider": "anthropic"}]),
    json.dumps([GOOD, GOOD]),
    json.dumps([{**GOOD, "id": "offline"}]),
    json.dumps([{**GOOD, "provider": "openai"}]),
])
def test_bad_studio_models_fail_clearly(raw):
    with pytest.raises(ValueError) as e:
        load_entries(raw)
    assert str(e.value)


def test_listed_only_with_credential():
    a, o = DEFAULT_ENTRIES
    assert credential_set(a, {"ANTHROPIC_API_KEY": "k"})
    assert not credential_set(a, {"ANTHROPIC_API_KEY": "  "})
    assert not credential_set(o, {"ANTHROPIC_API_KEY": "k"})
    assert listed_entries(DEFAULT_ENTRIES, {}) == (OFFLINE,)
    assert listed_entries(DEFAULT_ENTRIES, {"OPENROUTER_API_KEY": "k"}) == (OFFLINE, o)
    both = {"ANTHROPIC_API_KEY": "k", "OPENROUTER_API_KEY": "k"}
    assert listed_entries(DEFAULT_ENTRIES, both) == (OFFLINE, a, o)
    assert entry_for(DEFAULT_ENTRIES, "deepseek") == o
    assert entry_for(DEFAULT_ENTRIES, "nope") is None
    assert models.MODEL_CHOICE_DENIED == "model choice is not available"
    assert models.UNKNOWN_MODEL == "unknown model"


@pytest.mark.parametrize("bind,kwargs,expected", [
    ("127.0.0.1", {}, True),
    ("0.0.0.0", {}, False),
    ("::1", {"client": "::1", "host": "[::1]:8000"}, True),
    ("localhost", {"host": "localhost"}, True),
    ("127.0.0.1", {"client": "10.0.0.5"}, False),
    ("127.0.0.1", {"client": None}, False),
    ("127.0.0.1", {"host": "evil.example:8000"}, False),
    ("127.0.0.1", {"host": None}, False),
    ("127.0.0.1", {"host": "[::1]:8000"}, True),
    ("127.0.0.1", {"host": "[::1]"}, True),
    ("127.0.0.1", {"host": "[::2]:8000"}, False),
    ("127.0.0.1", {"host": "localhost.evil.example"}, False),
    ("127.0.0.1", {"method": "POST", "origin": "https://evil.example"}, False),
    ("127.0.0.1", {"method": "POST", "origin": "http://127.0.0.1:8000"}, True),
    ("127.0.0.1", {"method": "POST", "origin": "http://127.0.0.1:9999"}, False),
    ("127.0.0.1", {"method": "POST", "origin": "null"}, False),
    ("127.0.0.1", {"method": "POST", "origin": "ftp://127.0.0.1:8000"}, False),
    ("127.0.0.1", {"method": "GET", "origin": "https://evil.example"}, True),
    ("127.0.0.1", {"method": "GET"}, True),
    ("::1", {"client": "::1", "host": "[::1]:8000", "server": ("::1", 8000)}, True),
    ("127.0.0.1", {"server": ("10.0.0.2", 8000)}, False),       # the socket is not on loopback
    ("127.0.0.1", {"server": None}, False),                     # e.g. a unix socket behind a proxy
    ("127.0.0.1", {"extra": [("forwarded", "for=127.0.0.1")]}, False),
    ("127.0.0.1", {"extra": [("x-forwarded-for", "127.0.0.1")]}, False),
    ("127.0.0.1", {"extra": [("x-forwarded-host", "localhost")]}, False),
    ("127.0.0.1", {"extra": [("x-real-ip", "127.0.0.1")]}, False),
    ("127.0.0.1", {"extra": [("x-forwarded-for", "")]}, False),  # present at all is enough
])
def test_check_true_only_all_loopback(bind, kwargs, expected):
    assert may_choose_model(make_request(**kwargs), Settings(host=bind)) is expected


@pytest.mark.anyio
async def test_spoofed_forwarded_for_through_uvicorn_proxy_middleware_is_denied():
    """With FORWARDED_ALLOW_IPS=*, uvicorn rewrites the peer from X-Forwarded-For.

    A LAN client claiming to be 127.0.0.1 then looks like a loopback peer; the
    check must still say no, because the forwarded header is present.
    """
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope["client"]
        seen["allowed"] = may_choose_model(Request(scope), Settings(host="127.0.0.1"))

    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="*")
    scope = make_scope(client="10.0.0.5", host="localhost", extra=[("x-forwarded-for", "127.0.0.1")])
    await wrapped(scope, None, None)
    assert seen["client"][0] == "127.0.0.1"                     # the middleware did rewrite the peer
    assert seen["allowed"] is False


def test_main_uses_settings_host_port(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8123")
    runpy.run_module("agentic_solutions.web", run_name="__main__")
    (args, kwargs), = calls
    assert args == ("agentic_solutions.web.app:create_app",)
    assert kwargs["host"] == "127.0.0.1" and kwargs["port"] == 8123 and kwargs["workers"] == 1
    assert kwargs["proxy_headers"] is False                     # never rewrite the peer from headers
