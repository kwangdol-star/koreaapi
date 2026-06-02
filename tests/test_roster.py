"""Offline test: uncurated roster artists resolve via live search + are identity-guarded.

Roster (non-curated) artists have NO hardcoded Q-id - the id is resolved live via
wbsearchentities on the open network (GitHub runners). Here the HTTP is monkeypatched. The
fetched name is checked against the roster's canonical name, so a wrong resolution is
rejected (graceful degradation), never ingested - the same guard that caught 'Arborka'.

Run:  PYTHONPATH=src python -m pytest tests/test_roster.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from koreaapi.roster import ARTISTS
from koreaapi.sources.wikidata import WikidataSource, _QID


def _fake_http_get(entity_q: str, en: str, ko: str | None = None):
    """Return a search hit then a labels response, regardless of which URL is requested."""

    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": entity_q}]}
        labels = {"en": {"language": "en", "value": en}}
        if ko:
            labels["ko"] = {"language": "ko", "value": ko}
        return {"entities": {entity_q: {"id": entity_q, "labels": labels}}}

    return http_get


def test_roster_has_extras_beyond_the_curated_qids():
    # the extras are roster-only (no hardcoded Q-id) -> resolved live
    assert "artist:blackpink" in ARTISTS and "artist:blackpink" not in _QID


def test_roster_artist_resolves_via_search_and_passes_guard(monkeypatch):
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q24987224", "BLACKPINK", "블랙핑크"))
    res = asyncio.run(WikidataSource().fetch("artist:blackpink", "facts"))
    assert res["payload"]["name_en_official"] == "BLACKPINK"
    assert res["payload"]["name_ko"] == "블랙핑크"
    assert res["citation"].startswith("Wikidata Q24987224")  # id came from live search


def test_roster_artist_wrong_resolution_is_rejected(monkeypatch):
    # search resolves to an entity whose name is NOT blackpink -> identity guard rejects it
    monkeypatch.setattr(WikidataSource, "_http_get", _fake_http_get("Q999", "Some Other Thing"))
    with pytest.raises(ValueError, match="identity mismatch"):
        asyncio.run(WikidataSource().fetch("artist:blackpink", "facts"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
