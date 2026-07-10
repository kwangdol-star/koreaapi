"""Cross-vertical TYPE guard — the 'Sweet Home' lesson. The 1989 Capcom GAME and the webtoon share
the bilingual name ('Sweet Home' / 스위트(‌ )홈), so the name guards pass and the game's facts
(1989-12-15, Capcom, RPG) poisoned the webtoon record. The entity's own P31 typing is the tell:
positively typed as another vertical's class -> rejected, and fetch() walks to the next search
candidate (self-healing: the real webtoon wins). Fail-open on untyped items (name guard still applies).
"""

from __future__ import annotations

import asyncio

from koreaapi.sources.wikidata import WikidataSource, _alien_class, p31_of


def _ent(qid: str, en: str, ko: str | None = None, p31: list[str] = ()) -> dict:
    labels: dict = {"en": {"value": en}}
    if ko:
        labels["ko"] = {"value": ko}
    return {"entities": {qid: {"id": qid, "labels": labels, "claims": {
        "P31": [{"mainsnak": {"datavalue": {"value": {"id": c}}}} for c in p31]}}}}


def test_alien_class_logic():
    assert _alien_class("webtoon", {"Q7889"}) == "Q7889"             # game class on a webtoon -> alien
    assert _alien_class("webtoon", {"Q5398426"}) == "Q5398426"       # ...and the drama adaptation too
    assert _alien_class("animation", {"Q11424", "Q202866"}) is None  # own class wins outright
    assert _alien_class("animation", {"Q11424"}) is None             # film is ADJACENT to animation
    assert _alien_class("sports", {"Q5"}) is None                    # human is universal (never alien)
    assert _alien_class("fashion", {"Q431289"}) is None              # fashion houses ARE brands
    assert _alien_class("drama", set()) is None                      # untyped -> fail-open
    assert _alien_class("song", {"Q7889"}) == "Q7889"                # a game is not a song
    assert _alien_class("museum", {"Q33506"}) is None                # a museum IS a place (Q33506 ∈ place) — not alien
    assert _alien_class("museum", {"Q570116"}) is None               # ...a museum typed as a tourist attraction too
    assert _alien_class("museum", {"Q7889"}) == "Q7889"              # ...but a game is still alien to a museum
    assert _alien_class("temple", {"Q44539"}) is None                # a temple IS a place (Q44539 ∈ place) — not alien
    assert _alien_class("temple", {"Q7889"}) == "Q7889"              # ...but a game is still alien to a temple
    assert _alien_class("venue", {"Q570116"}) is None                # a stadium tagged as an attraction — not alien
    assert _alien_class("venue", {"Q7889"}) == "Q7889"               # ...but a game is still alien to a venue
    assert _alien_class("airport", {"Q570116"}) is None              # an airport tagged as an attraction — not alien
    assert _alien_class("airport", {"Q7889"}) == "Q7889"             # ...but a game is still alien to an airport


def test_p31_extraction():
    raw = _ent("Q1", "Sweet Home", p31=["Q7889", "Q11424"])
    assert p31_of(raw) == {"Q7889", "Q11424"}
    assert p31_of({"entities": {}}) == set()


def test_fetch_walks_past_same_name_impostor_of_another_kind(monkeypatch):
    # Candidate #1 = the GAME (P31 video game, bilingual labels that MATCH the curated name —
    # exactly how it slipped through); candidate #2 = the actual webtoon. The type guard must
    # reject #1 and land on #2.
    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": "QGAME"}, {"id": "QTOON"}]}
        if "QGAME" in url:
            return _ent("QGAME", "Sweet Home", ko="스위트 홈", p31=["Q7889"])
        return _ent("QTOON", "Sweet Home", ko="스위트홈")

    monkeypatch.setattr(WikidataSource, "_http_get", http_get)
    src = WikidataSource()
    res = asyncio.run(src.fetch("webtoon:sweethome", "facts"))
    assert res["citation"].startswith("Wikidata QTOON")   # the impostor was skipped
    assert res["payload"]["name_ko"] == "스위트홈"
    # and the WINNING candidate is memoized (the next fetch skips the search entirely)
    assert src._discovered["webtoon:sweethome"] == "QTOON"


def test_fetch_raises_when_every_candidate_is_alien(monkeypatch):
    import pytest

    def http_get(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": "QGAME"}]}
        return _ent("QGAME", "Sweet Home", ko="스위트 홈", p31=["Q7889"])

    monkeypatch.setattr(WikidataSource, "_http_get", http_get)
    with pytest.raises(ValueError, match="type guard"):   # miss, never wrong
        asyncio.run(WikidataSource().fetch("webtoon:sweethome", "facts"))


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
