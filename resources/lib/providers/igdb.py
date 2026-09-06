"""IGDB provider: exact-name lookups on one platform, with the platform itself resolved by name.

API v4, base https://api.igdb.com/v4/. Access needs a Twitch application:
the client id and secret (settings igdb_client_id, igdb_client_secret) are
exchanged for an app access token at ``POST https://id.twitch.tv/oauth2/token``
and every IGDB call sends ``Client-ID`` and ``Authorization: Bearer``. The
token is cached with its expiry; a 401 discards it and the call is made once
more with a fresh one. Calls are paced to four per second.

Queries are Apicalypse bodies posted to an endpoint:

* ``games`` with ``search "<title>"; where platforms = (<id>);`` finds games
  by name on one platform; ``where id = <id>;`` fetches one with companies,
  genres, images, ratings and release dates expanded.
* ``platforms`` is listed once (cached) so the Kodi platform can be resolved:
  platformids carry no IGDB id, so the platform's names (LaunchBox, HyperSpin,
  libretro, slugs) are matched against IGDB's name, alternative names,
  abbreviation and slug.

IGDB has no hash lookup: candidates are exact name matches among main games,
never IGDB's own ranking. The field lists of the current schema are tried
first and those of the older one on a 400. Image URLs are
https://images.igdb.com/igdb/image/upload/t_<size>/<image_id>.jpg.
"""
import time
from typing import Any, Dict, List, Optional, Sequence

from .. import namer
from .. import net
from . import OnlineProvider, Request, platform_key, platform_keys, platform_names

BASE_URL = "https://api.igdb.com/v4/"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload/t_{}/{}.jpg"
#: A logo is cut out on a transparent background, which only the PNG keeps
LOGO_URL = "https://images.igdb.com/igdb/image/upload/t_{}/{}.png"
MIN_INTERVAL = 0.25
#: How many titles one prefetch query asks about
PREFETCH_CHUNK = 60
TOKEN_MARGIN = 60
SEARCH_FIELDS = ("id,name,first_release_date,platforms,game_type,category",
                 "id,name,first_release_date,platforms")
DETAIL_COMMON = ("name,summary,storyline,first_release_date,total_rating,total_rating_count,"
                 "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
                 "genres.name,themes.name,franchises.name,game_modes.name,"
                 "multiplayer_modes.offlinemax,multiplayer_modes.offlinecoop,multiplayer_modes.platform,"
                 "cover.image_id,screenshots.image_id,artworks.image_id,"
                 "release_dates.date,release_dates.platform,release_dates.region")
DETAIL_FIELDS = (
    DETAIL_COMMON + ",collections.name,age_ratings.rating_category,age_ratings.organization,release_dates.date_format",
    DETAIL_COMMON + ",collection.name,age_ratings.rating,age_ratings.category,release_dates.category",
)
PLATFORM_LIST_FIELDS = "name,alternative_name,abbreviation,slug"
PLATFORM_FIELDS = "name,alternative_name,abbreviation,summary,platform_logo.image_id,generation,versions.companies.company.name"
MAIN_GAME = 0
BOARDS = {1: "ESRB", 2: "PEGI", 3: "CERO", 4: "USK", 5: "GRAC", 6: "CLASS_IND", 7: "ACB"}
RATINGS = {
    1: "3", 2: "7", 3: "12", 4: "16", 5: "18", 6: "RP", 7: "EC", 8: "E", 9: "E10+", 10: "T", 11: "M", 12: "AO",
    13: "A", 14: "B", 15: "C", 16: "D", 17: "Z", 18: "0", 19: "6", 20: "12", 21: "16", 22: "18",
    23: "All", 24: "12", 25: "15", 26: "18", 27: "Testing", 28: "L", 29: "10", 30: "12", 31: "14", 32: "16",
    33: "18", 34: "G", 35: "PG", 36: "M", 37: "MA15+", 38: "R18+", 39: "RC",
}


