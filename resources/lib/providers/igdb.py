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
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import namer
from .. import net
from . import DATA_DIR, OnlineProvider, Request, platform_key, platform_keys, platform_names, read_aliases

BASE_URL = "https://api.igdb.com/v4/"
#: Names collections use that IGDB's search does not find, each checked by hand
ALIASES_PATH = os.path.join(DATA_DIR, "igdb_aliases.tsv")
#: How Kodi plays a YouTube video, through the YouTube add-on
TRAILER = "plugin://plugin.video.youtube/play/?video_id={}"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload/t_{}/{}.jpg"
#: A logo is cut out on a transparent background, which only the PNG keeps
LOGO_URL = "https://images.igdb.com/igdb/image/upload/t_{}/{}.png"
MIN_INTERVAL = 0.25
#: How many titles one prefetch query asks about
PREFETCH_CHUNK = 60
TOKEN_MARGIN = 60
SEARCH_FIELDS = ("id,name,alternative_names.name,first_release_date,platforms,game_type,category",
                 "id,name,alternative_names.name,first_release_date,platforms")
DETAIL_COMMON = ("name,summary,storyline,first_release_date,total_rating,total_rating_count,"
                 "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
                 "genres.name,themes.name,franchises.name,franchise.name,game_modes.name,"
                 "multiplayer_modes.offlinemax,multiplayer_modes.offlinecoop,multiplayer_modes.platform,"
                 "multiplayer_modes.onlinemax,multiplayer_modes.splitscreen,multiplayer_modes.campaigncoop,"
                 "multiplayer_modes.dropin,multiplayer_modes.offlinecoopmax,"
                 "cover.image_id,screenshots.image_id,artworks.image_id,"
                 "release_dates.date,release_dates.platform,release_dates.region,"
                 # Everything below is recorded rather than shown today, so that
                 # what to do with it stays a decision and not another scrape
                 "status,version_title,parent_game.name,player_perspectives.name,"
                 "keywords.name,game_engines.name,alternative_names.name,alternative_names.comment,"
                 "language_supports.language.name,videos.video_id,videos.name,"
                 "similar_games.name,aggregated_rating,aggregated_rating_count,"
                 "rating,rating_count,hypes,websites.url,"
                 "dlcs.name,expansions.name,remakes.name,remasters.name,ports.name,"
                 "standalone_expansions.name,game_localizations.name,game_localizations.region.name,"
                 "game_localizations.region.identifier,game_localizations.cover.image_id")
DETAIL_FIELDS = (
    DETAIL_COMMON + ",game_type,collections.name,age_ratings.rating_category,age_ratings.organization,"
                    "age_ratings.rating_content_descriptions.description,"
                    "release_dates.date_format,websites.type.type,language_supports.language_support_type.name",
    DETAIL_COMMON + ",category,collection.name,age_ratings.rating,age_ratings.category,"
                    "age_ratings.content_descriptions.description,"
                    "release_dates.category,websites.category",
)
TIME_TO_BEAT_FIELDS = "game_id,hastily,normally,completely"
POPULARITY_FIELDS = "game_id,popularity_type,value"
MEMBERSHIP_FIELDS = "game,collection.name,type.name"
#: IGDB's own measures of interest in a game, by the names Kodi is given them under
POPULARITY_NAMES = {"visits": "visits", "want to play": "wanttoplay", "playing": "playing",
                    "played": "played"}
PLATFORM_LIST_FIELDS = "name,alternative_name,abbreviation,slug"
PLATFORM_FIELDS = "name,alternative_name,abbreviation,summary,platform_logo.image_id,generation,versions.companies.company.name"
#: Kinds that are the game itself rather than something sold alongside it.
#: A console release is often filed as a port or a remake -- IGDB has the NES
#: Castlequest as a port of the MSX original -- so taking only the main game
#: throws away the very version a ROM is.
GAME_ITSELF = frozenset({
    0,   # main game
    4,   # standalone expansion
    8,   # remake
    9,   # remaster
    5,   # mod -- a ROM hack or fan translation is a dump in its own right
    3,   # bundle -- a compilation is one file in the library, so it is a game
    13,  # pack -- as above
    10,  # expanded game
    11,  # port
    12,  # fork
})

