"""TheGamesDB provider: hash lookups and exact-name search on one platform, within a monthly allowance.

API v1, base https://api.thegamesdb.net/. Every call carries
``apikey=<public API key>`` (setting tgdb_api_key) and answers with
``remaining_monthly_allowance``; when that reaches zero the provider logs
once and reports itself unavailable for the rest of the month.

* ``/v1/Games/ByGameHash?hash=<md5>&filter[type]=md5`` identifies a ROM by
  MD5; the CRC is tried next, but only on a resolved platform.
* ``/v1.1/Games/ByGameName?name=<title>&filter[platform]=<id>`` searches by
  name; only an exact match on the title or an alternate name is a candidate.
* ``/v1/Games/ByGameID`` fetches a game find has not seen; records find
  fetched are kept so details rarely needs it.
* ``/v1/Games/Images?games_id=<id>`` lists art; URLs are ``base_url.original``
  joined with each ``filename``. Boxart carries a ``side`` of front or back.
* ``/v1/Platforms``, ``/v1/Genres``, ``/v1/Developers`` and ``/v1/Publishers``
  are fetched once and cached: platformids carry no TheGamesDB id, so the
  platform is resolved by matching its names against the list's ``name`` and
  ``alias``, and games name their genres and companies by id.

Candidate ids are TheGamesDB game ids.
"""
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from .. import namer
from .. import net
from . import OnlineProvider, Request, platform_key, platform_keys, platform_names

BASE_URL = "https://api.thegamesdb.net/"
GAMES_BY_HASH = "v1/Games/ByGameHash"
GAMES_BY_NAME = "v1.1/Games/ByGameName"
GAMES_BY_ID = "v1/Games/ByGameID"
GAME_IMAGES = "v1/Games/Images"
PLATFORMS = "v1/Platforms"
PLATFORM_IMAGES = "v1/Platforms/Images"
LOOKUPS = {"genres": "v1/Genres", "developers": "v1/Developers", "publishers": "v1/Publishers"}
FIELDS = "players,publishers,genres,overview,rating,coop,youtube,alternates"
IMAGE_TYPES = "boxart,fanart,banner,screenshot,clearlogo,titlescreen"
PLATFORM_FIELDS = "manufacturer,overview"
#: A machine's pictures: its own boxart is a photograph of the hardware
PLATFORM_ART = {"boxart": "photo", "fanart": "fanart", "banner": "banner",
                "clearlogo": "clearlogo", "icon": "icon"}
ART = {"fanart": "fanart", "banner": "banner", "screenshot": "screenshot", "clearlogo": "clearlogo",
       "titlescreen": "titlescreen"}
BOXART = {"front": "boxfront", "back": "boxback"}
TRAILER = "plugin://plugin.video.youtube/play/?video_id={}"
DATE = re.compile(r"^([1-9]\d{3})-(\d{2})-(\d{2})$")


