"""Supply-side certification — the DOMAIN-CONTROL claim protocol (the real-use rail; registry dormant).

The certified tier ranks ABOVE cross-verification: an official rights-holder vouches for the record.
The non-forgeable proof is DOMAIN CONTROL — only whoever controls the entity's official website (the
SAME P856 official_url KoreaAPI already cross-verified) can publish a token at a well-known path on it.
A same-name impostor cannot. This makes step 2 of /certify ("prove you speak for it") concrete + real.

This module is PURE (no network): it derives the deterministic proof token, validates a published proof
string, and shapes the one-line CERTIFIED entry a maintainer merges once the proof checks out. The actual
fetch of the published token is an out-of-band, best-effort step (like integrity.anchor_head) — the
registry stays INERT until a real institution proves in (we never fabricate a certification).
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

WELL_KNOWN = "/.well-known/koreaapi-certify.txt"  # where the rights-holder publishes the proof token
_PROOF = "domain-control"


def official_domain(url: str | None) -> str | None:
    """The normalized host of an official URL (P856): lowercased, no scheme / port / path, leading
    'www.' stripped. Returns None for a blank / non-http(s) / hostless value. Pure — the anchor shared
    by the commerce gateway (route here) and certification (prove control of THIS domain)."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if "://" not in u:
        u = "https://" + u  # tolerate a bare 'example.com'
    try:
        parsed = urlparse(u)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().strip().rstrip(".")  # strip a trailing FQDN dot (example.com.)
    if not host or "." not in host:
        return None
    return host[4:] if host.startswith("www.") else host


def claim_token(entity_id: str, domain: str) -> str:
    """The deterministic proof token a rights-holder publishes to prove control of `domain` for
    `entity_id`. Reproducible (no secret, no timestamp) so anyone can re-verify it; the security is that
    ONLY the domain owner can publish it at WELL_KNOWN on that domain. Pure."""
    dom = official_domain(domain) or (domain or "").strip().lower()
    digest = hashlib.sha256(f"{entity_id}|{dom}".encode()).hexdigest()[:40]
    return f"koreaapi-certify={digest}"


def claim_challenge(entity_id: str, domain: str) -> dict:
    """The full instruction envelope — the token + exactly where to publish it + the steps. Deterministic
    and offline, so a rights-holder (or their agent) can self-serve the proof before opening a request."""
    dom = official_domain(domain) or (domain or "").strip().lower()
    token = claim_token(entity_id, dom)
    return {
        "entity_id": entity_id,
        "domain": dom,
        "token": token,
        "publish_at": f"https://{dom}{WELL_KNOWN}",
        "proof": _PROOF,
        "steps": [
            f"Publish this exact line as plain text at https://{dom}{WELL_KNOWN}",
            "Open a request (GitHub issue) with the entity_id + domain; we fetch that URL and confirm the "
            "token matches AND the domain matches the official website already on the record (Wikidata P856).",
            "We add the one-line certification (your name + date + source URL); it flows to /certified.json, "
            "the entity page 🏅, and get_verified (officially_certified: true).",
        ],
    }


def verify_published(published_text: str | None, entity_id: str, domain: str) -> bool:
    """True iff the text fetched from the domain's well-known path carries the expected token for this
    entity (tolerant of surrounding whitespace / extra lines). Pure — the caller performs the fetch."""
    if not published_text:
        return False
    want = claim_token(entity_id, domain)
    return any(line.strip() == want for line in published_text.splitlines())


def domain_matches_record(domain: str, record_official_url: str | None) -> bool:
    """True iff `domain` is the SAME host as the entity's on-record official website (Wikidata P856).
    This equality is what the whole proof rests on: certification must bind to the domain KoreaAPI has
    ALREADY cross-verified for the entity — not any domain a claimant happens to control. Enforced in
    CODE here, not left as prose on the /certify page. Pure."""
    rec = official_domain(record_official_url)
    return bool(rec) and rec == official_domain(domain)


def verify_claim(published_text: str | None, entity_id: str, domain: str,
                 record_official_url: str | None) -> bool:
    """The COMPLETE gate an automated verifier MUST pass before certifying: (1) the proof token is
    published at the domain AND (2) that domain equals the entity's on-record official website (P856).
    Either alone is insufficient — the token is public, so a claimant could publish it on any domain they
    control; the P856-equality is what ties control of the domain to authority over THE entity. Pure."""
    return (verify_published(published_text, entity_id, domain)
            and domain_matches_record(domain, record_official_url))


def claim_record(entity_id: str, org: str, domain: str, date: str, url: str | None = None) -> dict:
    """The CERTIFIED-registry entry a maintainer merges AFTER verify_published passes — the shape
    service.certified() / get_certified reads (by / date / url), plus the domain + proof method for
    audit. Domain-anchored and dated: non-forgeable and non-backdatable by a latecomer."""
    dom = official_domain(domain) or (domain or "").strip().lower()
    return {"by": org, "date": date, "url": url or f"https://{dom}{WELL_KNOWN}",
            "domain": dom, "proof": _PROOF}
