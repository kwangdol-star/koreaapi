"""Offline tests for the natural-language router (ask / route).

The router PICKS one Answer Product from free text. It's best-effort: with a key it asks a cheap LLM,
without one (dev/sandbox/CI) it uses a pure keyword fallback — so it ALWAYS routes. The keyword router
and the routing envelope are fully tested; the live LLM path is exercised with an injected fake module
(no network), matching the "grounded/offline" discipline of the rest of the suite.

Run:  PYTHONPATH=src python -m pytest tests/test_route.py -q
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types

from koreaapi import answers


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_fallback_route_is_pure_and_keyword_driven():
    f = answers._fallback_route
    assert f("vegetarian Korean food")["product"] == "food-guide"
    assert f("plan a trip to Jeju")["product"] == "trip-plan"
    assert f("what's trending in kpop right now")["product"] == "trend-radar"
    assert f("artists under HYBE")["product"] == "agency-roster"
    assert f("how do you spell 빈센조")["product"] == "canonical-name"
    assert f("is this citable as fact")["product"] == "fact-check"
    assert f("Bong Joon-ho filmography")["product"] == "person-credits"
    assert f("BTS")["product"] == "identity-resolve"           # default: map the mention to an id
    assert f("채식 가능한 음식")["product"] == "food-guide"      # Korean keyword


def test_route_without_key_uses_keyword_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = answers.route("vegetarian Korean dishes")
    assert r == {"product": "food-guide", "query": "vegetarian Korean dishes", "via": "keyword"}
    assert answers.route("   ") == {"product": None, "query": "", "via": "empty"}


def _fake_anthropic(reply_text: str):
    """A stand-in `anthropic` module whose Anthropic().messages.create(...) returns `reply_text`."""
    mod = types.ModuleType("anthropic")
    block = type("Block", (), {"type": "text", "text": reply_text})()
    msg = type("Msg", (), {"content": [block]})()

    class _Messages:
        def create(self, **kw):
            return msg

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    mod.Anthropic = _Client
    return mod


def test_route_uses_llm_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setitem(sys.modules, "anthropic",
                        _fake_anthropic('Here: {"product": "trip-plan", "query": "Busan"}'))
    assert answers.route("plan a fun day in Busan") == {
        "product": "trip-plan", "query": "Busan", "via": "llm"}


def test_route_falls_back_when_llm_returns_unknown_product(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setitem(sys.modules, "anthropic",
                        _fake_anthropic('{"product": "not-a-real-product", "query": "x"}'))
    # unknown id -> ignore the LLM, use the deterministic keyword router
    r = answers.route("what's trending in kpop")
    assert r["product"] == "trend-radar" and r["via"] == "keyword"


def test_route_falls_back_when_llm_raises(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    broken = types.ModuleType("anthropic")

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("api down")

    broken.Anthropic = _Boom
    monkeypatch.setitem(sys.modules, "anthropic", broken)
    r = answers.route("artists under SM Entertainment")
    assert r["product"] == "agency-roster" and r["via"] == "keyword"


def test_ask_routes_runs_and_annotates(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = asyncio.run(answers.ask("vegetarian Korean dishes", db_path=_tmp_db()))
    assert env["product"] == "food-guide"                       # routed to the right product
    assert env["routed"] == {"from": "vegetarian Korean dishes", "to_product": "food-guide",
                             "query": "vegetarian Korean dishes", "via": "keyword"}


def test_ask_empty_question_errors():
    assert asyncio.run(answers.ask("   ")) == {"error": "question required"}


def test_ask_logs_the_freetext_demand_signal(monkeypatch):
    # Products log their own structured queries; the NL question + where it routed is demand signal the
    # moat would otherwise miss. ask() logs 'ask:<product>:<question>' (best-effort, via service._log).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    logged = []

    async def rec(kind, key, db_path):
        logged.append((kind, key))

    from koreaapi import service
    monkeypatch.setattr(service, "_log", rec)
    asyncio.run(answers.ask("vegetarian Korean dishes", db_path=_tmp_db()))
    assert ("query", "ask:food-guide:vegetarian Korean dishes") in logged


def test_route_system_prompt_lists_every_product():
    sysmsg = answers._route_system()
    for p in answers._PRODUCTS:            # the catalog drives the prompt -> never drifts from _PRODUCTS
        assert p["id"] in sysmsg


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