#: What to call a kind that is worth telling someone about. The main game is
#: left unnamed: every library is mostly main games, so saying so says nothing.
EDITION_NAMES = {
    3: "Compilation",
    13: "Compilation",
    4: "Standalone Expansion",
    5: "Mod",
    8: "Remake",
    9: "Remaster",
    10: "Expanded Game",
    11: "Port",
    12: "Fork",
}
BOARDS = {1: "ESRB", 2: "PEGI", 3: "CERO", 4: "USK", 5: "GRAC", 6: "CLASS_IND", 7: "ACB"}
#: The current API's rating_category ids, from its age_rating_categories endpoint
RATING_CATEGORIES = {
    1: "RP", 2: "EC", 3: "E", 4: "E10+", 5: "T", 6: "M", 7: "AO",
    8: "3", 9: "7", 10: "12", 11: "16", 12: "18",
    13: "A", 14: "B", 15: "C", 16: "D", 17: "Z", 18: "0", 19: "6", 20: "12", 21: "16", 22: "18",
    23: "All", 24: "12", 25: "15", 26: "19", 27: "Testing", 28: "L", 29: "10", 30: "12", 31: "14",
    32: "16", 33: "18", 34: "G", 35: "PG", 36: "M", 37: "MA15+", 38: "R18+", 39: "RC", 40: "18",
}
#: The deprecated rating enum, which numbers PEGI before ESRB
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
        #: How long players took to beat each game asked about, by id; empty
        #: where IGDB has no times for it
        self._times: Dict[str, dict] = {}
        #: The same for popularity, by id and then by Kodi's name for the measure
        self._popularity: Dict[str, Dict[str, float]] = {}
        #: IGDB's popularity types, by id, once asked
        self._popularity_types: Optional[Dict[int, str]] = None
        #: What each game asked about is to each series it is in, by id and series name
        self._memberships: Dict[str, Dict[str, str]] = {}
        self.aliases = read_aliases(ALIASES_PATH)

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
                found = []
                for row in rows or []:
                    if not is_the_game(row):
                        continue
                    for key in title_keys(row):
                        self._known.setdefault((platform_id, key), row)
                    self._by_id[str(row.get("id"))] = row
                    found.append(str(row.get("id")))
                self._prefetch_times(found, titles[chunk[0]])
                self._prefetch_popularity(found, titles[chunk[0]])
                self._prefetch_memberships(found, titles[chunk[0]])

    def _prefetch_times(self, ids: List[str], request: Request) -> None:
        ids = [i for i in ids if i.isdigit()]
        if not ids:
            return
        body = "where game_id = ({}); limit 500;".format(",".join(ids))
        rows = self._query("game_time_to_beats", (TIME_TO_BEAT_FIELDS,), body, request)
        if rows is None:
            return  # asked again game by game
        for game_id in ids:
            self._times.setdefault(game_id, {})
        for row in rows:
            self._times[str(row.get("game_id"))] = row

    def find_alias(self, request: Request) -> List[dict]:
        platform_id = self._platform_id(request)
        title = request.title()
        key = namer.normalise(title)
        return [{"id": game_id, "title": title, "score": 0.9, "matchedby": "alias"}
                for game_id in self.aliases.get((platform_id, key), [])]

    def find(self, request: Request) -> List[dict]:
        platform_id = self._platform_id(request)
        title = request.title()
        if not platform_id or not title:
            return []

        key = namer.normalise(title)
        known = self._known.get((platform_id, key))
        if known is not None:
            return [candidate(known)]

        aliased = self.find_alias(request)
        if aliased:
            return aliased

        body = 'search "{}"; where platforms = ({}); limit 50;'.format(apicalypse(title), platform_id)
        games = self._query("games", SEARCH_FIELDS, body, request)
        matches = self._same_game(games, key)
        if matches:
            return matches

        # The search does not find "Castlequest" when asked about "Castle
        # Quest", so a name the catalogues space differently is asked for
        # directly. The operator has to be the case-insensitive one; plain
        # equality here is case-sensitive.
        for variant in namer.spacing_variants(title):
            rows = self._query("games", SEARCH_FIELDS,
                               'where platforms = ({}) & name ~ "{}"; limit 5;'.format(
                                   platform_id, apicalypse(variant)), request)
            matches = self._same_game(rows, key)
            if matches:
                return matches
        return []

    @staticmethod
    def _same_game(rows: Optional[List[dict]], key: str) -> List[dict]:
        return [candidate(g) for g in rows or [] if is_the_game(g) and key in title_keys(g)]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        if not candidate_id.isdigit():
            return None
        known = self._by_id.get(candidate_id)
        if known is not None:
            return self._detailed(known, request)
        games = self._query("games", DETAIL_FIELDS, "where id = {}; limit 1;".format(candidate_id), request)
        return self._detailed(games[0], request) if games else None

    def _popularity_type_names(self, request: Request) -> Dict[int, str]:
        if self._popularity_types is None:
            rows = self._query("popularity_types", ("name",), "limit 100;", request)
            if rows is None:
                return {}
            self._popularity_types = {
                int(r["id"]): POPULARITY_NAMES[str(r.get("name") or "").strip().lower()]
                for r in rows if isinstance(r.get("id"), int)
                and str(r.get("name") or "").strip().lower() in POPULARITY_NAMES}
        return self._popularity_types

    def _prefetch_popularity(self, ids: List[str], request: Request) -> None:
        ids = [i for i in ids if i.isdigit()]
        types = self._popularity_type_names(request)
        if not ids or not types:
            return
        body = "where game_id = ({}) & popularity_type = ({}); limit 500;".format(
            ",".join(ids), ",".join(str(t) for t in types))
        rows = self._query("popularity_primitives", (POPULARITY_FIELDS,), body, request)
        if rows is None:
            return
        for game_id in ids:
            self._popularity.setdefault(game_id, {})
        for row in rows:
            self._take_popularity(row, types)

    def _take_popularity(self, row: dict, types: Dict[int, str]) -> None:
        name = types.get(row.get("popularity_type"))
        value = row.get("value")
        if name and isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            self._popularity.setdefault(str(row.get("game_id")), {})[name] = float(value)

    def _game_popularity(self, game_id: str, request: Request) -> Dict[str, float]:
        if game_id not in self._popularity:
            types = self._popularity_type_names(request)
            if not game_id.isdigit() or not types:
                return {}
            body = "where game_id = {} & popularity_type = ({}); limit 20;".format(
                game_id, ",".join(str(t) for t in types))
            rows = self._query("popularity_primitives", (POPULARITY_FIELDS,), body, request)
            if rows is None:
                return {}
            self._popularity[game_id] = {}
            for row in rows:
                self._take_popularity(row, types)
        return self._popularity[game_id]

    def _take_membership(self, row: dict) -> None:
        collection = row.get("collection") if isinstance(row.get("collection"), dict) else {}
        kind = row.get("type") if isinstance(row.get("type"), dict) else {}
        if collection.get("name") and kind.get("name"):
            self._memberships.setdefault(str(row.get("game")), {})[str(collection["name"])] = str(kind["name"])

    def _prefetch_memberships(self, ids: List[str], request: Request) -> None:
        ids = [i for i in ids if i.isdigit()]
        if not ids:
            return
        rows = self._query("collection_memberships", (MEMBERSHIP_FIELDS,),
                           "where game = ({}); limit 500;".format(",".join(ids)), request)
        if rows is None:
            return
        for game_id in ids:
            self._memberships.setdefault(game_id, {})
        for row in rows:
            self._take_membership(row)

    def _game_memberships(self, game_id: str, request: Request) -> Dict[str, str]:
        if game_id not in self._memberships:
            if not game_id.isdigit():
                return {}
            rows = self._query("collection_memberships", (MEMBERSHIP_FIELDS,),
                               "where game = {}; limit 50;".format(game_id), request)
            if rows is None:
                return {}
            self._memberships[game_id] = {}
            for row in rows:
                self._take_membership(row)
        return self._memberships[game_id]

    def _detailed(self, row: dict, request: Request) -> Dict[str, Any]:
        out = game_details(row, self._platform_id(request))
        # What the cabinet is says more than that the game is a port of itself
        if is_vs_system(request):
            out["edition"] = "Arcade"
        times = self._time_to_beat(str(row.get("id")), request)
        if times:
            out["timetobeat"] = times
        regional = regional_localization(row, request.preferred_regions())
        if regional:
            region, title, cover = regional
            if title:
                out["regionaltitle"] = title
            if cover:
                out.setdefault("art", {}).setdefault("boxfront", []).append({"url": cover, "region": region})
        if out.get("series"):
            spinoff = is_spinoff(self._game_memberships(str(row.get("id")), request).get(out["series"]))
            if spinoff is not None:
                out["spinoff"] = spinoff
        popularity = self._game_popularity(str(row.get("id")), request)
        if popularity:
            out["popularity"] = dict(popularity)
        return out

    def _time_to_beat(self, game_id: str, request: Request) -> Dict[str, int]:
        if game_id not in self._times:
            if not game_id.isdigit():
                return {}
            rows = self._query("game_time_to_beats", (TIME_TO_BEAT_FIELDS,),
                               "where game_id = {}; limit 1;".format(game_id), request)
            if rows is None:
                return {}
            self._times[game_id] = rows[0] if rows else {}
        return time_to_beat(self._times[game_id])

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
        # Asked narrowly: a blanket fall back to Arcade would match an ordinary
        # console game to the arcade game it shares a name with, and hand it the
        # wrong description and pictures
        names = ["Arcade"] if is_vs_system(request) else platform_names(request)
        platform_id = resolve_platform(rows, names)
        if not platform_id:
            self.log("no IGDB platform matches {!r}".format(request.get("platform")), False)
        return platform_id

    def _query(self, endpoint: str, field_variants: Sequence[str], body: str,
               request: Request) -> Optional[List[dict]]:
        """Rows for an Apicalypse body, tried with each field list in turn; None when nothing usable came back."""
        for index, fields in enumerate(field_variants):
            for attempt in (1, 2, 3):
                try:
                    rows = self._post(endpoint, "fields {}; {}".format(fields, body), request)
                except net.Error as err:
                    if getattr(err, "status", None) == 429:
                        # IGDB allows about four requests a second, which a bulk
                        # scan trips constantly. Wait and ask again: giving up on
                        # the first refusal switched the source off for the rest
                        # of the run, so a platform got one short burst of
                        # answers and nothing afterwards.
                        if attempt < 3:
                            time.sleep(attempt)
                            continue
                        self.stop_asking("{} is turning requests away even after "
                                         "backing off; not asking again for now".format(self.name))
                        return None
                    if err.status == 400 and index + 1 < len(field_variants):
                        break  # this field list is not understood; try the next
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


