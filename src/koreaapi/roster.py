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
    # Batch 4 — distinctive coined names (agency hints in AGENCY_HINTS).
    "artist:btob": "BTOB",
    "artist:wjsn": "WJSN",
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
    "artist:btob": "Cube",
    "artist:wjsn": "Starship",
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
    "place:seoraksan": "Gangwon",
    "place:seokguram": "Gyeongju",
    "place:jongmyo": "Seoul",
    "place:deoksugung": "Seoul",
    "place:changgyeonggung": "Seoul",
    "place:ddp": "Seoul",
    "place:namiisland": "Chuncheon",
    "place:hwaseong": "Suwon",
    "place:hahoe": "Andong",
    "place:jagalchi": "Busan",
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
    # Batch 4 — distinctive titles; the common-word one (Kingdom) pinned in _CURATED.
    "drama:hellbound": "Hellbound",
    "drama:dp": "D.P.",
    "drama:juvenilejustice": "Juvenile Justice",
    "drama:kingdom": "Kingdom",        # bilingual in _CURATED (vs the common word)
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
    # Batch 4 — acclaimed classics (distinctive titles; collision-prone ones pinned in _CURATED).
    "film:snowpiercer": "Snowpiercer",
    "film:theroundup": "The Roundup",
    "film:secretsunshine": "Secret Sunshine",
    "film:mrvengeance": "Sympathy for Mr. Vengeance",
    "film:ladyvengeance": "Sympathy for Lady Vengeance",
    "film:jsa": "Joint Security Area",
    "film:tazza": "Tazza",
    "film:peninsula": "Peninsula",
    "film:thehost": "The Host",        # bilingual in _CURATED (vs the concept/other films)
    "film:burning": "Burning",         # bilingual in _CURATED
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
    # seed expansion (#2). Common-phrase titles pinned bilingually in wikidata._CURATED.
    "webtoon:eleceed": "Eleceed",
    "webtoon:killingstalking": "Killing Stalking",
    "webtoon:annarasumanara": "Annarasumanara",
    "webtoon:truebeauty": "True Beauty",     # bilingual in _CURATED
    "webtoon:sweethome": "Sweet Home",       # bilingual in _CURATED
    "webtoon:windbreaker": "Wind Breaker",   # bilingual in _CURATED
    "webtoon:hardcorelevelingwarrior": "Hardcore Leveling Warrior",
    "webtoon:semanticerror": "Semantic Error",   # bilingual in _CURATED (vs the programming term)
    "webtoon:thesoundofyourheart": "The Sound of Your Heart",
    "webtoon:girlsofthewilds": "Girls of the Wild's",
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
    # seed expansion — famous attractions (all P625-coordinate-bearing -> map + geo JSON-LD)
    "place:seoraksan": "Seoraksan",
    "place:seokguram": "Seokguram",
    "place:jongmyo": "Jongmyo",
    "place:deoksugung": "Deoksugung",
    "place:changgyeonggung": "Changgyeonggung",
    "place:ddp": "Dongdaemun Design Plaza",
    "place:namiisland": "Nami Island",
    "place:hwaseong": "Hwaseong Fortress",
    "place:hahoe": "Hahoe Folk Village",
    "place:jagalchi": "Jagalchi Market",
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
    # fusion / modern Korean food trends (documented on Wikipedia → verifiable)
    "food:koreancorndog": "Korean corn dog",
    "food:budaejjigae": "Budae-jjigae",
    "food:koreanfriedchicken": "Korean fried chicken",
    "food:dalgona": "Dalgona",
    "food:dalgonacoffee": "Dalgona coffee",
    # more staples / soups / classics (seed expansion)
    "food:samgyetang": "Samgyetang",
    "food:seolleongtang": "Seolleongtang",
    "food:gamjatang": "Gamjatang",
    "food:jjamppong": "Jjamppong",
    "food:kalguksu": "Kalguksu",
    "food:doenjangjjigae": "Doenjang-jjigae",
    "food:tteokguk": "Tteokguk",
    "food:mandu": "Mandu",
    "food:pajeon": "Pajeon",
    "food:yukhoe": "Yukhoe",
    "food:dakbokkeumtang": "Dak-bokkeum-tang",
    "food:songpyeon": "Songpyeon",
}

