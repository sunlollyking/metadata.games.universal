"""REG-Vault: a hash-keyed catalogue that also holds scanned manuals.

The service answers one question, "what is this dump", and answers it well:
a title, a description, a box front, and where a manual exists, a document.
It is free, needs no key, and asks two things in return. It documents a
thousand requests a day per address, and it asks not to be scraped in bulk.
So this provider stays out of a folder scan and is used when a single game is
looked up, one request a second.

The catalogue hashes cartridge data, not the file, so a dump carrying a copier
header has to be hashed without it. Kodi already does that for the headers it
knows, and sends both hashes; the header-free one is the one to ask with.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from . import Log, Provider, Request

BASE_URL = "https://api.regvault.org/api/v1"

#: Pictures are served off the host root rather than under the API
ASSET_BASE_URL = "https://api.regvault.org"

USER_AGENT = "kodi-metadata.games.universal/1.0 (+https://kodi.tv)"

#: The service documents a hundred requests a minute; one a second stays well
#: under it and does not look like a scrape
MIN_SECONDS_BETWEEN_REQUESTS = 1.0

TIMEOUT = 30

#: A merged entry takes its year from whichever source shouted loudest, and is
#: wrong about a third of the time, always too late. A year outside the
#: machine's commercial life is dropped rather than shown.
SYSTEM_YEARS = {
    "atari2600": (1977, 1992), "atari5200": (1982, 1986), "atari7800": (1986, 1992),
    "nes": (1983, 1995), "famicomdisk": (1986, 1992), "snes": (1990, 2000),
    "n64": (1996, 2003), "gamecube": (2001, 2008), "wii": (2006, 2013),
    "gb": (1989, 2001), "gbc": (1998, 2003), "gba": (2001, 2008), "nds": (2004, 2014),
    "mastersystem": (1985, 1996), "megadrive": (1988, 1998), "segacd": (1991, 1996),
    "sega32x": (1994, 1996), "saturn": (1994, 2000), "dreamcast": (1998, 2002),
    "gamegear": (1990, 1997), "sg1000": (1983, 1987),
    "psx": (1994, 2005), "ps2": (2000, 2013), "psp": (2004, 2014),
    "pcengine": (1987, 1994), "pcenginecd": (1988, 1995), "neogeo": (1990, 2004),
    "lynx": (1989, 1995), "jaguar": (1993, 1996), "3do": (1993, 1996),
    "wonderswan": (1999, 2003), "wonderswancolor": (2000, 2004),
    "virtualboy": (1995, 1996), "intellivision": (1979, 1990), "colecovision": (1982, 1985),
    "vectrex": (1982, 1984), "c64": (1982, 1994), "msx": (1983, 1990), "msx2": (1985, 1993),
    "zxspectrum": (1982, 1992), "amiga": (1985, 1996),
}

#: A year a machine could plausibly have carried, allowing a year either side
YEAR_GRACE = 1


def plausible_year(system: str, year: Any) -> Optional[int]:
    if not isinstance(year, int) or year < 1970 or year > 2100:
        return None
    span = SYSTEM_YEARS.get(system)
    if span is None:
        return year
    return year if span[0] - YEAR_GRACE <= year <= span[1] + YEAR_GRACE else None


def genres(entry: Dict[str, Any]) -> List[str]:
    """The catalogue answers with a list for some games and a string for others."""
    value = entry.get("genre") or []
    if isinstance(value, str):
        value = value.split(",")
    return [part.strip() for part in value if isinstance(part, str) and part.strip()]


class RegVaultProvider(Provider):
    """Free, keyless, and deliberately not used to scan a collection."""

    name = "regvault"
    bulk_safe = False

    def __init__(self, log: Log):
        super().__init__(log)
        self._last_request = 0.0

    def available(self, settings: Dict[str, Any]) -> bool:
        return True

    def find(self, request: Request) -> List[dict]:
        system = request.platform_id(self.name)
        if not system:
            return []

        for key in ("md5", "sha1", "crc32"):
            digest = request.get(key).strip().lower()
            if key != "md5" or not digest:
                continue
            entry = self._lookup(system, digest)
            if entry is None:
                continue
            title = entry.get("title_en") or request.title()
            candidate = {"id": "{}/{}".format(system, digest), "title": title,
                         "score": 1.0, "matchedby": "hash"}
            year = plausible_year(system, entry.get("year"))
            if year:
                candidate["year"] = year
            return [candidate]

        return []

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        system, _, digest = candidate_id.partition("/")
        if not system or not digest:
            return None

        entry = self._lookup(system, digest)
        if entry is None:
            return None

        # A merged entry often points at a cleaner one built from a single
        # source, and that is the entry worth describing
        described = entry
        sibling = entry.get("manual_rom_hash")
        if isinstance(sibling, str) and sibling and sibling != digest:
            other = self._lookup(system, sibling)
            if other:
                described = other

        out: Dict[str, Any] = {"version": 1,
                               "title": described.get("title_en") or entry.get("title_en") or ""}
        if not out["title"]:
            return None

        overview = described.get("description_en") or entry.get("description_en")
        if overview:
            out["overview"] = overview

        year = plausible_year(system, described.get("year"))
        if year:
            out["year"] = year

        for key, field in (("developer", "developers"), ("publisher", "publishers")):
            value = described.get(key) or entry.get(key)
            if value:
                out[field] = [value]

        genre_list = genres(described) or genres(entry)
        if genre_list:
            out["genres"] = genre_list

        assets = dict(entry.get("assets") or {})
        assets.update({k: v for k, v in (described.get("assets") or {}).items() if v})
        art: Dict[str, List[Dict[str, str]]] = {}
        if assets.get("box_front"):
            art["boxfront"] = [{"url": ASSET_BASE_URL + assets["box_front"]}]
        if assets.get("fanart"):
            art["fanart"] = [{"url": ASSET_BASE_URL + assets["fanart"]}]
        if art:
            out["art"] = art

        # The manual is the reason this catalogue exists; the library holds a
        # link to it rather than the document
        if described.get("has_manual") or entry.get("has_manual"):
            out["manual"] = "{}/game/{}/{}/manual".format(BASE_URL, system, digest)

        out["uniqueids"] = {"regvault": digest}
        return out

    def _lookup(self, system: str, digest: str) -> Optional[Dict[str, Any]]:
        url = "{}/game/{}/{}".format(BASE_URL, urllib.parse.quote(system),
                                     urllib.parse.quote(digest))
        self._wait_turn()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            if err.code == 429:
                # Being asked to stop is not something to retry around
                self.log("regvault is rate limiting this address; stopping", True)
                return None
            self.log("regvault answered HTTP {}".format(err.code), True)
        except Exception as err:
            self.log("regvault could not be reached: {}".format(err), True)
        return None

    def _wait_turn(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
        self._last_request = time.time()
