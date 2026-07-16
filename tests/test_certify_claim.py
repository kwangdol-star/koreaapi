"""admin.certify_claim — the operator command that runs a rights-holder certification claim
end-to-end (the /certify flow promised 'we fetch and confirm' but had no runnable step). Gates in
order: verified record -> P856 domain equality (the impostor check) -> published proof token. Success
emits the exact roster.CERTIFIED line (a reviewed code change — never auto-written). Offline via an
injected fetch."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

from koreaapi import admin, certify
from koreaapi.models import Name, Provenance, Record
from koreaapi.pipeline import store

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _db(official_url: str | None = "https://www.hybecorp.com") -> str:
    db = tempfile.mktemp(suffix=".db")
    data = {"official_url": official_url} if official_url else {}
    asyncio.run(store.append_record(Record(
        entity_id="company:hybe", kind="facts", name=Name(ko="하이브", en_official="HYBE"),
        snapshot_at=NOW, summary_en="x", data=data,
        provenance=Provenance(sources=["Wikidata Q1", "Wikipedia x"], fetched_at=NOW,
                              skill_score=1.0, confidence="high", agreeing_sources=2)), db_path=db))
    return db


def test_valid_claim_emits_the_registry_line():
    token = certify.claim_token("company:hybe", "hybecorp.com")
    out = asyncio.run(admin.certify_claim("company:hybe", "hybecorp.com", "HYBE Corporation",
                                          db_path=_db(), fetch=lambda u: f"# proof\n{token}\n"))
    assert out["ok"] is True
    assert out["entry"]["by"] == "HYBE Corporation" and out["entry"]["proof"] == "domain-control"
    assert '"company:hybe"' in out["merge_as"] and "roster.CERTIFIED" in out["note"]


def test_wrong_domain_is_refused_as_impostor_path():
    # The token is public — publishing it on a domain you happen to control must NOT certify you.
    token = certify.claim_token("company:hybe", "hybe-fanclub.com")
    out = asyncio.run(admin.certify_claim("company:hybe", "hybe-fanclub.com", "Impostor",
                                          db_path=_db(), fetch=lambda u: token))
    assert out["ok"] is False and "on-record official site" in out["reason"]
    assert out["challenge"]["domain"] == "hybecorp.com"          # points at the REAL required domain


def test_missing_token_and_missing_p856_are_refused():
    out = asyncio.run(admin.certify_claim("company:hybe", "hybecorp.com",
                                          db_path=_db(), fetch=lambda u: "nothing here"))
    assert out["ok"] is False and "does not match" in out["reason"]
    out2 = asyncio.run(admin.certify_claim("company:hybe", "hybecorp.com",
                                           db_path=_db(official_url=None), fetch=lambda u: ""))
    assert out2["ok"] is False and "P856" in out2["reason"]      # no on-record site -> nothing to bind to


def test_unreachable_proof_url_reports_and_returns_challenge():
    def boom(u):
        raise OSError("connection refused")
    out = asyncio.run(admin.certify_claim("company:hybe", "hybecorp.com", db_path=_db(), fetch=boom))
    assert out["ok"] is False and "could not fetch" in out["reason"]
    assert out["challenge"]["publish_at"].endswith("/.well-known/koreaapi-certify.txt")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