#: Comments IGDB writes by hand against an alternative name. A romanisation is
#: the game's own title in Latin script, which is what "original title" means
#: here; a translation, a respelling or an abbreviation is not.
def original_title(game: dict) -> str:
    fallback = ""
    for entry in game.get("alternative_names") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        comment = str(entry.get("comment") or "").lower()
        if not name or "title" not in comment:
            continue
        if "romani" in comment:
            return name
        if not any(word in comment for word in ("translat", "alternative", "abbrev", "spelling")):
            fallback = fallback or name
    return fallback


def title_keys(game: dict) -> set:
    """Every name this game answers to, normalised.

    A dump is often named in the language it was sold in -- "Akumajou
    Densetsu" for Castlevania III -- and the catalogue files that as an
    alternative name rather than the title.
    """
    keys = {namer.normalise(str(game.get("name") or ""))}
    keys.update(namer.normalise(name) for name in names(game, "alternative_names"))
    keys.discard("")
    return keys


#: Markers that a dump is for Nintendo's VS. System or PlayChoice-10. Both are
#: arcade cabinets built from console parts, so the file sits in the console's
#: folder and plays on a console emulator, but the catalogue rightly files the
#: game under Arcade.
VS_SYSTEM_TAGS = ("unisystem", "playchoice", "dualsystem")