# Curated EDITORIAL spice rating (none / mild / medium / hot / very hot) — Wikidata has no spiciness
# property, so this is a KoreaAPI editorial classification (clearly labeled as such on the page, NOT
# cross-verified). It answers the #1 foreigner food question ("is it spicy?"). The dish NAME stays
# cross-verified; only this rating is editorial.
FOOD_SPICE = {
    "food:bibimbap": "medium", "food:kimchi": "medium", "food:tteokbokki": "hot",
    "food:bulgogi": "mild", "food:samgyeopsal": "mild", "food:japchae": "mild",
    "food:naengmyeon": "mild", "food:kimbap": "mild", "food:sundubujjigae": "hot",
    "food:galbi": "mild", "food:jjajangmyeon": "mild", "food:dakgalbi": "hot",
    "food:hotteok": "none", "food:bingsu": "none", "food:gochujang": "very hot",
    "food:kimchijjigae": "hot", "food:makgeolli": "none", "food:soju": "none",
    "food:sundae": "mild", "food:koreancorndog": "mild", "food:budaejjigae": "hot",
    "food:koreanfriedchicken": "medium", "food:dalgona": "none", "food:dalgonacoffee": "none",
    "food:samgyetang": "mild", "food:seolleongtang": "mild", "food:gamjatang": "medium",
    "food:jjamppong": "hot", "food:kalguksu": "mild", "food:doenjangjjigae": "mild",
    "food:tteokguk": "mild", "food:mandu": "mild", "food:pajeon": "mild",
    "food:yukhoe": "mild", "food:dakbokkeumtang": "hot", "food:songpyeon": "none",
}

# Curated EDITORIAL dietary tag (#3) — like spice, Wikidata has no clean property, so this is a KoreaAPI
# editorial note (clearly labeled, NOT cross-verified). Foreigner-relevant ("can I eat this?"). Short
# tags: vegan / vegetarian / vegetarian option / contains meat / contains seafood / varies.
FOOD_VEG = {
    "food:bibimbap": "vegetarian (ask, often has egg/beef)", "food:japchae": "vegetarian",
    "food:kimchi": "vegan (some use fish sauce)", "food:tteokbokki": "vegetarian (often)",
    "food:naengmyeon": "contains meat (beef broth)", "food:bulgogi": "contains meat (beef)",
    "food:samgyeopsal": "contains meat (pork)", "food:galbi": "contains meat",
    "food:dakgalbi": "contains meat (chicken)", "food:samgyetang": "contains meat (chicken)",
    "food:seolleongtang": "contains meat (beef)", "food:gamjatang": "contains meat (pork)",
    "food:jjajangmyeon": "contains meat (pork)", "food:jjamppong": "contains seafood",
    "food:yukhoe": "contains meat (raw beef)", "food:mandu": "varies (meat or veggie)",
    "food:pajeon": "varies (seafood common)", "food:hotteok": "vegetarian",
    "food:bingsu": "vegetarian", "food:songpyeon": "vegetarian", "food:soju": "vegan",
    "food:makgeolli": "vegan", "food:gimbap": "varies", "food:sundubujjigae": "vegetarian option",
    "food:doenjangjjigae": "vegetarian option", "food:kimchijjigae": "contains meat (often pork)",
}

