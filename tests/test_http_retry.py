"""The live pull fires hundreds of Wikidata/Wikipedia calls at ~100 entities; Wikimedia throttling
(HTTP 429/503) used to silently drop the TAIL of the roster (dramas/films sort last). `_http_get_json`
must back off and retry so a transient throttle never fails an entity. Offline (urlopen + sleep mocked).
"""

from __future__ import annotations

import urllib.error

from koreaapi.sources import wikidata


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:  # first call throttled
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests",
                                         {"Retry-After": "0"}, None)
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr(wikidata.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(wikidata.time, "sleep", lambda s: None)  # don't actually wait
    out = wikidata._http_get_json("https://www.wikidata.org/x", {"User-Agent": "t"})
    assert out == {"ok": True}
    assert calls["n"] == 2  # retried exactly once after the 429


def test_gives_up_after_attempts_and_raises(monkeypatch):
    def always_429(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "0"}, None)

    monkeypatch.setattr(wikidata.urllib.request, "urlopen", always_429)
    monkeypatch.setattr(wikidata.time, "sleep", lambda s: None)
    try:
        wikidata._http_get_json("https://x", {"User-Agent": "t"}, attempts=3)
    except urllib.error.HTTPError as e:
        assert e.code == 429
    else:
        raise AssertionError("expected HTTPError after exhausting retries")


def test_retries_on_transient_urlerror(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("temporary network blip")
        return _Resp(b'{"v": 1}')

    monkeypatch.setattr(wikidata.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(wikidata.time, "sleep", lambda s: None)
    assert wikidata._http_get_json("https://x", {"User-Agent": "t"}) == {"v": 1}


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
