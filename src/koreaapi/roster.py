"""The artist roster - entity_id -> canonical name (the live-resolution search term).

These are NOT Q-ids. Q-ids are resolved LIVE on the open network (GitHub runners) via
wbsearchentities / Wikipedia and cross-verified, never hardcoded unverified - that is exactly
how a wrong id ("Q484203 = Arborka") slipped in before. The fetched name is then identity-
checked against this canonical name, so a wrong search resolution is rejected by graceful
degradation, never ingested.

Keep names DISTINCTIVE (low search-collision); a name that also matches an unrelated entity
could pass the name guard. The 3 hottest acts also have verified Q-ids in
sources/wikidata.py `_CURATED` (fast path + bilingual guard).
"""

ARTISTS = {
    "artist:bts": "BTS",
    "artist:newjeans": "NewJeans",
    "artist:aespa": "aespa",
    "artist:blackpink": "BLACKPINK",
    "artist:lesserafim": "LE SSERAFIM",
    "artist:straykids": "Stray Kids",
    # Coverage expansion — distinctive (coined) names only, to keep search-collision low (per note).
    "artist:itzy": "ITZY",
    "artist:gidle": "(G)I-DLE",
    "artist:enhypen": "ENHYPEN",
    "artist:nmixx": "NMIXX",
    "artist:riize": "RIIZE",
    "artist:zerobaseone": "ZEROBASEONE",
    "artist:txt": "Tomorrow X Together",
    "artist:ateez": "ATEEZ",
    "artist:babymonster": "BABYMONSTER",
    "artist:illit": "ILLIT",
}

# 소속사 disambiguation hint: entity_id -> agency CORE name. Wikidata's P264 can list several labels
# (e.g. a foreign distribution label first — the BTS/Avex bug); the hint picks the RIGHT one among the
# LIVE values. It never fabricates — the value still comes from Wikidata, and fetch() falls back to
# the first label if nothing matches. (The 3 curated acts also carry this in wikidata `_CURATED`.)
AGENCY_HINTS = {
    "artist:bts": "Big Hit",
    "artist:newjeans": "ADOR",
    "artist:aespa": "SM Entertainment",
    "artist:blackpink": "YG",
    "artist:lesserafim": "Source",
    "artist:straykids": "JYP",
    "artist:itzy": "JYP",
    "artist:gidle": "Cube",
    "artist:enhypen": "Belift",
    "artist:nmixx": "JYP",
    "artist:riize": "SM Entertainment",
    "artist:zerobaseone": "WakeOne",
    "artist:txt": "Big Hit",
    "artist:ateez": "KQ",
    "artist:babymonster": "YG",
    "artist:illit": "Belift",
}