# Company vertical: major Korean companies/brands (Wikidata-verifiable). `company:` maps to industry
# (P452) + founded (P571). Distinctive brand names (low collision); these connect to label hubs.
COMPANIES = {
    "company:samsung": "Samsung Electronics",
    "company:hyundai": "Hyundai Motor Company",
    "company:lg": "LG Electronics",
    "company:skhynix": "SK Hynix",
    "company:naver": "Naver",
    "company:kakao": "Kakao",
    "company:coupang": "Coupang",
    "company:krafton": "Krafton",
    "company:nexon": "Nexon",
    "company:celltrion": "Celltrion",
    "company:posco": "POSCO",
    "company:cj": "CJ Group",
    # batch 2 — the K-entertainment majors (also the 소속사 hubs) + more chaebols / global names.
    "company:hybe": "HYBE",
    "company:sment": "SM Entertainment",
    "company:jypent": "JYP Entertainment",
    "company:ygent": "YG Entertainment",
    "company:kia": "Kia",
    "company:lotte": "Lotte Corporation",
    "company:koreanair": "Korean Air",
    "company:shinsegae": "Shinsegae",
}

# Brand vertical: Korean consumer brands, K-beauty-led (Wikidata-verifiable). `brand:` maps to
# owned-by (P127, the parent group) + inception (P571). Collision-prone names bilingually pinned.
BRANDS = {
    "brand:laneige": "Laneige",
    "brand:sulwhasoo": "Sulwhasoo",
    "brand:cosrx": "COSRX",
    "brand:drjart": "Dr.Jart+",
    "brand:missha": "Missha",
    "brand:etudehouse": "Etude House",
    "brand:mamonde": "Mamonde",
    "brand:tonymoly": "Tony Moly",
    "brand:banilaco": "Banila Co",
    "brand:innisfree": "Innisfree",        # bilingual in _CURATED (vs the Yeats poem / place)
    "brand:naturerepublic": "Nature Republic",  # bilingual in _CURATED (generic phrase)
    "brand:thefaceshop": "The Face Shop",  # bilingual in _CURATED (generic phrase)
    # "Korea gone global" — Korean F&B brands/franchises that expanded overseas (the foreigner-facing
    # angle): bakeries, fried chicken, frozen/instant exports. Owned-by P127 -> the parent group.
    "brand:parisbaguette": "Paris Baguette",
    "brand:touslesjours": "Tous les Jours",
    "brand:genesisbbq": "Genesis BBQ",
    "brand:bibigo": "Bibigo",
    "brand:shinramyun": "Shin Ramyun",
    "brand:buldakramen": "Buldak-bokkeum-myeon",
}

# Book vertical: Korean literature (Wikidata-verifiable). `book:` maps to publisher (P123) +
# publication date (P577) + author(s) (P50). Generic-title novels bilingually pinned in _CURATED.
BOOKS = {
    "book:kimjiyoung": "Kim Ji-young, Born 1982",
    "book:ihavetheright": "I Have the Right to Destroy Myself",
    "book:thehenwhodreamed": "The Hen Who Dreamed She Could Fly",
    "book:theplotters": "The Plotters",
    "book:thevegetarian": "The Vegetarian",        # bilingual in _CURATED (vs the concept)
    "book:humanacts": "Human Acts",                # bilingual in _CURATED
    "book:almond": "Almond",                       # bilingual in _CURATED (vs the nut)
    "book:pleaselookaftermom": "Please Look After Mom",  # bilingual in _CURATED
    # seed expansion (#2). Common-phrase titles pinned bilingually in wikidata._CURATED.
    "book:pachinko": "Pachinko",                    # bilingual in _CURATED
    "book:cursedbunny": "Cursed Bunny",
    "book:greeklessons": "Greek Lessons",           # bilingual in _CURATED
    "book:whitebook": "The White Book",             # bilingual in _CURATED
    "book:loveinthebigcity": "Love in the Big City",  # bilingual in _CURATED
    "book:diaryofamurderer": "Diary of a Murderer",
    "book:thecourtdancer": "The Court Dancer",
    "book:theoldwomanwiththeknife": "The Old Woman with the Knife",
    "book:welcometohyunamdong": "Welcome to the Hyunam-dong Bookshop",
}

