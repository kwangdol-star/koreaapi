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
    # Batch 2 — distinctive (coined) names.
    "artist:oneus": "ONEUS",
    "artist:sf9": "SF9",
    "artist:cravity": "CRAVITY",
    "artist:p1harmony": "P1Harmony",
    "artist:stayc": "STAYC",
    "artist:apink": "Apink",
    "artist:taemin": "TAEMIN",
    "artist:sunmi": "SUNMI",
    "artist:chungha": "Chung Ha",
    "artist:viviz": "VIVIZ",
    # Batch 2 — collision-prone (real-word / real-name overlap): bilingual identity in wikidata._CURATED.
    "artist:kissoflife": "Kiss of Life",
    "artist:ohmygirl": "Oh My Girl",
    "artist:everglow": "EVERGLOW",
    "artist:zico": "ZICO",
    "artist:boynextdoor": "BOYNEXTDOOR",
    # Batch 3 — distinctive.
    "artist:akmu": "AKMU",
    "artist:nctdream": "NCT Dream",
    "artist:triples": "tripleS",
    "artist:xdinaryheroes": "Xdinary Heroes",
    "artist:qwer": "QWER",
    "artist:plave": "PLAVE",
    "artist:younha": "Younha",
    # Batch 3 — collision-prone (bilingual identity in wikidata._CURATED).
    "artist:boa": "BoA",
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
    "artist:oneus": "RBW",
    "artist:sf9": "FNC",
    "artist:cravity": "Starship",
    "artist:p1harmony": "FNC",
    "artist:stayc": "High Up",
    "artist:apink": "IST",
    "artist:taemin": "SM Entertainment",
    "artist:sunmi": "ABYSS",
    "artist:chungha": "MNH",
    "artist:viviz": "Big Planet",
    "artist:akmu": "YG",
    "artist:nctdream": "SM Entertainment",
    "artist:triples": "Modhaus",
    "artist:xdinaryheroes": "JYP",
    "artist:qwer": "3Y",
    "artist:plave": "VLAST",
    "artist:younha": "C9",
    # webtoon publisher/platform hints (P123 disambiguation; falls back to the first label)
    "webtoon:sololeveling": "Kakao",
    "webtoon:towerofgod": "Naver",
    "webtoon:thegodofhighschool": "Naver",
    "webtoon:noblesse": "Naver",
    "webtoon:omniscientreader": "Naver",
    "webtoon:yumiscells": "Naver",
    "webtoon:cheeseinthetrap": "Naver",
    # place region hints (P131 located-in disambiguation; falls back to the first value)
    "place:gyeongbokgung": "Seoul",
    "place:nseoultower": "Seoul",
    "place:bukchonhanok": "Seoul",
    "place:changdeokgung": "Seoul",
    "place:lotteworldtower": "Seoul",
    "place:myeongdong": "Seoul",
    "place:gwangjangmarket": "Seoul",
    "place:cheonggyecheon": "Seoul",
    "place:bulguksa": "Gyeongju",
    "place:seongsanilchulbong": "Jeju",
    "place:hallasan": "Jeju",
    "place:haeundae": "Busan",
    "place:gamcheon": "Busan",
    "place:jeonjuhanok": "Jeonju",
    "place:everland": "Yongin",
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
    # Batch 2 — distinctive titles.
    "drama:mymister": "My Mister",
    "drama:movetoheaven": "Move to Heaven",
    "drama:mrqueen": "Mr. Queen",
    "drama:theuncannycounter": "The Uncanny Counter",
    "drama:alchemyofsouls": "Alchemy of Souls",
    "drama:queenoftears": "Queen of Tears",
    "drama:reply1997": "Reply 1997",
    "drama:misaeng": "Misaeng",
    # Batch 3.
    "drama:gyeongseongcreature": "Gyeongseong Creature",
    "drama:marrymyhusband": "Marry My Husband",
    "drama:maskgirl": "Mask Girl",
    "drama:the8show": "The 8 Show",
    "drama:lovelyrunner": "Lovely Runner",
    "drama:kingtheland": "King the Land",
    "drama:crashcourseinromance": "Crash Course in Romance",
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
    # Batch 2 — distinctive titles.
    "film:thegangsterthecopthedevil": "The Gangster, the Cop, the Devil",
    "film:exhuma": "Exhuma",
    "film:alongwiththegods": "Along with the Gods",
    # Batch 2 — collision-prone (real-word overlap): bilingual identity in wikidata._CURATED.
    "film:ahardday": "A Hard Day",
    "film:svaha": "Svaha",
    # Batch 3.
    "film:concreteutopia": "Concrete Utopia",
    "film:alienoid": "Alienoid",
    "film:killboksoon": "Kill Boksoon",
    "film:1212theday": "12.12: The Day",
    # Batch 3 — collision-prone (bilingual identity in wikidata._CURATED).
    "film:smugglers": "Smugglers",
}