class TheGamesDbProvider(OnlineProvider):
    name = "thegamesdb"
    #: A public key allows a thousand requests a month and one game costs two
    #: or three of them, so a scan spends a share and then leaves it alone
    bulk_safe = False
    monthly_budget = 300
    budget_setting = "tgdb_monthly_lookups"
    folder = "tgdb"
    required_settings = ("tgdb_api_key",)

    def available(self, settings: Dict[str, Any]) -> bool:
        return super().available(settings) and not self.exhausted

    def find(self, request: Request) -> List[dict]:
        platform_id = self._platform_id(request)
        hashes = request.hashes()
        for hash_type, key in (("md5", "md5"), ("crc", "crc32")):
            value = hashes.get(key)
            if not value or (hash_type == "crc" and not platform_id):
                continue
            params = {"hash": value, "filter[type]": hash_type, "fields": FIELDS, "include": "platform"}
            if platform_id:
                params["filter[platform]"] = platform_id
            games = self._games(GAMES_BY_HASH, params, request)
            if games:
                return [candidate(g, 1.0, "hash") for g in games]
        title = request.title()
        if not platform_id or not title:
            return []
        params = {"name": title, "filter[platform]": platform_id, "fields": FIELDS, "include": "platform"}
        key = namer.normalise(title)
        return [candidate(g, 0.9, "name") for g in self._games(GAMES_BY_NAME, params, request) if key in game_keys(g)]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        game = self.cache.load("game_" + candidate_id, request.cache_days())
        if game is None:
            games = self._games(GAMES_BY_ID, {"id": candidate_id, "fields": FIELDS, "include": "platform"}, request)
            game = games[0] if games else None
        if not isinstance(game, dict) or not game.get("game_title"):
            return None
        lookups = {kind: self._lookup(kind, request) for kind in LOOKUPS if game.get(kind)}
        return game_details(game, self._images(candidate_id, request), lookups)

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        platform_id = self._platform_id(request)
        for row in self._platforms(request):
            if str(row.get("id")) == platform_id and platform_id:
                out: Dict[str, Any] = {"version": 1, "name": str(row.get("name") or "")}
                manufacturer = row.get("manufacturer") or row.get("developer")
                if manufacturer:
                    out["manufacturer"] = str(manufacturer)
                if row.get("overview"):
                    out["overview"] = str(row["overview"])
                pictures = self._platform_art(platform_id, request)
                if pictures:
                    out["art"] = pictures
                return out
        return None

    def _platform_art(self, platform_id: str, request: Request) -> Dict[str, List[Dict[str, str]]]:
        """The machine's own pictures, cached for as long as its description."""
        key = "platform-images-{}".format(platform_id)
        images = self.cache.load(key, request.cache_days())
        if images is None:
            images = self._get(PLATFORM_IMAGES, {"platforms_id": platform_id}, request)
            if images is None:
                return {}
            images = images.get("data") if isinstance(images.get("data"), dict) else {}
            self.cache.save(key, images)
        return platform_art(images)

    def _platform_id(self, request: Request) -> str:
        platform_id = resolve_platform(self._platforms(request), platform_names(request))
        if not platform_id:
            self.log("no TheGamesDB platform matches {!r}".format(request.get("platform")), False)
        return platform_id

    def _platforms(self, request: Request) -> List[dict]:
        rows = self.cache.load("platforms", request.cache_days())
        if rows is None:
            answer = self._get(PLATFORMS, {"fields": PLATFORM_FIELDS}, request)
            rows = table(answer, "platforms")
            if answer is None:
                return []
            self.cache.save("platforms", rows)
        return rows

    def _games(self, endpoint: str, params: Dict[str, Any], request: Request) -> List[dict]:
        answer = self._get(endpoint, params, request)
        games = ((answer or {}).get("data") or {}).get("games")
        games = [g for g in games if isinstance(g, dict) and g.get("id") is not None] if isinstance(games, list) else []
        for game in games:
            self.cache.save("game_{}".format(game["id"]), game)
        return games

    def _images(self, game_id: str, request: Request) -> Dict[str, Any]:
        doc = self.cache.load("images_" + game_id, request.cache_days())
        if doc is None:
            answer = self._get(GAME_IMAGES, {"games_id": game_id, "filter[type]": IMAGE_TYPES}, request)
            doc = (answer or {}).get("data") if isinstance((answer or {}).get("data"), dict) else {}
            if answer is not None:
                self.cache.save("images_" + game_id, doc)
        return doc if isinstance(doc, dict) else {}

    def _lookup(self, kind: str, request: Request) -> Dict[str, str]:
        doc = self.cache.load(kind, request.cache_days())
        if doc is None:
            answer = self._get(LOOKUPS[kind], {}, request)
            doc = {str(row.get("id")): str(row.get("name")) for row in table(answer, kind) if row.get("name")}
            if answer is not None:
                self.cache.save(kind, doc)
        return doc if isinstance(doc, dict) else {}

    def _get(self, endpoint: str, params: Dict[str, Any], request: Request) -> Optional[dict]:
        if self.exhausted:
            return None
        query: Dict[str, Any] = {"apikey": request.settings.get("tgdb_api_key")}
        query.update(params)
        try:
            answer = net.get_json(BASE_URL + endpoint, query, log=self.log)
        except (net.Error, ValueError) as err:
            # Being told to stop is not a failure to retry around: every later
            # call would pay the same wait for the same answer
            if getattr(err, "status", None) == 429:
                self.stop_asking("TheGamesDB is turning requests away; not asking "
                                 "again for now")
            else:
                self.log("{} failed: {}".format(endpoint, err), True)
            return None
        if not isinstance(answer, dict):
            return None
        remaining = answer.get("remaining_monthly_allowance")
        extra = answer.get("extra_allowance") if isinstance(answer.get("extra_allowance"), int) else 0
        if isinstance(remaining, int) and remaining + extra <= 0:
            self.stop_asking("TheGamesDB monthly allowance is used up; not asking again "
                             "this month", self.ALLOWANCE_DAYS)
        return answer