# History vertical: Korean dynasties / periods / events (canonical, Wikidata-verifiable). `history:`
# maps to start time (P580) / inception (P571). Distinctive names (low collision).
HISTORY = {
    "history:joseon": "Joseon",
    "history:goryeo": "Goryeo",
    "history:silla": "Silla",
    "history:goguryeo": "Goguryeo",
    "history:baekje": "Baekje",
    "history:gojoseon": "Gojoseon",
    "history:threekingdoms": "Three Kingdoms of Korea",
    "history:koreanwar": "Korean War",
    "history:march1": "March First Movement",
    "history:gwangju": "Gwangju Uprising",
    "history:koreanempire": "Korean Empire",
    "history:donghak": "Donghak Peasant Revolution",
}

# Heritage vertical: Korean cultural heritage + traditional arts/music/국악 (canonical, verifiable).
# `heritage:` is name-anchored (+ optional inception P571). Distinctive romanized terms (low collision).
HERITAGE = {
    "heritage:hunminjeongeum": "Hunminjeongeum",
    "heritage:tripitakakoreana": "Tripitaka Koreana",
    "heritage:pansori": "Pansori",
    "heritage:samulnori": "Samul nori",
    "heritage:gayageum": "Gayageum",
    "heritage:taekwondo": "Taekwondo",
    "heritage:hanbok": "Hanbok",
    "heritage:talchum": "Talchum",
    "heritage:minhwa": "Minhwa",
    "heritage:koreanceladon": "Korean celadon",
    "heritage:jongmyojerye": "Jongmyo jerye",
    "heritage:kimjang": "Kimjang",
    # 건축 (architecture) + 미술/공예 (fine art & craft) — fold the culture-ToC's art/architecture
    # sections in here rather than spinning up thin verticals.
    "heritage:hanok": "Hanok",
    "heritage:ondol": "Ondol",
    "heritage:najeonchilgi": "Najeonchilgi",
    "heritage:dancheong": "Dancheong",
    "heritage:buncheong": "Buncheong",
}

# Folklore vertical: Korean legends / myths / shamanism / ghosts (설화·민담·신화·무속·귀신). `folklore:`
# is cross-verified by NAME only. English forms match the Wikipedia/Wikidata titles where they differ.
FOLKLORE = {
    "folklore:dangun": "Dangun",
    "folklore:kumiho": "Kumiho",
    "folklore:dokkaebi": "Dokkaebi",
    "folklore:jeoseungsaja": "Jeoseung Saja",
    "folklore:koreanshamanism": "Korean shamanism",
    "folklore:chunhyangjeon": "Chunhyangga",
    "folklore:heungbujeon": "Heungbujeon",
    "folklore:simcheongjeon": "Simcheongga",
    "folklore:honggildong": "The Tale of Hong Gildong",
    "folklore:haetae": "Haetae",
    "folklore:bulgasari": "Bulgasari",
    "folklore:samshin": "Samshin",
}

# Medical vertical: major Korean hospitals / medical centers (Wikidata-verifiable). `medical:` maps to
# located-in P131 (the region) + inception P571. Distinctive institution names (low collision); the
# wider universe (tertiary hospitals nationwide) is filled by auto-discovery (hospital class, country SK).
MEDICAL = {
    "medical:snuh": "Seoul National University Hospital",
    "medical:asanmedical": "Asan Medical Center",
    "medical:samsungmedical": "Samsung Medical Center",
    "medical:severance": "Severance Hospital",
    "medical:seoulstmarys": "Seoul St. Mary's Hospital",
    "medical:koreauniv": "Korea University Medical Center",
    "medical:ajou": "Ajou University Hospital",
    "medical:gangnamseverance": "Gangnam Severance Hospital",
}

