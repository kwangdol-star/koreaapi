"""Supply-side certification (the endgame moat): the /certify storefront + /certified.json registry +
the CERTIFIED tier flowing onto the entity page. The rail ships INERT (empty) and self-populates the
moment a real institution certifies — position first (free), monetize later (managed tier, dormant). Offline."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, service
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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
