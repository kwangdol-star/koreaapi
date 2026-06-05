# Share copy — KoreaAPI

Ready-to-post copy for distribution. Goal of Phase-1 sharing: **earn citations + agent
discovery** (not vanity reach). Lead with the verifiable angle, always link the public data.

**Links:** data page <https://kwangdol-star.github.io/koreaapi/> · digest
`/korea-rising.md` · agents `/llms.txt` + [`docs/MCP_INSTALL.md`](./MCP_INSTALL.md)

---

## One-liner
> KoreaAPI — the verifiable data layer for Korean culture, callable by any AI agent (MCP).
> Every fact is cross-verified across independent sources and carries a source + Skill Score.

## Talking points (the differentiators)
- **Verification is the product, not the data.** A fact clears the single-source cap only when
  ≥2 independent sources (Wikidata + Wikipedia) agree on the canonical bilingual name.
- **Guarded against the two ways LLMs lie:** an *identity guard* rejects a contradictory label;
  a *hallucination guard* drops any LLM-extracted entry not present verbatim in its source
  (it caught a model fabricating a stale chart #1 in a live run).
- **Agent-native:** 5 MCP tools; every response carries provenance + a ready-to-cite line.
- **Bilingual** (Korean canonical, English for distribution) and **append-only** (the time-series
  is the moat).

## Show HN / dev forums
> **Show HN: KoreaAPI — a verifiable K-culture data layer for AI agents (MCP)**
>
> Korean-culture API wrappers are a commodity; the hard part is *trust*. KoreaAPI cross-verifies
> every fact across independent sources (Wikidata + Wikipedia must agree on the canonical name),
> attaches a transparent 0–1 Skill Score + provenance, and guards the two failure modes LLMs
> have: contradictory identities are rejected, and LLM-extracted data must appear verbatim in its
> source or it's dropped (this caught a hallucinated chart #1 live). It exposes 5 MCP tools and
> publishes Schema.org JSON-LD + /llms.txt so answer engines can cite it. Phase 1, open, early.
> Verified data: https://kwangdol-star.github.io/koreaapi/

## r/LocalLLaMA / agent-builder communities
> Built an MCP server that returns **verified** Korean-culture data — each response has its
> source + a Skill Score, cross-verified across ≥2 sources, with a hallucination guard that
> drops anything not literally in the source. 5 tools (artist status, agency roster, calendar,
> "Korea rising", buy options). Install/connect: [MCP_INSTALL]. Feedback welcome.

## X / Threads thread
1/ Korean-culture data for AI agents is everywhere — but can you *trust* it? KoreaAPI makes
   verification the product: every fact cross-checked across independent sources, with a source
   + Skill Score attached. 🧵
2/ Two guards: an identity guard rejects contradictory labels; a hallucination guard drops any
   LLM-extracted entry not present verbatim in its source. (It caught a model inventing a stale
   chart #1 — and refused to ship it.)
3/ Agent-native: 5 MCP tools, Schema.org JSON-LD + /llms.txt so answer engines can cite it.
   Bilingual, append-only. Verified data, live: https://kwangdol-star.github.io/koreaapi/

## Honesty note (keep us credible)
Phase 1 / cold-start: real verified roster + agencies + Circle Chart #1 (via Wikipedia) + YouTube
releases are live; commerce/payment rails are deliberately *not* wired yet (they come after
traffic). Don't overclaim coverage — the moat is verification + provenance, so let the Skill
Scores and citations speak.
