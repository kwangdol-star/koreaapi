"""Tamper-evident integrity layer — turns "verifiable" from a claim into a CHECKABLE property.

Our concept is a *verifiable*, *append-only* data layer. This module lets anyone prove both:

- record_fingerprint(rec): a STABLE SHA-256 of a record's verified CONTENT (bilingual name + facts +
  which sources agreed + Skill Score), with per-fetch citation timestamps normalized out — so it
  changes ONLY when the verified facts change, not on every re-collect. Published per record as
  `content_hash`, so a single cited row can be independently re-checked.
- dataset_hash(records): the fingerprint of the WHOLE published dataset (order-independent),
  reproducible by anyone who fetches latest.json — proves the published data matches the published hash.
- chain_head(snapshots.jsonl): a hash CHAIN over the append-only history — each line hashes the
  previous, so altering any past snapshot breaks the chain from that point on. The head is published
  (and git-committed) each build, so altered history is detectable against the prior head.

This is tamper-EVIDENCE (a published, committed head), NOT external notarization — anchoring the head
to a public timestamp authority is a possible future step. No re-derivation of open data can show an
unaltered, hash-chained verification trail; that is what hardens the moat.
"""

from __future__ import annotations

import hashlib
import json
import re

ALGORITHM = "sha256"
_TS = re.compile(r"\s+\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")  # a per-fetch citation timestamp suffix


def _stable_sources(sources) -> list[str]:
    """Keep the stable part of each citation (provider + id); drop the per-fetch timestamp."""
    return sorted(_TS.sub("", s) for s in (sources or []))


def _core(rec: dict) -> dict:
    """The stable verified core of a record (per-fetch timestamps + transient fields excluded)."""
    name = rec.get("name") or {}
    prov = rec.get("provenance") or {}
    return {
        "entity_id": rec.get("entity_id"),
        "kind": rec.get("kind"),
        "name": {"ko": name.get("ko"), "en_official": name.get("en_official"),
                 "romanized": name.get("romanized")},
        "summary_en": rec.get("summary_en"),
        "summary_ko": rec.get("summary_ko"),
        "data": rec.get("data"),
        "skill_score": round(float(prov.get("skill_score") or 0), 4),
        "agreeing_sources": prov.get("agreeing_sources"),
        "sources": _stable_sources(prov.get("sources")),
    }


def _sha_obj(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def record_fingerprint(rec: dict) -> str:
    """Stable SHA-256 of a record's verified content (ignores any existing `content_hash`)."""
    return _sha_obj(_core(rec))


def dataset_hash(records: list[dict]) -> str:
    """Order-independent SHA-256 of the whole dataset: hash the sorted per-record fingerprints."""
    return hashlib.sha256("".join(sorted(record_fingerprint(r) for r in records)).encode("utf-8")).hexdigest()


def chain_head(snapshots_path: str) -> tuple[str | None, int]:
    """Hash-chain over the append-only history file (raw lines). Returns (head_hex_or_None, line_count)."""
    head, n = "", 0
    try:
        with open(snapshots_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                head = hashlib.sha256((head + line).encode("utf-8")).hexdigest()
                n += 1
    except FileNotFoundError:
        return None, 0
    return (head or None), n
