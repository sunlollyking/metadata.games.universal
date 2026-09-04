"""Wikidata and Wikimedia Commons: pictures of the machines themselves.

Front ends put a drawing of the console and its logo beside a system's games.
Batocera keeps its own set, but they are SVG and Kodi's texture pipeline
cannot decode one, so they are no use here. Wikidata holds the same two
pictures for every machine worth naming -- a photograph under P18 and a logo
under P154 -- and Commons will rasterise an SVG on request, which gives a
transparent PNG logo and a photograph of the hardware, free and without a key.

This provider describes machines only. Games are far better served by the
catalogues that exist for them, and asking Wikidata about tens of thousands of
files would be neither polite nor useful.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from . import OnlineProvider, Request, platform_names

API_URL = "https://www.wikidata.org/w/api.php"

#: Commons renders a file at a given width, turning an SVG logo into a
#: transparent PNG on the way
FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width={}"

#: Wikimedia asks that a client say what it is
USER_AGENT = "kodi-metadata.games.universal/1.0 (+https://kodi.tv)"

TIMEOUT = 30

#: What a picture is called here, and how wide to ask for it
PICTURES = (("P18", "photo", 1280), ("P154", "clearlogo", 800))

#: Words that mark a search hit as a machine rather than a game, a company or
#: a film of the same name
MACHINE_WORDS = ("console", "computer", "handheld", "arcade", "microcomputer",
                 "game system", "video game", "home computer")

MANUFACTURER = "P176"

#: A machine is dated by when it was published; a few items carry only the
#: date the design came into being
DATES = ("P577", "P571")


def picture_url(filename: str, width: int) -> str:
    return FILE_URL.format(urllib.parse.quote(filename.replace(" ", "_")), width)


def first_value(claims: Dict[str, Any], prop: str) -> Optional[Any]:
    for claim in claims.get(prop) or []:
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") == "value" and "datavalue" in snak:
            return snak["datavalue"].get("value")
    return None


def release_year(claims: Dict[str, Any]) -> int:
    for prop in DATES:
        value = first_value(claims, prop)
        stamp = value.get("time") if isinstance(value, dict) else None
        if not isinstance(stamp, str) or len(stamp) < 5:
            continue
        try:
            return int(stamp[1:5])
        except ValueError:
            continue
    return 0


def label(entity: Dict[str, Any]) -> str:
    """An item's name. Wikidata keeps names that read the same in every
    language under "mul" rather than repeating them per language."""
    labels = entity.get("labels") or {}
    for language in ("en", "mul"):
        value = (labels.get(language) or {}).get("value")
        if value:
            return str(value)
    return ""


class WikidataProvider(OnlineProvider):
    """Pictures and a few facts for a machine, keyed on its name."""

    name = "wikidata"
    folder = "wikidata"

    def available(self, settings: Dict[str, Any]) -> bool:
        return True

    def find(self, request: Request) -> List[dict]:
        return []

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        return None

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        names = [n for n in platform_names(request) if n]
        if not names:
            return None

        key = "platform-" + names[0].lower().replace(" ", "-")
        cached = self.cache.load(key, request.cache_days())
        if cached is not None:
            return cached or None

        described = self._describe(names)
        self.cache.save(key, described or {})
        return described

    def _describe(self, names: List[str]) -> Optional[Dict[str, Any]]:
        item = self._machine(names)
        if item is None:
            return None

        claims = item.get("claims") or {}
        out: Dict[str, Any] = {"version": 1, "name": label(item)}

        year = release_year(claims)
        if year:
            out["released"] = year

        art: Dict[str, List[Dict[str, str]]] = {}
        for prop, art_type, width in PICTURES:
            filename = first_value(claims, prop)
            if isinstance(filename, str) and filename:
                art[art_type] = [{"url": picture_url(filename, width)}]

        # The maker's own logo sits on its own item, one hop away
        maker = first_value(claims, MANUFACTURER)
        maker_id = maker.get("id") if isinstance(maker, dict) else None
        if maker_id:
            company = self._entity(maker_id)
            if company:
                maker_name = label(company)
                if maker_name:
                    out["manufacturer"] = maker_name
                logo = first_value(company.get("claims") or {}, "P154")
                if isinstance(logo, str) and logo:
                    art["logo"] = [{"url": picture_url(logo, 800)}]

        if art:
            out["art"] = art
        return out if out.get("name") or art else None

    def _machine(self, names: List[str]) -> Optional[Dict[str, Any]]:
        """The first hit that reads like a machine rather than something else of the name."""
        for name in names[:3]:
            for hit in self._search(name):
                description = str(hit.get("description") or "").lower()
                if not any(word in description for word in MACHINE_WORDS):
                    continue
                entity = self._entity(str(hit.get("id") or ""))
                if entity is not None:
                    return entity
        return None

    def _search(self, name: str) -> List[Dict[str, Any]]:
        answer = self._get({"action": "wbsearchentities", "search": name, "language": "en",
                            "uselang": "en", "type": "item", "limit": 5, "format": "json"})
        hits = (answer or {}).get("search")
        return hits if isinstance(hits, list) else []

    def _entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        if not entity_id:
            return None
        answer = self._get({"action": "wbgetentities", "ids": entity_id,
                            "props": "claims|labels", "languages": "en|mul", "format": "json"})
        entity = ((answer or {}).get("entities") or {}).get(entity_id)
        return entity if isinstance(entity, dict) else None

    def _get(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = API_URL + "?" + urllib.parse.urlencode(params)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            self.log("wikidata answered HTTP {}".format(err.code), True)
        except Exception as err:
            self.log("wikidata could not be reached: {}".format(err), True)
        return None
