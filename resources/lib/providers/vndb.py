"""VNDB: the visual novel database, for the adventure games Japanese computers were full of.

Most of the PC-98, PC-88 and X68000 games no game catalogue describes are
visual novels and text adventures, and VNDB lists them under their Japanese
titles as well as their romanised ones. The API is free, needs no key and
allows 200 requests in five minutes, so the whole list for a machine is read
once (a dozen requests for the PC-98) and kept, and games are matched against
it without asking again.

A match is by name only, so it is only made against the machine's own list:
VNDB knows what was released on the PC-98, and a name that matches there is
very likely the game. A near match must agree on every number in the name,
because "Dragon Knight 3" and "Dragon Knight" are close and different games.
"""
import difflib
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional

from .. import namer, net
from . import OnlineProvider, Request

API_URL = "https://api.vndb.org/kana/vn"

#: VNDB's code for each of Kodi's platforms where visual novels were released
PLATFORMS = {
    "pc98": "p98", "pc88": "p88", "x68000": "x68", "fmtowns": "fmt", "fm7": "fm7",
    "msx": "msx", "msx2": "msx", "x1": "x1s", "pcengine": "pce", "pcenginecd": "pce",
    "pcfx": "pcf", "saturn": "sat", "segacd": "scd", "psx": "ps1", "ps2": "ps2",
    "dreamcast": "drc", "3do": "tdo", "nds": "nds", "psp": "psp", "dos": "dos",
    "windows": "win",
}

FIELDS = ("id,title,alttitle,titles.title,titles.latin,released,developers.name,"
          "image.url,image.sexual,image.violence,description")

PAGE_SIZE = 100

#: 200 requests in five minutes is one every 1.5 seconds
MIN_INTERVAL = 1.6

#: Covers VNDB's voters rate this sexual or violent, on a scale of 0 to 2, are
#: only used when the setting allows them
ADULT_COVERS = "vndb_adult_covers"
ADULT_RATING = 1.0

#: A near match has to be this close, and long enough for closeness to mean something
CLOSE_RATIO = 0.9
CLOSE_MIN_LENGTH = 5

_DIGITS = re.compile(r"\d+")
#: A sequel numbered in Roman numerals, as VNDB and Japanese collections often
#: write it: "ドラゴンナイトIII" is "ドラゴンナイト3". V and X stand alone in
#: too many names, "X68000" among them, to be read as numbers.
_ROMAN = re.compile(r"(?<![A-Za-z0-9])(VIII|VII|VI|IV|IX|III|II)(?![A-Za-z0-9])")
_ROMAN_VALUES = {"II": "2", "III": "3", "IV": "4", "VI": "6", "VII": "7", "VIII": "8", "IX": "9"}
_LINK = re.compile(r"\[url=[^\]]*\](.*?)\[/url\]", re.IGNORECASE | re.DOTALL)
_SPOILER = re.compile(r"\[spoiler\].*?\[/spoiler\]", re.IGNORECASE | re.DOTALL)
_SOURCE_NOTE = re.compile(r"\s*\[(?:from|source|translated from|edited from)\b[^\]]*\]\s*$",
                          re.IGNORECASE)
_TAG = re.compile(r"\[/?[a-z]+(?:=[^\]]*)?\]", re.IGNORECASE)


def overview(text: Any) -> str:
    """A description without VNDB's markup, its spoilers or the note naming where it came from."""
    text = _SPOILER.sub("", str(text or ""))
    text = _LINK.sub(r"\1", text)
    text = _SOURCE_NOTE.sub("", text)
    text = _TAG.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def name_key(name: str) -> str:
    """A name as compared here, with its sequel number in digits."""
    plain = unicodedata.normalize("NFKC", name)
    return namer.normalise(_ROMAN.sub(lambda m: _ROMAN_VALUES[m.group(1)], plain))


def names(vn: Dict[str, Any]) -> List[str]:
    """Every name the entry goes by, as comparison keys."""
    raw = [vn.get("title"), vn.get("alttitle")]
    for title in vn.get("titles") or []:
        raw += [title.get("title"), title.get("latin")]
    keys = [name_key(str(n)) for n in raw if n]
    return list(dict.fromkeys(k for k in keys if k))