# Region vertical: South Korea + its first-level administrative divisions (광역자치단체) — the country
# article + 8 metropolitan-level cities + 9 provinces. `region:` is name-anchored (canonical, stable).
# The flagship 대한민국 (South Korea) is Q-id-pinned in wikidata._CURATED so the vertical is anchored.
REGION = {
    "region:southkorea": "South Korea",
    "region:seoul": "Seoul",
    "region:busan": "Busan",
    "region:incheon": "Incheon",
    "region:daegu": "Daegu",
    "region:daejeon": "Daejeon",
    "region:gwangju": "Gwangju",
    "region:ulsan": "Ulsan",
    "region:sejong": "Sejong",
    "region:gyeonggi": "Gyeonggi Province",
    "region:gangwon": "Gangwon Province",
    "region:northchungcheong": "North Chungcheong Province",
    "region:southchungcheong": "South Chungcheong Province",
    "region:northjeolla": "North Jeolla Province",
    "region:southjeolla": "South Jeolla Province",
    "region:northgyeongsang": "North Gyeongsang Province",
    "region:southgyeongsang": "South Gyeongsang Province",
    "region:jeju": "Jeju Province",
}

# Game vertical: Korean-developed video games (a major global K-export — "게임 강국"). `game:` maps to
# developer P178 (the studio: Nexon · NCSoft · Krafton · Smilegate · Pearl Abyss) + release date P577.
# Distinctive titles (low collision); the common-word titles (Lineage, Aion) are bilingually pinned in
# wikidata._CURATED. The wider catalogue is filled by auto-discovery (video-game class, origin SK).
GAMES = {
    "game:pubg": "PUBG: Battlegrounds",
    "game:maplestory": "MapleStory",
    "game:blackdesert": "Black Desert Online",
    "game:lostark": "Lost Ark",
    "game:dungeonfighter": "Dungeon Fighter Online",
    "game:ragnarokonline": "Ragnarok Online",
    "game:bladeandsoul": "Blade & Soul",
    "game:kartrider": "KartRider",
    "game:vindictus": "Vindictus",
    "game:lineage": "Lineage",          # bilingual in _CURATED (vs the concept "lineage")
    "game:aion": "Aion",                # bilingual in _CURATED (vs the common word)
}

# Show vertical: Korean variety / entertainment TV (방송 · 예능) — a major K-content export. `show:`
# maps to original network P449 + start date P580 + cast/host P161 (the MC hubs feed the person graph).
# Distinctive titles; the common-phrase one (Running Man) is bilingually pinned in wikidata._CURATED.
SHOWS = {
    "show:runningman": "Running Man",            # bilingual in _CURATED (vs the concept / film)
    "show:infinitechallenge": "Infinite Challenge",
    "show:2days1night": "2 Days & 1 Night",
    "show:knowingbros": "Knowing Bros",
    "show:physical100": "Physical: 100",
    "show:kingofmaskedsinger": "King of Mask Singer",
    "show:newjourneytothewest": "New Journey to the West",
    "show:ilivealone": "I Live Alone",
    "show:produce101": "Produce 101",
    "show:streetwomanfighter": "Street Woman Fighter",
}

# Animation vertical: Korean animation (애니메이션) — globally syndicated (Pororo "뽀통령", Baby Shark).
# `animation:` maps to production company P272 + publication date P577. Distinctive titles; the common-
# word one (Larva) is bilingually pinned in wikidata._CURATED.
ANIMATIONS = {
    "animation:pororo": "Pororo the Little Penguin",
    "animation:tayo": "Tayo the Little Bus",
    "animation:robocarpoli": "Robocar Poli",
    "animation:larva": "Larva",                  # bilingual in _CURATED (vs the insect)
    "animation:babyshark": "Baby Shark",
    "animation:pucca": "Pucca",
    "animation:hellojadoo": "Hello Jadoo",
    "animation:dooly": "Dooly the Little Dinosaur",
    # seed expansion (#2) — acclaimed Korean animated films. Seoul Station pinned (vs the station).
    "animation:leafie": "Leafie, a Hen into the Wild",
    "animation:thekingofpigs": "The King of Pigs",
    "animation:yobi": "Yobi, the Five Tailed Fox",
    "animation:satellitegirl": "The Satellite Girl and Milk Cow",
    "animation:seoulstation": "Seoul Station",   # bilingual in _CURATED (vs the railway station)
    "animation:greendays": "Green Days: Dinosaur and I",
    "animation:catchteenieping": "Catch! Teenieping",
    "animation:thehauntedhouse": "The Haunted House",
}