def is_vs_system(request: Request) -> bool:
    title = str(request.title() or "").strip().lower()
    if title.startswith("vs. ") or title.startswith("vs "):
        return True
    name = str(request.get("filename") or "").lower()
    return any(tag in name for tag in VS_SYSTEM_TAGS)


def is_the_game(game: dict) -> bool:
    """Whether the row is the game, rather than an add-on, bundle or episode."""
    kind = game.get("game_type", game.get("category"))
    return kind is None or kind in GAME_ITSELF


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
        if "rating_category" in item:
            value = RATING_CATEGORIES.get(item["rating_category"])
        else:
            value = RATINGS.get(item.get("rating"))
        if board and value:
            # What the board rated it for, such as violence or bad language
            reasons = [str(d["description"]) for d in
                       item.get("rating_content_descriptions") or item.get("content_descriptions") or []
                       if isinstance(d, dict) and d.get("description")]
            out.append({"board": board, "value": value, "descriptors": ", ".join(reasons)})
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
    # A series is the run of games a title belongs to, like Mario Kart; a
    # franchise is wider, like Mario, and stays a collection only
    series = names(game, "collections") or names(game, "collection")
    if series:
        out["series"] = series[0]
    edition = EDITION_NAMES.get(game.get("game_type", game.get("category")))
    if edition:
        out["edition"] = edition
    native = original_title(game)
    if native and namer.normalise(native) != namer.normalise(out["title"]):
        out["originaltitle"] = native
    out["names"] = [out["title"]] + names(game, "alternative_names")
    # A game sold under another name in a region: Probotector in Europe
    for _, title, _ in localizations(game):
        if title and title not in out["names"]:
            out["names"].append(title)
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
        # What makes a game one to play together on the sofa
        for field, key in (("dropin", "dropin"), ("splitscreen", "splitscreen")):
            if isinstance(mode.get(field), bool):
                out[key] = mode[field]
        coop_players = mode.get("offlinecoopmax")
        if isinstance(coop_players, int) and not isinstance(coop_players, bool) and coop_players > 0:
            out["coopplayers"] = coop_players
    rating = game.get("total_rating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        out["ratings"] = {"igdb": {"rating": round(float(rating), 1), "max": 100,
                                   "votes": int(game.get("total_rating_count") or 0)}}
    critic = game.get("aggregated_rating")
    if isinstance(critic, (int, float)) and not isinstance(critic, bool):
        out.setdefault("ratings", {})["igdbcritic"] = {
            "rating": round(float(critic), 1), "max": 100,
            "votes": int(game.get("aggregated_rating_count") or 0)}
    # Keywords, perspectives and engines are all tags as far as the library is
    # concerned, and it already has somewhere to put them
    tags = names(game, "keywords") + names(game, "player_perspectives") + names(game, "game_engines")
    if tags:
        out["tags"] = list(dict.fromkeys(tags))
    clips = [v for v in game.get("videos") or [] if isinstance(v, dict) and v.get("video_id")]
    if clips:
        # A video IGDB calls a trailer, else whatever it lists first
        named = [v for v in clips if "trailer" in str(v.get("name") or "").lower()]
        out["trailer"] = TRAILER.format((named or clips)[0]["video_id"])
    similar = names(game, "similar_games")
    if similar:
        out["similar"] = similar
    related = [{"kind": kind, "title": title} for field, kind in RELATED
               for title in names(game, field)]
    if related:
        out["related"] = related
    languages = language_support(game)
    if languages:
        out["languagesupport"] = languages
    modes = names(game, "game_modes")
    if modes:
        out["modes"] = modes
    extra = wider(game)
    if extra:
        out["igdb"] = extra
    return out


