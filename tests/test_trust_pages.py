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
    fa_ko = open(os.path.join(out, "ko", "for-agents.html"), encoding="utf-8").read()
    assert '<html lang="ko">' in fa_ko and "MCP 빠른 시작" in fa_ko
    man = json.load(open(os.path.join(out, "agents.json"), encoding="utf-8"))
    assert man["name"] == "KoreaAPI"
    assert any(t["name"] == "get_verified" for t in man["mcp"]["tools"])
    assert man["mcp"]["command"] == "python -m koreaapi.server"
    assert man["data"]["open_json"].endswith("/latest.json")
    assert man["verification"]["integrity"].endswith("/integrity.json")
    assert man["premium"]["protocol"] == "x402" and man["cite_as"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