# K-webtoon vertical (4th vertice, same engine, namespace-switched): the `webtoon:` namespace maps to
# publisher/platform (P123), publication date (P577/P571), author(s) (P50). Distinctive titles; the
# generic-word one (Lookism) is bilingually pinned in wikidata._CURATED.
WEBTOONS = {
    "webtoon:sololeveling": "Solo Leveling",
    "webtoon:towerofgod": "Tower of God",
    "webtoon:thegodofhighschool": "The God of High School",
    "webtoon:noblesse": "Noblesse",
    "webtoon:omniscientreader": "Omniscient Reader",
    "webtoon:yumiscells": "Yumi's Cells",
    "webtoon:cheeseinthetrap": "Cheese in the Trap",
    "webtoon:lookism": "Lookism",  # bilingual identity in wikidata._CURATED (vs the concept "lookism")
}

# Travel vertical: Korean destinations / attractions (Wikidata-verifiable). `place:` namespace maps
# to located-in (P131) as the region edge + inception (P571). Distinctive names (low collision).
PLACES = {
    "place:gyeongbokgung": "Gyeongbokgung",
    "place:nseoultower": "N Seoul Tower",
    "place:bukchonhanok": "Bukchon Hanok Village",
    "place:changdeokgung": "Changdeokgung",
    "place:lotteworldtower": "Lotte World Tower",
    "place:myeongdong": "Myeongdong",
    "place:gwangjangmarket": "Gwangjang Market",
    "place:cheonggyecheon": "Cheonggyecheon",
    "place:bulguksa": "Bulguksa",
    "place:seongsanilchulbong": "Seongsan Ilchulbong",
    "place:hallasan": "Hallasan",
    "place:haeundae": "Haeundae Beach",
    "place:gamcheon": "Gamcheon Culture Village",
    "place:jeonjuhanok": "Jeonju Hanok Village",
    "place:everland": "Everland",
}

# Food vertical: Korean dishes/cuisine (Wikidata-verifiable). `food:` is cross-verified by NAME only
# (a dish has no stable agency/date/people edge). Distinctive romanized names; the lone real-word
# collision (Sundae) is bilingually pinned in wikidata._CURATED.
FOODS = {
    "food:bibimbap": "Bibimbap",
    "food:kimchi": "Kimchi",
    "food:tteokbokki": "Tteokbokki",
    "food:bulgogi": "Bulgogi",
    "food:samgyeopsal": "Samgyeopsal",
    "food:japchae": "Japchae",
    "food:naengmyeon": "Naengmyeon",
    "food:kimbap": "Gimbap",
    "food:sundubujjigae": "Sundubu-jjigae",
    "food:galbi": "Galbi",
    "food:jjajangmyeon": "Jajangmyeon",
    "food:dakgalbi": "Dak-galbi",
    "food:hotteok": "Hotteok",
    "food:bingsu": "Patbingsu",
    "food:gochujang": "Gochujang",
    "food:kimchijjigae": "Kimchi-jjigae",
    "food:makgeolli": "Makgeolli",
    "food:soju": "Soju",
    "food:sundae": "Sundae",  # bilingual identity in wikidata._CURATED (vs the ice-cream "sundae")
}

# Every verified entity across all verticals: id -> canonical name (search + identity term).
NAMES = {**ARTISTS, **DRAMAS, **FILMS, **WEBTOONS, **PLACES, **FOODS}