#: IGDB's regions for a game's localizations, by the names the providers give regions
LOCALIZATION_REGIONS = {"north america": "USA", "worldwide": "World", "europe": "Europe",
                        "japan": "Japan", "korea": "Korea", "china": "China", "asia": "Asia",
                        "australia": "Australia", "new zealand": "New Zealand", "brazil": "Brazil"}

#: Games IGDB relates to this one, and what each is to it
RELATED = (("remakes", "remake"), ("remasters", "remaster"), ("ports", "port"),
           ("dlcs", "dlc"), ("expansions", "expansion"), ("standalone_expansions", "expansion"),
           ("parent_game", "original"))

#: Lists worth keeping whole, by the name they are given back under
WIDER_LISTS = (("player_perspectives", "perspectives"), ("keywords", "keywords"),
               ("game_engines", "engines"), ("alternative_names", "alsoknownas"),
               ("similar_games", "similar"), ("dlcs", "dlc"), ("expansions", "expansions"),
               ("remakes", "remakes"), ("remasters", "remasters"), ("ports", "ports"))
#: Single numbers worth keeping, by the name they are given back under
WIDER_NUMBERS = (("aggregated_rating", "criticrating"), ("aggregated_rating_count", "criticvotes"),
                 ("rating", "userrating"), ("rating_count", "uservotes"), ("hypes", "hypes"))


