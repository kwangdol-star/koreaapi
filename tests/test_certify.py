"""Supply-side certification (the endgame moat): the /certify storefront + /certified.json registry +
the CERTIFIED tier flowing onto the entity page. The rail ships INERT (empty) and self-populates the
moment a real institution certifies — position first (free), monetize later (managed tier, dormant). Offline."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, certify, service
from koreaapi.models import Name, Provenance, Record


def _seed(db: str, eid: str = "artist:newjeans", agency: str = "ADOR") -> None:
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    asyncio.run(admin.store.append_record(Record(
        entity_id=eid, kind="facts", name=Name(ko="뉴진스", en_official="NewJeans"),
        snapshot_at=now, summary_en="NewJeans", data={"agency_en": agency},
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=now,
                              skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))


def test_certify_storefront_pages_written(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    en = (tmp_path / "site" / "certify.html").read_text(encoding="utf-8")
    ko = (tmp_path / "site" / "ko" / "certify.html").read_text(encoding="utf-8")
    assert "Certify your record" in en and "cross-verification" in en
    assert "Free for official rights-holders" in en          # free-to-win positioning
    assert "managed tier" in en                              # the dormant paid hook (position first)
    assert "certified.json" in en and "officially_certified" in en   # links the registry + the queryable flag
    assert "공식 인증" in ko and "무료" in ko and "관리형 등급" in ko   # KO parity + dormant paid hook
    assert 'href="../certified.json"' in ko  # root-relative from /ko/ (regression: was a broken ./certified.json)


def test_certified_feed_empty_by_default(tmp_path):
    # The rail ships inert: no fabricated certifications (the hallucination lesson) — just the structure.
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    asyncio.run(admin.export(db_path=db, out_dir=str(tmp_path)))
    feed = json.load(open(tmp_path / "certified.json", encoding="utf-8"))
    assert feed["count"] == 0 and feed["certified"] == []
    assert feed["license"]["id"] == "CC-BY-4.0"
    assert feed["how_to_certify"].endswith("/certify.html")


def test_certification_flows_to_feed_and_page(tmp_path, monkeypatch):
    # When a real rights-holder certifies (CERTIFIED gains an entry), it flows to the registry AND the
    # entity page 🏅 badge — the rail is live end-to-end, just dormant until claimed.
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    monkeypatch.setitem(admin.CERTIFIED, "artist:newjeans",
                        {"by": "ADOR", "date": "2026-06-01", "url": "https://ador.example/verify"})
    asyncio.run(admin.export(db_path=db, out_dir=str(tmp_path)))
    feed = json.load(open(tmp_path / "certified.json", encoding="utf-8"))
    assert feed["count"] == 1
    c = feed["certified"][0]
    assert c["entity_id"] == "artist:newjeans" and c["certified_by"] == "ADOR"
    assert c["name"]["en_official"] == "NewJeans" and c["tier"] == "certified"  # shape matches get_certified API
    assert c["certified_date"] == "2026-06-01" and c["in_store"] is True
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    page = (tmp_path / "site" / "artist" / "newjeans.html").read_text(encoding="utf-8")
    assert "officially certified by ADOR" in page and "Official certification" in page


def test_certify_in_sitemap_and_manifest(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    sm = tempfile.mktemp(suffix=".xml")
    asyncio.run(admin.sitemap(db_path=db, out_path=sm))
    assert "/certify.html" in open(sm, encoding="utf-8").read()
    assert "certified_feed" in admin._agents_manifest()["data"]
    assert any(t[0] == "get_certified" for t in admin._MCP_TOOLS)  # advertised as an agent tool


def test_get_certified_registry_queryable(monkeypatch):
    # Symmetry with get_history / get_changes: the certified registry is an agent-queryable feed. Inert
    # (empty) by default; self-populates when a real rights-holder certifies.
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    empty = asyncio.run(service.certified(db_path=db))
    assert empty["count"] == 0 and empty["certified"] == [] and empty["license"]["id"] == "CC-BY-4.0"
    assert empty["how_to_certify"].endswith("/certify.html")
    monkeypatch.setitem(admin.CERTIFIED, "artist:newjeans",
                        {"by": "ADOR", "date": "2026-06-01", "url": "https://ador.example/verify"})
    out = asyncio.run(service.certified(db_path=db))
    assert out["count"] == 1
    c = out["certified"][0]
    assert c["entity_id"] == "artist:newjeans" and c["certified_by"] == "ADOR"
    assert c["name"]["en_official"] == "NewJeans" and c["in_store"] is True and c["tier"] == "certified"


def test_certify_domain_control_protocol():
    # The real-use proof: DOMAIN CONTROL of the entity's official site — deterministic token, published
    # at a well-known path only the domain owner can write. Pure + offline.
    assert certify.official_domain("https://www.hybecorp.com/about") == "hybecorp.com"  # strip scheme/www/path
    assert certify.official_domain("hybecorp.com") == "hybecorp.com"                     # tolerate a bare host
    assert certify.official_domain("http://Ador.example:8080/x") == "ador.example"       # lowercase, drop port
    assert certify.official_domain(None) is None and certify.official_domain("ftp://x.com") is None
    assert certify.official_domain("nodot") is None                                      # hostless -> None
    # deterministic + normalization-stable: the bare host and the full URL yield the SAME token
    t = certify.claim_token("artist:bts", "hybecorp.com")
    assert t.startswith("koreaapi-certify=")
    assert t == certify.claim_token("artist:bts", "https://www.hybecorp.com/x")
    assert t != certify.claim_token("artist:iu", "hybecorp.com")   # bound to the entity
    # verification: the token in the fetched file passes; noise / wrong-entity / empty fail
    assert certify.verify_published(f"# koreaapi\n{t}\n", "artist:bts", "hybecorp.com") is True
    assert certify.verify_published("nope", "artist:bts", "hybecorp.com") is False
    assert certify.verify_published(t, "artist:iu", "hybecorp.com") is False
    assert certify.verify_published(None, "artist:bts", "hybecorp.com") is False
    # the merged registry entry: domain-anchored + dated (non-forgeable / non-backdatable)
    rec = certify.claim_record("artist:bts", "HYBE", "www.hybecorp.com", "2026-06-01")
    assert rec["by"] == "HYBE" and rec["date"] == "2026-06-01" and rec["domain"] == "hybecorp.com"
    assert rec["proof"] == "domain-control" and rec["url"].endswith("/.well-known/koreaapi-certify.txt")


def test_certify_record_flows_into_get_certified(monkeypatch):
    # A domain-control claim_record, once merged, is exactly what service.certified() reads back.
    db = tempfile.mktemp(suffix=".db")
    _seed(db, "artist:newjeans", "ADOR")
    monkeypatch.setitem(admin.CERTIFIED, "artist:newjeans",
                        certify.claim_record("artist:newjeans", "ADOR", "ador.com", "2026-06-01"))
    out = asyncio.run(service.certified(db_path=db))
    assert out["count"] == 1 and out["certified"][0]["certified_by"] == "ADOR"


def test_certify_storefront_documents_domain_control(tmp_path):
    # The storefront makes step 2 CONCRETE: publish a token at the well-known path on your official domain.
    db = tempfile.mktemp(suffix=".db")
    _seed(db)
    asyncio.run(admin.entity_pages(db_path=db, out_dir=str(tmp_path / "site")))
    en = (tmp_path / "site" / "certify.html").read_text(encoding="utf-8")
    ko = (tmp_path / "site" / "ko" / "certify.html").read_text(encoding="utf-8")
    assert "/.well-known/koreaapi-certify.txt" in en and "domain control" in en and "P856" in en
    assert "/.well-known/koreaapi-certify.txt" in ko and "도메인 소유 증명" in ko


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
