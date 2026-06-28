"""Korean answer-page layer + hreflang (Naver / 국내 질의).

Korean-led entity pages (/ko/artist/<slug>.html), vertical hubs (/ko/<vertical>.html), person pages
(/ko/person/<slug>.html) and a /ko/ home — each paired with its English page via hreflang, and listed
in the sitemap. Offline (seeded temp DB)."""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _seed(db: str) -> None:
    facts = [
        ("film:parasite", {"name_ko": "기생충", "name_en_official": "Parasite", "name_en_source": "official",
                           "directors": ["Bong Joon-ho"], "attrs": {"Genre": "Thriller"},
                           "abstract_en": "Parasite is a 2019 South Korean film."}),
        ("film:memoriesofmurder", {"name_ko": "살인의 추억", "name_en_official": "Memories of Murder",
                                   "name_en_source": "official", "directors": ["Bong Joon-ho"]}),
    ]
    for eid, p in facts:
        asyncio.run(ingest_one("facts", eid, [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_korean_entity_page_and_hreflang(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out))
    assert res["ko"] == 2
    # Korean-led page: lang=ko, Korean h1 + headings + cite, attr key translated, hreflang back to EN
    ko = open(os.path.join(out, "ko", "artist", "parasite.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in ko
    assert "<h1>기생충" in ko and "검증된 사실" in ko and "이렇게 인용하세요" in ko
    assert "<b>장르:</b> Thriller" in ko                             # Genre -> 장르
    assert 'hreflang="en"' in ko and "/artist/parasite.html" in ko
    # English page now declares its Korean alternate (the pairing search engines need)
    en = open(os.path.join(out, "artist", "parasite.html"), encoding="utf-8").read()
    assert 'hreflang="ko"' in en and "/ko/artist/parasite.html" in en
    # Korean home: lang=ko, hreflang to EN home, internal link into the /ko/ layer
    home = open(os.path.join(out, "ko", "index.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in home and 'hreflang="en"' in home
    assert "./artist/parasite.html" in home and "./films.html" in home   # links to ko hubs + entities


def test_korean_hub_and_person_pages(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out))
    # Korean vertical hub: lang=ko, Korean label, links into /ko/ entities, hreflang to the EN hub
    films_ko = open(os.path.join(out, "ko", "films.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in films_ko and "K-영화" in films_ko
    assert "./artist/parasite.html" in films_ko
    assert 'hreflang="en"' in films_ko and "../films.html" in films_ko
    films_en = open(os.path.join(out, "films.html"), encoding="utf-8").read()
    assert 'hreflang="ko"' in films_en and "/ko/films.html" in films_en
    # Korean person page (Bong Joon-ho: a director -> qualifies for a hub)
    bong_ko = open(os.path.join(out, "ko", "person", "bong-joon-ho.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in bong_ko and "검증된 크레딧" in bong_ko
    assert "../artist/parasite.html" in bong_ko and 'hreflang="en"' in bong_ko
    bong_en = open(os.path.join(out, "person", "bong-joon-ho.html"), encoding="utf-8").read()
    assert 'hreflang="ko"' in bong_en and "/ko/person/bong-joon-ho.html" in bong_en
    # Korean people hub
    people_ko = open(os.path.join(out, "ko", "people.html"), encoding="utf-8").read()
    assert "검증된 인물" in people_ko and "./person/bong-joon-ho.html" in people_ko


def test_sitemap_includes_korean_urls(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out = str(tmp_path / "sitemap.xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=out))
    sm = open(out, encoding="utf-8").read()
    assert f"{admin._SITE_BASE}/ko/" in sm
    assert "/ko/artist/parasite.html" in sm        # ko entity
    assert "/ko/films.html" in sm                  # ko hub
    assert "/ko/person/bong-joon-ho.html" in sm    # ko person


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