def wider(game: dict) -> Dict[str, Any]:
    """What IGDB knows beyond the fields the library has a home for.

    Kept together under one key so a later decision about where any of it
    belongs does not mean scraping the whole collection again.
    """
    out: Dict[str, Any] = {}
    for field, key in WIDER_LISTS:
        values = names(game, field)
        if values:
            out[key] = values
    for field, key in WIDER_NUMBERS:
        value = game.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = round(float(value), 1) if "rating" in key else int(value)
    for field, key in (("status", "status"), ("version_title", "versiontitle")):
        if game.get(field) not in (None, ""):
            out[key] = game[field]
    parent = game.get("parent_game")
    if isinstance(parent, dict) and parent.get("name"):
        out["parent"] = str(parent["name"])
    languages = []
    for entry in game.get("language_supports") or []:
        language = entry.get("language") if isinstance(entry, dict) else None
        if isinstance(language, dict) and language.get("name"):
            languages.append(str(language["name"]))
    if languages:
        out["languages"] = list(dict.fromkeys(languages))
    sites = [str(w["url"]) for w in game.get("websites") or []
             if isinstance(w, dict) and w.get("url")]
    if sites:
        out["websites"] = sites
    videos = ["https://www.youtube.com/watch?v=" + str(v["video_id"])
              for v in game.get("videos") or [] if isinstance(v, dict) and v.get("video_id")]
    if videos:
        out["videos"] = videos
    return out


def time_to_beat(row: dict) -> Dict[str, int]:
    """IGDB's three times, in seconds, under the names Kodi gives them."""
    out = {}
    for field, key in (("hastily", "main"), ("normally", "extras"), ("completely", "complete")):
        value = row.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            out[key] = value
    return out


def is_spinoff(membership: Optional[str]) -> Optional[bool]:
    """Whether a game is a spin-off of its series, by IGDB's name for its place in it."""
    kind = str(membership or "").lower()
    if "spin" in kind:
        return True
    if "main" in kind:
        return False
    return None


def localizations(game: dict) -> List[Tuple[str, str, str]]:
    """Each localization's region, as the providers name regions, its title and its cover."""
    out = []
    for item in game.get("game_localizations") or []:
        if not isinstance(item, dict):
            continue
        region = item.get("region") if isinstance(item.get("region"), dict) else {}
        found = (LOCALIZATION_REGIONS.get(str(region.get("name") or "").strip().lower())
                 or LOCALIZATION_REGIONS.get(str(region.get("identifier") or "").strip().lower()))
        if not found:
            continue
        cover = item.get("cover") if isinstance(item.get("cover"), dict) else {}
        url = IMAGE_URL.format("cover_big", cover["image_id"]) if cover.get("image_id") else ""
        out.append((found, str(item.get("name") or "").strip(), url))
    return out


def regional_localization(game: dict, preferred: Sequence[str]) -> Optional[Tuple[str, str, str]]:
    """The game's name and cover in the player's first region IGDB names, where it was localized there.

    A region further down the player's list doesn't count: what IGDB calls the game, and its own
    cover, are what was sold in the player's region unless IGDB says otherwise.
    """
    named = {region.lower() for region in LOCALIZATION_REGIONS.values()}
    for region in preferred:
        if region in named:
            for found, title, cover in localizations(game):
                if found.lower() == region and (title or cover):
                    return found, title, cover
            return None
    return None


def language_support(game: dict) -> List[Dict[str, Any]]:
    """Each language the game can be played in, and whether it is spoken, subtitled or in the menus."""
    out: Dict[str, Dict[str, Any]] = {}
    for item in game.get("language_supports") or []:
        if not isinstance(item, dict) or not isinstance(item.get("language"), dict):
            continue
        language = str(item["language"].get("name") or "").strip()
        if not language:
            continue
        entry = out.setdefault(language, {"language": language})
        kind = str((item.get("language_support_type") or {}).get("name") or "").lower()
        for word, key in (("audio", "audio"), ("subtitle", "subtitles"), ("interface", "interface")):
            if word in kind:
                entry[key] = True
    return list(out.values())


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