def table(answer: Optional[dict], key: str) -> List[dict]:
    """Rows of a list endpoint, which keys them by id."""
    rows = ((answer or {}).get("data") or {}).get(key)
    if isinstance(rows, dict):
        rows = list(rows.values())
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def resolve_platform(rows: Sequence[dict], names: Sequence[str]) -> str:
    keyed = []
    for row in rows:
        keys: Set[str] = set()
        for value in (row.get("name"), row.get("alias")):
            if isinstance(value, str):
                keys.update(platform_keys(value))
        keyed.append((keys, str(row.get("id"))))
    for name in names:
        key = platform_key(name)
        for keys, platform_id in keyed:
            if key in keys:
                return platform_id
    return ""


def game_keys(game: dict) -> Set[str]:
    titles = [game.get("game_title")] + list(game.get("alternates") or [])
    return {namer.normalise(str(t)) for t in titles if isinstance(t, str) and t}


def candidate(game: dict, score: float, matchedby: str) -> dict:
    out = {"id": str(game.get("id")), "title": str(game.get("game_title") or ""), "score": score, "matchedby": matchedby}
    m = DATE.match(str(game.get("release_date") or ""))
    if m:
        out["year"] = int(m.group(1))
    return out


def resolved(game: dict, kind: str, lookups: Dict[str, Dict[str, str]]) -> List[str]:
    ids = game.get(kind) if isinstance(game.get(kind), list) else []
    names = [lookups.get(kind, {}).get(str(i)) for i in ids]
    return [n for n in names if n]


def art(images: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    base = ((images.get("base_url") or {}).get("original") or "") if isinstance(images.get("base_url"), dict) else ""
    out: Dict[str, List[Dict[str, str]]] = {}
    entries = images.get("images") or {}
    for items in entries.values() if isinstance(entries, dict) else []:
        for image in items if isinstance(items, list) else []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            kind = image.get("type")
            art_type = BOXART.get(str(image.get("side") or "")) if kind == "boxart" else ART.get(str(kind))
            if art_type:
                out.setdefault(art_type, []).append({"url": base + str(image["filename"])})
    return out


def platform_art(images: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """Pictures of a machine, keyed the way the library names them."""
    base = ((images.get("base_url") or {}).get("original") or "") if isinstance(images.get("base_url"), dict) else ""
    out: Dict[str, List[Dict[str, str]]] = {}
    entries = images.get("images") or {}
    for items in entries.values() if isinstance(entries, dict) else []:
        for image in items if isinstance(items, list) else []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            art_type = PLATFORM_ART.get(str(image.get("type") or ""))
            if art_type:
                out.setdefault(art_type, []).append({"url": base + str(image["filename"])})
    return out


def game_details(game: dict, images: Dict[str, Any], lookups: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "version": 1,
        "title": str(game.get("game_title") or ""),
        "overview": str(game.get("overview") or "").strip(),
        "developers": resolved(game, "developers", lookups),
        "publishers": resolved(game, "publishers", lookups),
        "genres": resolved(game, "genres", lookups),
        "uniqueids": {"thegamesdb": str(game.get("id"))},
        "art": art(images),
    }
    m = DATE.match(str(game.get("release_date") or ""))
    if m:
        out["releasedate"] = m.group(0)
        out["year"] = int(m.group(1))
    players = game.get("players")
    if isinstance(players, int) and players > 0:
        out["players"] = {"min": 1, "max": players}
    coop = str(game.get("coop") or "").strip().lower()
    if coop in ("yes", "no"):
        out["coop"] = coop == "yes"
    rating = str(game.get("rating") or "").strip()
    if rating and not rating.lower().startswith("not rated"):
        out["ageratings"] = [{"board": "ESRB", "value": rating.split(" - ")[0].strip(), "descriptors": ""}]
    if game.get("youtube"):
        out["trailer"] = TRAILER.format(game["youtube"])
    return out