class IgdbProvider(OnlineProvider):
    name = "igdb"
    folder = "igdb"
    required_settings = ("igdb_client_id", "igdb_client_secret")

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        #: What a batch asked about, by platform and normalised name, and by id
        self._known: Dict[tuple, dict] = {}
        self._by_id: Dict[str, dict] = {}

    def prefetch(self, requests: Sequence[Request]) -> None:
        """Ask about a whole folder's titles at once.

        A scan of a full set is otherwise two requests a game against an API
        paced to four a second, which is hours for a large collection. IGDB
        will return up to five hundred games for one query, so the titles are
        asked for in chunks and what comes back answers both find and details
        without going out again.
        """
        if not requests:
            return

        wanted: Dict[str, Dict[str, Request]] = {}
        for request in requests:
            platform_id = self._platform_id(request)
            title = request.title()
            if not platform_id or not title:
                continue
            wanted.setdefault(platform_id, {}).setdefault(title, request)

        for platform_id, titles in wanted.items():
            names = list(titles)
            for start in range(0, len(names), PREFETCH_CHUNK):
                chunk = names[start:start + PREFETCH_CHUNK]
                quoted = ",".join('"{}"'.format(apicalypse(name)) for name in chunk)
                # An exact list; IGDB's case-insensitive operator does not take one
                body = "where platforms = ({}) & name = ({}); limit 500;".format(platform_id, quoted)
                rows = self._query("games", DETAIL_FIELDS, body, titles[chunk[0]])
                for row in rows or []:
                    if not main_game(row):
                        continue
                    key = namer.normalise(str(row.get("name") or ""))
                    if not key:
                        continue
                    self._known.setdefault((platform_id, key), row)
                    self._by_id[str(row.get("id"))] = row

    def find(self, request: Request) -> List[dict]:
        platform_id = self._platform_id(request)
        title = request.title()
        if not platform_id or not title:
            return []

        key = namer.normalise(title)
        known = self._known.get((platform_id, key))
        if known is not None:
            return [candidate(known)]

        body = 'search "{}"; where platforms = ({}); limit 50;'.format(apicalypse(title), platform_id)
        games = self._query("games", SEARCH_FIELDS, body, request)
        return [candidate(g) for g in games or []
                if main_game(g) and namer.normalise(str(g.get("name") or "")) == key]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        if not candidate_id.isdigit():
            return None
        known = self._by_id.get(candidate_id)
        if known is not None:
            return game_details(known, self._platform_id(request))
        games = self._query("games", DETAIL_FIELDS, "where id = {}; limit 1;".format(candidate_id), request)
        return game_details(games[0], self._platform_id(request)) if games else None

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        platform_id = self._platform_id(request)
        if not platform_id:
            return None
        rows = self._query("platforms", (PLATFORM_FIELDS,), "where id = {}; limit 1;".format(platform_id), request)
        return platform_info(rows[0]) if rows else None

    def _platform_id(self, request: Request) -> str:
        rows = self.cache.load("platforms", request.cache_days())
        if rows is None:
            rows = self._query("platforms", (PLATFORM_LIST_FIELDS,), "limit 500;", request)
            if rows is None:
                return ""
            self.cache.save("platforms", rows)
        platform_id = resolve_platform(rows, platform_names(request))
        if not platform_id:
            self.log("no IGDB platform matches {!r}".format(request.get("platform")), False)
        return platform_id

    def _query(self, endpoint: str, field_variants: Sequence[str], body: str,
               request: Request) -> Optional[List[dict]]:
        """Rows for an Apicalypse body, tried with each field list in turn; None when nothing usable came back."""
        for index, fields in enumerate(field_variants):
            try:
                rows = self._post(endpoint, "fields {}; {}".format(fields, body), request)
            except net.Error as err:
                if getattr(err, "status", None) == 429:
                    self.stop_asking("{} is turning requests away; not asking again "
                                     "for now".format(self.name))
                if err.status == 400 and index + 1 < len(field_variants):
                    continue
                self.log("{} query failed: {}".format(endpoint, err), True)
                return None
            return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None
        return None

    def _post(self, endpoint: str, body: str, request: Request) -> Any:
        for attempt in (1, 2):
            token = self._token(request)
            if not token:
                raise net.Error(BASE_URL + endpoint, reason="no access token")
            headers = {"Client-ID": str(request.settings.get("igdb_client_id") or ""),
                       "Authorization": "Bearer " + token, "Accept": "application/json"}
            try:
                return net.post_json(BASE_URL + endpoint, body, headers=headers, log=self.log,
                                     min_interval=MIN_INTERVAL)
            except net.Error as err:
                if err.status != 401 or attempt == 2:
                    raise
                self.cache.save("token", {})

    def _token(self, request: Request) -> str:
        client_id = str(request.settings.get("igdb_client_id") or "")
        doc = self.cache.load("token", 3650)
        if isinstance(doc, dict) and doc.get("client_id") == client_id and doc.get("access_token") \
                and float(doc.get("expires") or 0) - TOKEN_MARGIN > time.time():
            return str(doc["access_token"])
        params = {"client_id": client_id, "client_secret": str(request.settings.get("igdb_client_secret") or ""),
                  "grant_type": "client_credentials"}
        try:
            answer = net.post_json(TOKEN_URL, b"", params=params, log=self.log)
        except (net.Error, ValueError) as err:
            self.log("Twitch token request failed: {}".format(err), True)
            return ""
        token = answer.get("access_token") if isinstance(answer, dict) else None
        if not token:
            self.log("Twitch token answer carries no access_token", True)
            return ""
        try:
            expires_in = int(answer.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        self.cache.save("token", {"client_id": client_id, "access_token": token, "expires": time.time() + expires_in})
        return str(token)


def apicalypse(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def resolve_platform(rows: Sequence[dict], names: Sequence[str]) -> str:
    keyed = []
    for row in rows:
        keys = set()
        for value in (row.get("name"), row.get("alternative_name"), row.get("abbreviation"), row.get("slug")):
            if isinstance(value, str):
                for piece in value.split(","):
                    keys.update(platform_keys(piece.strip()))
        keyed.append((keys, str(row.get("id"))))
    for name in names:
        key = platform_key(name)
        for keys, platform_id in keyed:
            if key in keys:
                return platform_id
    return ""


def main_game(game: dict) -> bool:
    kind = game.get("game_type", game.get("category"))
    return kind is None or kind == MAIN_GAME


def candidate(game: dict) -> dict:
    out = {"id": str(game.get("id")), "title": str(game.get("name") or ""), "score": 0.9, "matchedby": "name"}
    date = format_date(game.get("first_release_date"), 2)
    if date:
        out["year"] = int(date[:4])
    return out


def format_date(stamp: Any, date_format: Any) -> str:
    try:
        t = time.gmtime(int(stamp))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    fmt = date_format if isinstance(date_format, int) else 0
    if fmt == 0:
        return time.strftime("%Y-%m-%d", t)
    if fmt == 1:
        return time.strftime("%Y-%m", t)
    if 2 <= fmt <= 6:
        return time.strftime("%Y", t)
    return ""


def release_date(game: dict, platform_id: str) -> str:
    dates = [rd for rd in game.get("release_dates") or [] if isinstance(rd, dict) and rd.get("date")]
    mine = [rd for rd in dates if str(rd.get("platform")) == platform_id] or dates
    if mine:
        rd = min(mine, key=lambda x: x["date"])
        return format_date(rd["date"], rd.get("date_format", rd.get("category")))
    return format_date(game.get("first_release_date"), 0) if game.get("first_release_date") else ""


def names(game: dict, key: str) -> List[str]:
    value = game.get(key)
    items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    return [str(i["name"]) for i in items if isinstance(i, dict) and i.get("name")]


def companies(game: dict, role: str) -> List[str]:
    out = []
    for item in game.get("involved_companies") or []:
        company = item.get("company") if isinstance(item, dict) else None
        if item.get(role) and isinstance(company, dict) and company.get("name"):
            out.append(str(company["name"]))
    return list(dict.fromkeys(out))


def age_ratings(game: dict) -> List[dict]:
    out = []
    for item in game.get("age_ratings") or []:
        if not isinstance(item, dict):
            continue
        board = BOARDS.get(item.get("organization", item.get("category")))
        category = item.get("rating_category", item.get("rating"))
        if board and category is not None:
            out.append({"board": board, "value": RATINGS.get(category, str(category)), "descriptors": ""})
    return out


def multiplayer(game: dict, platform_id: str) -> Optional[dict]:
    modes = [m for m in game.get("multiplayer_modes") or [] if isinstance(m, dict)]
    mine = [m for m in modes if str(m.get("platform")) == platform_id] or modes
    return mine[0] if mine else None


def art(game: dict) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    cover = game.get("cover")
    if isinstance(cover, dict) and cover.get("image_id"):
        out["boxfront"] = [{"url": IMAGE_URL.format("cover_big", cover["image_id"])}]
    for key, art_type, size in (("screenshots", "screenshot", "screenshot_big"), ("artworks", "fanart", "1080p")):
        urls = [IMAGE_URL.format(size, i["image_id"]) for i in game.get(key) or []
                if isinstance(i, dict) and i.get("image_id")]
        if urls:
            out[art_type] = [{"url": u} for u in urls]
    return out


def game_details(game: dict, platform_id: str) -> Dict[str, Any]:
    overview = str(game.get("summary") or "").strip()
    storyline = str(game.get("storyline") or "").strip()
    if storyline:
        overview = "{}\n\n{}".format(overview, storyline) if overview else storyline
    out: Dict[str, Any] = {
        "version": 1,
        "title": str(game.get("name") or ""),
        "overview": overview,
        "developers": companies(game, "developer"),
        "publishers": companies(game, "publisher"),
        "genres": names(game, "genres") + names(game, "themes"),
        "collections": list(dict.fromkeys(names(game, "franchises") + names(game, "collections") + names(game, "collection"))),
        "ageratings": age_ratings(game),
        "uniqueids": {"igdb": str(game.get("id"))},
        "art": art(game),
    }
    date = release_date(game, platform_id)
    if date:
        out["releasedate"] = date
        out["year"] = int(date[:4])
    mode = multiplayer(game, platform_id)
    if mode:
        if isinstance(mode.get("offlinemax"), int) and mode["offlinemax"] > 0:
            out["players"] = {"min": 1, "max": mode["offlinemax"]}
        if "offlinecoop" in mode:
            out["coop"] = bool(mode["offlinecoop"])
    rating = game.get("total_rating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        out["ratings"] = {"igdb": {"rating": round(float(rating), 1), "max": 100,
                                   "votes": int(game.get("total_rating_count") or 0)}}
    return out


def platform_info(row: dict) -> Dict[str, Any]:
    out: Dict[str, Any] = {"version": 1, "name": str(row.get("name") or "")}
    if row.get("summary"):
        out["overview"] = str(row["summary"])
    for version in row.get("versions") or []:
        for item in (version.get("companies") or []) if isinstance(version, dict) else []:
            company = item.get("company") if isinstance(item, dict) else None
            if isinstance(company, dict) and company.get("name"):
                out["manufacturer"] = str(company["name"])
                break
        if "manufacturer" in out:
            break
    logo = row.get("platform_logo")
    if isinstance(logo, dict) and logo.get("image_id"):
        out["art"] = {"clearlogo": [{"url": LOGO_URL.format("logo_med", logo["image_id"])}]}
    return out
