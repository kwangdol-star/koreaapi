"""Korean-search fallback for Korean-labeled-only Wikidata items (유성온천, 샤롯데씨어터 …): the English
wbsearchentities pass can't see them, so resolve_candidates ALSO searches language=ko with the roster's
SEARCH_KO term, and that Korean name joins the expected identity (otherwise a ko-only item fails the
overlap guard even when found). Every candidate still walks the type + identity guards — a wrong term
degrades to a miss, never a wrong record. Offline via an injected _http_get."""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.roster import NAMES, SEARCH_KO
from koreaapi.sources.wikidata import WikidataSource


def test_search_url_is_language_parameterized():
    src = WikidataSource()
    assert "language=en" in src._search_url("Yuseong Hot Springs")
    ko = src._search_url("유성온천", "ko")
    assert "language=ko" in ko and "uselang=ko" in ko


def test_resolve_candidates_falls_back_to_korean_search(monkeypatch):
    src = WikidataSource()
    calls = []

    def fake_get(url):
        calls.append(url)
        if "language=ko" in url:
            return {"search": [{"id": "Q555"}]}
        return {"search": []}                      # the English search sees nothing (ko-only item)

    monkeypatch.setattr(src, "_http_get", fake_get)
    qids = asyncio.run(src.resolve_candidates("hotspring:yuseong"))
    assert qids == ["Q555"]                        # found via the Korean pass
    assert any("language=ko" in u for u in calls) and any("language=en" in u for u in calls)


def test_resolve_candidates_merges_and_dedups_both_passes(monkeypatch):
    src = WikidataSource()

    def fake_get(url):
        if "language=ko" in url:
            return {"search": [{"id": "Q1"}, {"id": "Q2"}]}   # Q1 duplicates the EN hit
        return {"search": [{"id": "Q1"}]}

    monkeypatch.setattr(src, "_http_get", fake_get)
    assert asyncio.run(src.resolve_candidates("beach:hyeopjae")) == ["Q1", "Q2"]


def test_no_match_error_names_both_terms(monkeypatch):
    src = WikidataSource()
    monkeypatch.setattr(src, "_http_get", lambda url: {"search": []})
    with pytest.raises(ValueError, match="을왕리해수욕장"):
        asyncio.run(src.resolve_candidates("beach:eurwangni"))


def test_expected_identity_includes_the_korean_name(monkeypatch):
    # A ko-labeled-only item must pass the overlap guard: fetch()'s expected identity now carries the
    # SEARCH_KO name. Drive fetch end-to-end with injected HTTP: search (en empty, ko hit) + entity.
    src = WikidataSource()

    def fake_get(url):
        if "wbsearchentities" in url:
            return {"search": [{"id": "Q555"}]} if "language=ko" in url else {"search": []}
        # wbgetentities: a Korean-labeled-only 온천 item (no English label at all)
        return {"entities": {"Q555": {
            "labels": {"ko": {"value": "유성온천"}},
            "claims": {},
        }}}

    monkeypatch.setattr(src, "_http_get", fake_get)
    out = asyncio.run(src.fetch("hotspring:yuseong", "facts"))
    assert out["payload"]["name_ko"] == "유성온천"           # accepted — overlap satisfied by the ko name
    assert "Q555" in out["citation"]


def test_search_ko_entries_are_hangul_seed_terms():
    assert set(SEARCH_KO) <= set(NAMES)                      # every ko term belongs to a real seed
    assert all(any("가" <= ch <= "힣" for ch in v) for v in SEARCH_KO.values())  # real Hangul
    assert len(set(SEARCH_KO.values())) == len(SEARCH_KO)    # no duplicate terms


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
