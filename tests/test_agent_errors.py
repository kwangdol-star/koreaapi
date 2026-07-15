"""Machine-actionable API errors — the caller is an autonomous agent, not a human on a browser page.
Starlette's default 404/405 are text/plain dead-ends; ours are JSON with the NEXT ACTION (catalog at /,
spec at /openapi.json), so an agent (or an agent spawned by an agent) self-corrects instead of failing."""

from __future__ import annotations

from starlette.testclient import TestClient

from koreaapi.api import app


def test_unknown_endpoint_returns_json_with_next_action():
    r = TestClient(app).get("/v1/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert "/v1/does-not-exist" in body["error"]
    assert "openapi.json" in body["hint"]                      # the self-correcting pointer
    assert any("agents.json" in s for s in body["see"])        # the machine manifest


def test_wrong_method_returns_json_405():
    r = TestClient(app).post("/v1/certified")
    assert r.status_code == 405
    assert "GET" in r.json()["hint"]                            # tells the agent the right verb


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
