"""Best-effort structured enrichment from the Wikipedia lead abstract via a cheap LLM (Haiku).

"Cheap AI as collection labor" (PRINCIPLES): the Wikipedia lead is ALREADY a cited source on the
record, but its facts sit in prose. This pulls a few structured `key: value` facts (+ alternate
names) OUT of that prose so they ride in `attrs` / `aliases` — then GROUNDS every value against the
abstract text (drops anything not literally present), exactly like the Circle Chart extractor
(`sources/circlechart._grounded`). So a hallucinated or outside-knowledge value can NEVER enter a
verified record: extraction is the labor, grounding is the gate. "verification over trust" holds.

Safety envelope (matches romanize.py / circlechart.py):
  - `enrich()` returns None when it could NOT run (no abstract / no `ANTHROPIC_API_KEY` / any error) so
    the caller retries on a later build (SELF-HEAL). It returns the grounded dict — possibly with empty
    attrs & aliases — only on a REAL run (a completed call that grounded, even if it grounded nothing).
  - attrs are GAP-FILL ONLY: a key already carried by a structured source (Wikidata/KTO/KOSIS) is
    never overridden — the cross-verified value always wins.
  - RUN-ONCE per entity: the first SUCCESSFUL derivation is stored (data.enrichment) and later builds
    carry it forward (no repeat call). A no-key / failed build stores NO marker, so it is retried — a
    transient Haiku error on first sighting can never freeze an entity un-enriched forever.
  - `parse_enrichment` + `ground_enrichment` are pure and offline-tested; the live LLM call runs
    only where the key is set (GitHub runners / deploy).
"""

from __future__ import annotations

import json
import os
import re

_MODEL = "claude-haiku-4-5-20251001"  # cheap extraction labor

_SYSTEM = (
    "You extract STRUCTURED FACTS from an encyclopedia lead paragraph about a Korean cultural "
    'entity. Return ONLY a JSON object: {"attrs": {label: value, ...}, "aliases": [name, ...]}.\n'
    "Hard rules:\n"
    "- Every value and every alias MUST be copied VERBATIM from the text. No paraphrase, no "
    "outside knowledge, no inference, no translation.\n"
    "- Only emit a fact when the text states the label relationship EXPLICITLY.\n"
    "- Prefer short values a database column holds: a year, a place, a number, a proper noun, a "
    "category. Labels are short Title-Case English (Founded, Location, Capacity, Genre, Director).\n"
    "- aliases = other names/spellings the text gives for the SAME entity.\n"
    "- Max 6 attrs, 4 aliases. If unsure, omit it. No prose, no markdown, no code fences."
)

_MAX_ATTRS = 6
_MAX_ALIASES = 4


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _in_text(value: str, haystack: str) -> bool:
    """Grounding gate: `value` is literally present in the abstract (space-normalized, case-insensitive).
    A value not in the source text is a hallucination and is dropped — the same guard the chart uses."""
    v = _norm(value).casefold()
    return bool(v) and v in _norm(haystack).casefold()


def parse_enrichment(text: str) -> dict:
    """Pure: an LLM reply -> {"attrs": {str: str}, "aliases": [str]}. Tolerant of prose / markdown
    fencing around the JSON; a malformed reply -> empty (never raises)."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {"attrs": {}, "aliases": []}
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return {"attrs": {}, "aliases": []}
    if not isinstance(obj, dict):
        return {"attrs": {}, "aliases": []}
    attrs: dict[str, str] = {}
    raw_attrs = obj.get("attrs")
    if isinstance(raw_attrs, dict):
        for k, v in raw_attrs.items():
            if isinstance(k, str) and isinstance(v, (str, int, float)) and _norm(k) and _norm(v):
                attrs[_norm(k)] = _norm(v)
    aliases: list[str] = []
    raw_aliases = obj.get("aliases")
    if isinstance(raw_aliases, list):
        for a in raw_aliases:
            if isinstance(a, str) and _norm(a):
                aliases.append(_norm(a))
    return {"attrs": attrs, "aliases": aliases}


def ground_enrichment(
    parsed: dict, abstract: str, *, existing_keys: tuple = (), known_names: tuple = ()
) -> dict:
    """Pure anti-hallucination gate. Keep an attr only if its VALUE is literally in the abstract AND
    its key is not already carried (gap-fill). Keep an alias only if it is literally in the abstract
    and is not already a known name. Caps applied last."""
    ex = {_norm(k).casefold() for k in existing_keys}
    known = {_norm(n).casefold() for n in known_names if n}
    attrs: dict[str, str] = {}
    for k, v in (parsed.get("attrs") or {}).items():
        if _norm(k).casefold() in ex or _norm(k).casefold() in {a.casefold() for a in attrs}:
            continue
        if _in_text(v, abstract):
            attrs[k] = v
        if len(attrs) >= _MAX_ATTRS:
            break
    aliases: list[str] = []
    seen = set(known)
    for a in parsed.get("aliases") or []:
        key = _norm(a).casefold()
        if key in seen:
            continue
        if _in_text(a, abstract):
            aliases.append(a)
            seen.add(key)
        if len(aliases) >= _MAX_ALIASES:
            break
    return {"attrs": attrs, "aliases": aliases}


def enrich(abstract: str | None, *, existing_keys: tuple = (), known_names: tuple = ()) -> dict | None:
    """Best-effort: grounded structured attrs + aliases from a Wikipedia lead abstract.

    Returns None when it could NOT run — no abstract / no `ANTHROPIC_API_KEY` / any error — so the caller
    retries on a later build (never poisons the run-once marker with a transient failure). Returns the
    grounded {"attrs": ..., "aliases": ...} (possibly empty) only on a REAL, completed run. Never raises."""
    if not abstract or not abstract.strip() or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        msg = anthropic.Anthropic().messages.create(
            model=_MODEL,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": abstract.strip()[:6000]}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        parsed = parse_enrichment(text)
        return ground_enrichment(parsed, abstract, existing_keys=existing_keys, known_names=known_names)
    except Exception:
        return None  # transient failure -> None so ingest retries next build (self-heal); never break ingest