# University vertical: major Korean universities (교육) — Wikidata-verifiable, foreigner-searched.
# `university:` maps to located-in P131 (region) + inception P571 (founded). Distinctive names. The
# wider set is filled by auto-discovery (university class, country SK).
UNIVERSITIES = {
    "university:snu": "Seoul National University",
    "university:kaist": "KAIST",
    "university:yonsei": "Yonsei University",
    "university:korea": "Korea University",
    "university:postech": "Pohang University of Science and Technology",
    "university:sungkyunkwan": "Sungkyunkwan University",
    "university:hanyang": "Hanyang University",
    "university:kyunghee": "Kyung Hee University",
    "university:ewha": "Ewha Womans University",
    "university:sogang": "Sogang University",
}

# Classic vertical: Korean classical texts / historical records / treatises (고전 · 사료) — the famous,
# Wikipedia/Wikidata-backed ones (many are UNESCO Memory of the World / National Treasures). `classic:`
# maps to author P50 + compilation/publication date. Distinctive romanized titles (low collision).
CLASSICS = {
    "classic:samguksagi": "Samguk Sagi",
    "classic:samgukyusa": "Samguk Yusa",
    "classic:goryeosa": "Goryeosa",
    "classic:annalsofjoseon": "Annals of the Joseon Dynasty",
    "classic:seungjeongwonilgi": "Seungjeongwon ilgi",
    "classic:donguibogam": "Dongui Bogam",
    "classic:gyeonggukdaejeon": "Gyeongguk daejeon",
    "classic:nanjungilgi": "Nanjung ilgi",
    "classic:mokminsimseo": "Mongmin Simseo",
    "classic:taengniji": "Taengniji",
    "classic:daedongyeojido": "Daedongyeojido",
    "classic:jingbirok": "Jingbirok",
    # batch 2 — more canonical records / treatises (several UNESCO Memory of the World)
    "classic:goryeosajeoryo": "Goryeosa jeoryo",
    "classic:jikji": "Jikji",
    "classic:uigwe": "Uigwe",
    "classic:ilseongnok": "Ilseongnok",
    "classic:hanjungnok": "Hanjungnok",
    "classic:jasaneobo": "Jasaneobo",
    "classic:jibongyuseol": "Jibong yuseol",
    "classic:muyedobotongji": "Muyedobotongji",
}

# Every verified entity across all verticals: id -> canonical name (search + identity term).
NAMES = {**ARTISTS, **DRAMAS, **FILMS, **WEBTOONS, **PLACES, **FOODS, **COMPANIES, **BRANDS,
         **BOOKS, **HISTORY, **HERITAGE, **FOLKLORE, **MEDICAL, **REGION, **GAMES,
         **SHOWS, **ANIMATIONS, **UNIVERSITIES, **CLASSICS}

# Institutional certification — the strongest, NON-REPLICABLE moat. An organization (agency / brand /
# museum / studio) officially vouches for an entity's data; that record then ranks ABOVE "triple
# cross-verified" (an authority staked its name — faster + more official than a wiki edit, and a
# competitor re-scraping Wikidata can never reproduce it). SEED MODEL: empty until a real partnership
# lands, then it's a one-line entry per entity. entity_id -> {"by": org, "date": "YYYY-MM-DD", "url"?}.
# (Deliberately empty — we do not fabricate a certification that hasn't happened.)
CERTIFIED: dict[str, dict] = {
    # "artist:bts": {"by": "HYBE", "date": "2026-06-01", "url": "https://hybecorp.com/..."},  # example
}
