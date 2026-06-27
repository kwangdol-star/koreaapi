"""The roster - entity_id -> canonical name (the live-resolution search term).

These are NOT Q-ids. Q-ids are resolved LIVE on the open network (GitHub runners) via
wbsearchentities / Wikipedia and cross-verified, never hardcoded unverified - that is exactly
how a wrong id ("Q484203 = Arborka") slipped in before. The fetched name is then identity-
checked against this canonical name, so a wrong search resolution is rejected by graceful
degradation, never ingested.

Keep names DISTINCTIVE (low search-collision); a name that also matches an unrelated entity
could pass the name guard. For collision-prone-but-important acts/titles (TWICE, Parasite, ...)
the *bilingual* identity (ko + en) is pinned in sources/wikidata.py `_CURATED`, so the strict
identity guard there rejects a same-EN-label impostor (TREASURE -> 보물) by its Korean name -
worst case a miss, never a wrong record. The 3 hottest acts also carry verified Q-ids there.
"""

ARTISTS = {
    "artist:bts": "BTS",
    "artist:newjeans": "NewJeans",
    "artist:aespa": "aespa",
    "artist:blackpink": "BLACKPINK",
    "artist:lesserafim": "LE SSERAFIM",
    "artist:straykids": "Stray Kids",
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
    # Coverage expansion — distinctive (coined) names (low search-collision).
    "artist:mamamoo": "Mamamoo",
    "artist:monstax": "Monsta X",
    "artist:gfriend": "GFriend",
    "artist:kep1er": "Kep1er",
    "artist:shinee": "SHINee",
    "artist:tvxq": "TVXQ",
    "artist:2ne1": "2NE1",
    "artist:psy": "PSY",
    "artist:gdragon": "G-Dragon",
    "artist:taeyeon": "Taeyeon",
    "artist:fromis9": "fromis_9",
    "artist:girlsgeneration": "Girls' Generation",
    "artist:superjunior": "Super Junior",
    "artist:theboyz": "The Boyz",
    # Collision-prone but top-tier — bilingual identity pinned in wikidata._CURATED (strict guard).
    "artist:twice": "TWICE",
    "artist:seventeen": "SEVENTEEN",
    "artist:redvelvet": "Red Velvet",
    "artist:treasure": "TREASURE",
    "artist:ive": "IVE",
    "artist:nct": "NCT",
    "artist:exo": "EXO",
    "artist:iu": "IU",
}

# 소속사 disambiguation hint: entity_id -> agency CORE name. Wikidata's P264 can list several labels
# (e.g. a foreign distribution label first — the BTS/Avex bug); the hint picks the RIGHT one among the
# LIVE values. It never fabricates — the value still comes from Wikidata, and fetch() falls back to
# the first label if nothing matches. (Curated acts carry the hint in wikidata `_CURATED` instead.)
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
    "artist:mamamoo": "RBW",
    "artist:monstax": "Starship",
    "artist:gfriend": "Source",
    "artist:kep1er": "WakeOne",
    "artist:shinee": "SM Entertainment",
    "artist:tvxq": "SM Entertainment",
    "artist:2ne1": "YG",
    "artist:psy": "P Nation",
    "artist:gdragon": "Galaxy",
    "artist:taeyeon": "SM Entertainment",
    "artist:fromis9": "Pledis",
    "artist:girlsgeneration": "SM Entertainment",
    "artist:superjunior": "Label SJ",
    "artist:theboyz": "IST",
}

# K-drama vertical (Phase A breadth). Distinctive titles = low search-collision. Verified by the
# SAME engine (name cross-verify Wikidata + Wikipedia); the `drama:` namespace switches the source
# props (air date P577 instead of debut P571) and the JSON-LD type (TVSeries instead of MusicGroup).
DRAMAS = {
    "drama:squidgame": "Squid Game",
    "drama:crashlandingonyou": "Crash Landing on You",
    "drama:itaewonclass": "Itaewon Class",
    "drama:extraordinaryattorneywoo": "Extraordinary Attorney Woo",
    "drama:reply1988": "Reply 1988",
    # Coverage expansion — distinctive titles only (low collision).
    "drama:theglory": "The Glory",
    "drama:vincenzo": "Vincenzo",
    "drama:hospitalplaylist": "Hospital Playlist",
    "drama:itsokaytonotbeokay": "It's Okay to Not Be Okay",
    "drama:thekingeternalmonarch": "The King: Eternal Monarch",
    "drama:hometowncha": "Hometown Cha-Cha-Cha",
    "drama:twentyfivetwentyone": "Twenty-Five Twenty-One",
    "drama:businessproposal": "Business Proposal",
    "drama:allofusaredead": "All of Us Are Dead",
    "drama:descendantsofthesun": "Descendants of the Sun",
    "drama:goblin": "Guardian: The Lonely and Great God",
    "drama:mylovefromthestar": "My Love from the Star",
    "drama:mrsunshine": "Mr. Sunshine",
}

# K-film vertical (more K-culture breadth, same engine). Distinctive titles; the lone generic-but-
# essential title (Parasite, Oldboy) is bilingually pinned in wikidata._CURATED (strict guard).
FILMS = {
    "film:traintobusan": "Train to Busan",
    "film:thehandmaiden": "The Handmaiden",
    "film:decisiontoleave": "Decision to Leave",
    "film:memoriesofmurder": "Memories of Murder",
    "film:thewailing": "The Wailing",
    # Coverage expansion.
    "film:parasite": "Parasite",
    "film:oldboy": "Oldboy",
    "film:okja": "Okja",
    "film:ataxidriver": "A Taxi Driver",
    "film:isawthedevil": "I Saw the Devil",
    "film:themanfromnowhere": "The Man from Nowhere",
    "film:thekingandtheclown": "The King and the Clown",
    "film:springsummerfall": "Spring, Summer, Fall, Winter... and Spring",
    "film:abittersweetlife": "A Bittersweet Life",
    "film:thegoodthebadtheweird": "The Good, the Bad, the Weird",
}

# Every verified entity (artists + dramas + films): id -> canonical name (search + identity term).
NAMES = {**ARTISTS, **DRAMAS, **FILMS}