class VndbProvider(OnlineProvider):
    """Visual novels on the machines that had them, matched by name against that machine's list."""

    name = "vndb"
    folder = "vndb"

    def available(self, settings: Dict[str, Any]) -> bool:
        return True

    def find(self, request: Request) -> List[dict]:
        code = PLATFORMS.get(request.get("platform"))
        title = name_key(request.title())
        if not code or not title:
            return []
        entries = self._list(code, request)
        exact = [vn for vn in entries if title in names(vn)]
        if exact:
            return [self._candidate(vn, 0.9) for vn in exact]
        close = []
        if len(title) >= CLOSE_MIN_LENGTH:
            numbers = _DIGITS.findall(title)
            for vn in entries:
                for key in names(vn):
                    if _DIGITS.findall(key) != numbers:
                        continue
                    ratio = difflib.SequenceMatcher(None, title, key).ratio()
                    if ratio >= CLOSE_RATIO:
                        close.append((ratio, vn))
                        break
        close.sort(key=lambda hit: -hit[0])
        return [self._candidate(vn, 0.8) for _, vn in close[:3]]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        code = PLATFORMS.get(request.get("platform"))
        vn = next((v for v in self._list(code, request) if v.get("id") == candidate_id), None) \
            if code else None
        if vn is None:
            found = self._query(["id", "=", candidate_id], 1)
            vn = found[0] if found else None
        if vn is None:
            return None

        out: Dict[str, Any] = {"version": 1, "title": str(vn.get("title") or ""),
                               "genres": ["Visual Novel"], "uniqueids": {self.name: candidate_id}}
        original = str(vn.get("alttitle") or "")
        if original and original != out["title"]:
            out["originaltitle"] = original
        text = overview(vn.get("description"))
        if text:
            out["overview"] = text
        released = str(vn.get("released") or "")
        if re.match(r"^\d{4}", released):
            out["year"] = int(released[:4])
        if re.match(r"^\d{4}-\d{2}-\d{2}$", released):
            out["releasedate"] = released
        developers = [str(d.get("name")) for d in vn.get("developers") or [] if d.get("name")]
        if developers:
            out["developers"] = developers
        image = vn.get("image") or {}
        if image.get("url") and (request.settings.get(ADULT_COVERS) or
                                 (image.get("sexual") or 0) < ADULT_RATING and
                                 (image.get("violence") or 0) < ADULT_RATING):
            out["art"] = {"boxfront": [{"url": image["url"]}]}
        return out

    def _candidate(self, vn: Dict[str, Any], score: float) -> Dict[str, Any]:
        candidate = {"id": str(vn.get("id")), "title": str(vn.get("title") or ""),
                     "score": score, "matchedby": "name"}
        released = str(vn.get("released") or "")
        if re.match(r"^\d{4}", released):
            candidate["year"] = int(released[:4])
        return candidate

    def _list(self, code: str, request: Request) -> List[Dict[str, Any]]:
        """Every visual novel VNDB lists for the machine, from the cache when it is fresh."""
        key = "platform-" + code
        cached = self.cache.load(key, request.cache_days())
        if isinstance(cached, list):
            return cached
        entries: List[Dict[str, Any]] = []
        page = 1
        while True:
            answer = self._post({"filters": ["platform", "=", code], "fields": FIELDS,
                                 "results": PAGE_SIZE, "page": page})
            if answer is None:
                # Half a list would hide the games on the pages not read
                return entries
            entries += answer.get("results") or []
            if not answer.get("more"):
                break
            page += 1
        self.cache.save(key, entries)
        return entries

    def _query(self, filters: List[Any], results: int) -> List[Dict[str, Any]]:
        answer = self._post({"filters": filters, "fields": FIELDS, "results": results})
        return (answer or {}).get("results") or []

    def _post(self, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.exhausted:
            return None
        try:
            return net.post_json(API_URL, json.dumps(body), headers={"Content-Type": "application/json"},
                                 log=self.log, min_interval=MIN_INTERVAL)
        except net.Error as err:
            if err.status == 429:
                self.stop_asking("vndb is rate limiting this address; asking again later")
            else:
                self.log("vndb could not be asked: {}".format(err), True)
        return None
