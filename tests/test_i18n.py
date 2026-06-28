"""Korean answer-page layer + hreflang (Naver / 국내 질의).

Korean-led entity pages at /ko/artist/<slug>.html, paired with the English pages via hreflang, plus
a Korean home at /ko/index.html and Korean URLs in the sitemap. Offline (seeded temp DB)."""

from __future__ import annotations

import asyncio
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _seed(db: str) -> None:
    p = {"name_ko": "기생충", "name_en_official": "Parasite", "name_en_source": "official",
         "directors": ["Bong Joon-ho"], "abstract_en": "Parasite is a 2019 South Korean film.",
         "attrs": {"Genre": "Thriller"}}
    asyncio.run(ingest_one("facts", "film:parasite",
                           [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))


def test_korean_entity_page_and_hreflang(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out = str(tmp_path / "site")
    res = asyncio.run(admin.entity_pages(db_path=db, out_dir=out))
    assert res["ko"] == 1
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
    assert "./artist/parasite.html" in home


def test_sitemap_includes_korean_urls(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    out = str(tmp_path / "sitemap.xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=out))
    sm = open(out, encoding="utf-8").read()
    assert f"{admin._SITE_BASE}/ko/" in sm
    assert "/ko/artist/parasite.html" in sm


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
