"""Best-effort Korean -> Latin romanization via a cheap LLM (Haiku).

"Cheap AI as collection labor" (PRINCIPLES): fills the `name_romanized` field once at ingest
(append-only caches it forever). No `ANTHROPIC_API_KEY`, or any error -> returns None;
romanization is a nice-to-have and must never break ingestion. Runs on the open network
(GitHub runners / deploy) where the key is provided as a secret; a no-key dev/sandbox skips it.
"""

from __future__ import annotations

import os

_MODEL = "claude-haiku-4-5-20251001"  # cheap; romanization is a tiny task

_SYSTEM = (
    "You romanize Korean text using Revised Romanization of Korean. "
    "Output ONLY the romanization (Latin letters), no quotes, no notes, no Korean."
)


def romanize(ko: str | None) -> str | None:
    """Return the Revised-Romanization of `ko`, or None (no key / blank / any failure)."""
    if not ko or not ko.strip() or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        msg = anthropic.Anthropic().messages.create(
            model=_MODEL,
            max_tokens=40,
            system=_SYSTEM,
            messages=[{"role": "user", "content": ko.strip()}],
        )
        out = "".join(
            b.text for b in msg.content if getattr(b, "type", "") == "text"
        ).strip()
        return out or None
    except Exception:
        return None  # best-effort: never break ingest on a romanization failure
