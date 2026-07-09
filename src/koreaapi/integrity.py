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
import os
import re
import shutil
import subprocess

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


def anchor_head(head_hex: str | None, out_dir: str) -> dict:
    """Best-effort EXTERNAL anchoring of the chain-head via OpenTimestamps — a FREE, KEYLESS timestamp
    on the Bitcoin blockchain (no wallet, no gas). Writes `integrity-head.txt` + its `.ots` proof to
    out_dir and returns the anchor status. Runs where the network + the `ots` client are present (the
    collector runner); a DORMANT status otherwise, so a build never breaks.

    This turns the time moat from self-attestation into EXTERNAL cryptographic timestamping: with the
    chain-head anchored to Bitcoin, a latecomer cannot forge that this exact append-only verification
    history existed at this time — the strongest, non-replicable moat, made externally provable. The
    proof matures into a full Bitcoin attestation in ~1 day; verify with `ots verify`.
    """
    base = {
        "method": "opentimestamps", "chain": "bitcoin", "keyless": True, "cost": "free",
        "note": ("external, keyless timestamp of the append-only chain-head (no wallet/gas) — the time "
                 "moat beyond self-attestation: a latecomer cannot forge this history's existence-time"),
    }
    if not head_hex:
        return {**base, "status": "no_history"}
    if shutil.which("ots") is None:  # dormant rail: ships inert, self-activates when the client is present
        return {**base, "status": "dormant",
                "activate": "add `opentimestamps-client` to the build (provides the `ots` CLI); it then "
                            "stamps the chain-head on every run"}
    try:
        os.makedirs(out_dir, exist_ok=True)
        head_file = os.path.join(out_dir, "integrity-head.txt")
        with open(head_file, "w", encoding="utf-8") as f:
            f.write(head_hex + "\n")
        # `ots stamp` submits the file's SHA-256 to the OpenTimestamps calendars and writes <file>.ots
        # (a pending proof, upgradeable to a full Bitcoin attestation later). Bounded so a slow calendar
        # can never hang a build.
        proc = subprocess.run(["ots", "stamp", head_file], capture_output=True, text=True, timeout=90)
        proof = head_file + ".ots"
        if proc.returncode == 0 and os.path.exists(proof):
            return {**base, "status": "stamped", "head": head_hex,
                    "target_file": os.path.basename(head_file), "proof": os.path.basename(proof),
                    "verify": "ots verify integrity-head.txt.ots  (after the Bitcoin attestation matures, ~1 day)"}
        return {**base, "status": "stamp_failed", "detail": (proc.stderr or proc.stdout or "").strip()[:200]}
    except Exception as exc:  # best-effort — anchoring must never break a build
        return {**base, "status": "error", "detail": str(exc)[:200]}
