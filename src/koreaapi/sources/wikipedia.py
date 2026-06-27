"""Wikipedia source adapter (real source #2) — an independent cross-check for the name.

Fetches an article's English title + its Korean interlanguage link via the MediaWiki action
API (credential-free, same egress pattern as Wikidata; works on deploy / GitHub runners).
Pairing this with Wikidata lets the ingestion CROSS-VERIFY the bilingual name from two
independent sources — when they agree the Skill Score clears the single-source cap
(verification is the product). The PARSE step is pure + fixture-tested offline.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .wikidata import _http_get_json  # shared retry+backoff GET (rate-limit resilient)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_UA = {
    "User-Agent": "KoreaAPI/0.1 (https://github.com/kwangdol-star/koreaapi) python-urllib"
}

# entity_id -> English Wikipedia article title (curated fast path; else derive from the id).
_TITLES = {
    "artist:bts": "BTS",
    "artist:newjeans": "NewJeans",
    "artist:aespa": "Aespa",
    "artist:blackpink": "Blackpink",
    "artist:lesserafim": "Le Sserafim",
    "artist:straykids": "Stray Kids",
    "artist:itzy": "Itzy",
    "artist:gidle": "(G)I-dle",
    "artist:enhypen": "Enhypen",
    "artist:nmixx": "NMIXX",
    "artist:riize": "Riize",
    "artist:zerobaseone": "Zerobaseone",
    "artist:txt": "Tomorrow X Together",
    "artist:ateez": "Ateez",
    "artist:babymonster": "BabyMonster",
    "artist:illit": "Illit (group)",
    "artist:mamamoo": "Mamamoo",
    "artist:monstax": "Monsta X",
    "artist:gfriend": "GFriend",
    "artist:kep1er": "Kep1er",
    "artist:shinee": "Shinee",
    "artist:tvxq": "TVXQ",
    "artist:2ne1": "2NE1",
    "artist:psy": "Psy",
    "artist:gdragon": "G-Dragon",
    "artist:taeyeon": "Taeyeon",
    "artist:fromis9": "Fromis 9",
    "artist:girlsgeneration": "Girls' Generation",
    "artist:superjunior": "Super Junior",
    "artist:theboyz": "The Boyz (South Korean band)",
    "artist:twice": "Twice (group)",
    "artist:seventeen": "Seventeen (South Korean band)",
    "artist:redvelvet": "Red Velvet (group)",
    "artist:treasure": "Treasure (group)",
    "artist:ive": "Ive (group)",
    "artist:nct": "NCT (group)",
    "artist:exo": "Exo (band)",
    "artist:iu": "IU (singer)",
    "artist:oneus": "Oneus",
    "artist:sf9": "SF9",
    "artist:cravity": "Cravity",
    "artist:p1harmony": "P1Harmony",
    "artist:stayc": "STAYC",
    "artist:apink": "Apink",
    "artist:taemin": "Taemin",
    "artist:sunmi": "Sunmi",
    "artist:chungha": "Chung Ha",
    "artist:viviz": "Viviz",
    "artist:kissoflife": "Kiss of Life (group)",
    "artist:ohmygirl": "Oh My Girl",
    "artist:everglow": "Everglow (group)",
    "artist:zico": "Zico (rapper)",
    "artist:boynextdoor": "Boynextdoor",
    "drama:squidgame": "Squid Game",
    "drama:crashlandingonyou": "Crash Landing on You",
    "drama:itaewonclass": "Itaewon Class",
    "drama:extraordinaryattorneywoo": "Extraordinary Attorney Woo",
    "drama:reply1988": "Reply 1988",
    "drama:theglory": "The Glory (TV series)",
    "drama:vincenzo": "Vincenzo (TV series)",
    "drama:hospitalplaylist": "Hospital Playlist",
    "drama:itsokaytonotbeokay": "It's Okay to Not Be Okay",
    "drama:thekingeternalmonarch": "The King: Eternal Monarch",
    "drama:hometowncha": "Hometown Cha-Cha-Cha",
    "drama:twentyfivetwentyone": "Twenty-Five Twenty-One",
    "drama:businessproposal": "Business Proposal (TV series)",
    "drama:allofusaredead": "All of Us Are Dead",
    "drama:descendantsofthesun": "Descendants of the Sun",
    "drama:goblin": "Guardian: The Lonely and Great God",
    "drama:mylovefromthestar": "My Love from the Star",
    "drama:mrsunshine": "Mr. Sunshine (TV series)",
    "drama:mymister": "My Mister",
    "drama:movetoheaven": "Move to Heaven",
    "drama:mrqueen": "Mr. Queen",
    "drama:theuncannycounter": "The Uncanny Counter",
    "drama:alchemyofsouls": "Alchemy of Souls",
    "drama:queenoftears": "Queen of Tears",
    "drama:reply1997": "Reply 1997",
    "drama:misaeng": "Misaeng: Incomplete Life",
    "film:traintobusan": "Train to Busan",
    "film:thehandmaiden": "The Handmaiden",
    "film:decisiontoleave": "Decision to Leave",
    "film:memoriesofmurder": "Memories of Murder",
    "film:thewailing": "The Wailing (film)",
    "film:parasite": "Parasite (2019 film)",
    "film:oldboy": "Oldboy (2003 film)",
    "film:okja": "Okja",
    "film:ataxidriver": "A Taxi Driver",
    "film:isawthedevil": "I Saw the Devil",
    "film:themanfromnowhere": "The Man from Nowhere (film)",
    "film:thekingandtheclown": "The King and the Clown",
    "film:springsummerfall": "Spring, Summer, Fall, Winter... and Spring",
    "film:abittersweetlife": "A Bittersweet Life",
    "film:thegoodthebadtheweird": "The Good, the Bad, the Weird",
    "film:thegangsterthecopthedevil": "The Gangster, the Cop, the Devil",
    "film:exhuma": "Exhuma",
    "film:alongwiththegods": "Along with the Gods: The Two Worlds",
    "film:ahardday": "A Hard Day (2014 film)",
    "film:svaha": "Svaha: The Sixth Finger",
}


def parse_page(raw: dict, entity_id: str, kind: str) -> dict:
    """Pure: turn a MediaWiki `query` response (title + ko langlink) into our payload shape."""
    pages = raw.get("query", {}).get("pages", [])
    if not pages:
        raise ValueError("no page in Wikipedia response")
    page = pages[0]
    if page.get("missing"):
        raise ValueError("Wikipedia page missing")
    en = page.get("title")
    ko = None
    for ll in page.get("langlinks", []):
        if ll.get("lang") == "ko":
            ko = ll.get("title")
            break
    if not en and not ko:
        raise ValueError("no title in Wikipedia response")
    return {
        "name_ko": ko or en,
        "name_en_official": en,
        "name_romanized": None,
        "name_en_source": "official" if en else "llm",
        "name_en_confidence": "high" if en else "low",
        "summary_en": f"{en or ko} - {kind} (Wikipedia).",
        "summary_ko": f"{ko or en} - {kind} (위키백과).",
    }


class WikipediaSource:
    name = "Wikipedia"
    is_fallback = False

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        # entity_id -> article title for ids outside the curated map (e.g. swept labelmates).
        self._aliases: dict[str, str] = aliases or {}

    def _title(self, entity_id: str) -> str:
        return _TITLES.get(entity_id) or self._aliases.get(entity_id) or entity_id.split(":", 1)[-1].strip()

    def _url(self, title: str) -> str:
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "titles": title,
                "prop": "langlinks",
                "lllang": "ko",
                "lllimit": "1",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
        )
        return f"{WIKIPEDIA_API}?{query}"

    def _http_get(self, url: str) -> dict:
        return _http_get_json(url, _UA)

    async def fetch(self, entity_id: str, kind: str) -> dict:
        title = self._title(entity_id)
        raw = await asyncio.to_thread(self._http_get, self._url(title))
        payload = parse_page(raw, entity_id, kind)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"payload": payload, "citation": f"Wikipedia {payload['name_en_official']} {ts}"}
