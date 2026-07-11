"""The trust + agent-operator surface: /methodology (E-E-A-T) and /for-agents + /agents.json (the
page + manifest a person wiring an agent reads). EN + KO, paired via hreflang. Offline."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

from koreaapi import admin
from koreaapi.pipeline.ingest import ingest_one
from koreaapi.sources.mock import MockSource


def _build(tmp_path) -> str:
    db = tempfile.mktemp(suffix=".db")
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official",
         "agency_en": "Big Hit Music", "members": ["RM"]}
    asyncio.run(ingest_one("facts", "artist:bts",
                           [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    out = str(tmp_path / "site")
    asyncio.run(admin.entity_pages(db_path=db, out_dir=out))
    return out


def test_methodology_pages(tmp_path):
    out = _build(tmp_path)
    en = open(os.path.join(out, "methodology.html"), encoding="utf-8").read()
    assert "How KoreaAPI verifies" in en and "Skill Score" in en and "Identity" in en
    assert '"@type": "TechArticle"' in en
    assert 'hreflang="ko"' in en and "/ko/methodology.html" in en
    ko = open(os.path.join(out, "ko", "methodology.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in ko and "검증 방법" in ko and 'hreflang="en"' in ko


def test_for_agents_page_and_manifest(tmp_path):
    out = _build(tmp_path)
    fa = open(os.path.join(out, "for-agents.html"), encoding="utf-8").read()
    assert "python -m koreaapi.server" in fa and "<code>get_verified</code>" in fa
    assert "./agents.json" in fa and 'hreflang="ko"' in fa
    assert "verified, not just asserted" in fa and "not by brand" in fa  # positioning: verification-trust
    fa_ko = open(os.path.join(out, "ko", "for-agents.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in fa_ko and "MCP 빠른 시작" in fa_ko
    assert "브랜드가 아니라 구조로" in fa_ko  # KO parity for the positioning
    man = json.load(open(os.path.join(out, "agents.json"), encoding="utf-8"))
    assert man["name"] == "KoreaAPI"
    assert man["trust_model"]["basis"] == "verification, not brand"   # the differentiator, machine-readable
    assert "Skill Score" in man["trust_model"]["how"]
    assert "open-data ecosystem" in man["trust_model"]["ecosystem"]   # positioned as the verification layer
    assert any(t["name"] == "get_verified" for t in man["mcp"]["tools"])
    assert man["mcp"]["command"] == "python -m koreaapi.server"
    assert man["data"]["open_json"].endswith("/latest.json")
    assert man["verification"]["integrity"].endswith("/integrity.json")
    assert man["premium"]["protocol"] == "x402" and man["cite_as"]


def test_pricing_pages(tmp_path):
    out = _build(tmp_path)
    en = open(os.path.join(out, "pricing.html"), encoding="utf-8").read()
    assert "Pricing" in en and "x402" in en and "KoreaAPI Pro" in en
    assert 'hreflang="ko"' in en and "/ko/pricing.html" in en
    ko = open(os.path.join(out, "ko", "pricing.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in ko and "가격" in ko and 'hreflang="en"' in ko


def test_status_json_health_snapshot(tmp_path):
    db = tempfile.mktemp(suffix=".db")
    p = {"name_ko": "방탄소년단", "name_en_official": "BTS", "name_en_source": "official"}
    asyncio.run(ingest_one("facts", "artist:bts",
                           [MockSource("Wikidata", p), MockSource("Wikipedia", p)], db_path=db))
    out = str(tmp_path / "status.json")
    asyncio.run(admin.status_json(db_path=db, out_path=out))
    s = json.load(open(out, encoding="utf-8"))
    assert s["ok"] and s["entities"] == 1 and s["cross_verified"] == 1
    assert "avg_skill_score" in s and "fresh" in s and s["integrity"].endswith("/integrity.json")


def test_status_json_empty_store_keeps_static_file():
    sentinel = tempfile.mktemp(suffix=".json")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("STATIC")
    asyncio.run(admin.status_json(db_path=tempfile.mktemp(suffix=".db"), out_path=sentinel))
    assert open(sentinel, encoding="utf-8").read() == "STATIC"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
